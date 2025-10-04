# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Valuation Engine Specialist

This module provides the ValuationEngine service that handles property valuation calculations
with sophisticated polymorphic dispatch across different valuation methodologies.

The ValuationEngine serves as the abstraction layer between deal analysis and the various
valuation models (ReversionValuation, DCFValuation, DirectCapValuation, SalesCompValuation),
providing consistent interfaces for property value extraction and disposition analysis.

Key responsibilities:
- Property value time series extraction with intelligent estimation
- Net Operating Income (NOI) series extraction with type-safe enum access
- Disposition proceeds calculation with polymorphic dispatch
- Valuation model integration and context management

The service implements sophisticated fallback strategies to ensure robust valuation
even when primary data sources are unavailable, following institutional modeling standards.

Example:
    ```python
    from performa.deal.analysis import ValuationEngine

    # Create valuation engine
    engine = ValuationEngine(deal, timeline, settings)

    # Process valuation with settings-driven assumptions
    result = ValuationEngine.process(context)

    # Access computed values
    property_values = result["property_value"]
    disposition_proceeds = result["gross_proceeds"]
    ```

Architecture:
    - Uses dataclass pattern for runtime service state
    - Implements polymorphic dispatch for different valuation types
    - Provides type-safe data access through enum-based keys
    - Includes sophisticated fallback and estimation strategies
    - Maintains institutional-grade calculation standards
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from ...core.ledger.records import SeriesMetadata
from ...core.primitives import CashFlowCategoryEnum, ValuationSubcategoryEnum
from .base import AnalysisSpecialist


@dataclass
class ValuationEngine(AnalysisSpecialist):
    """
    Specialist service for handling property valuation calculations with polymorphic dispatch.

    This service provides sophisticated valuation capabilities that bridge the gap between
    asset analysis and various valuation methodologies. It handles the complexity of
    extracting valuation data from different sources and applying appropriate estimation
    strategies when primary data is unavailable.

    Key features:
    - Intelligent property value estimation with multiple fallback strategies
    - Type-safe NOI extraction using enum-based keys
    - Polymorphic dispatch across different valuation models
    - Robust error handling with graceful degradation
    - Institutional-grade calculation standards

    Attributes:
        deal: The deal containing valuation and asset information
        timeline: Analysis timeline for valuation calculations
        settings: Global settings for valuation configuration
        property_value_series: Cached property value time series (internal use)
        noi_series: Cached NOI time series (internal use)

    Example:
        ```python
        engine = ValuationEngine(deal, timeline, settings)

        # Process valuation with settings
        result = ValuationEngine.process(context)

        # Access computed values
        property_values = result["property_value"]
        print(f"Property value range: {property_values.min():.0f} - {property_values.max():.0f}")

        noi_series = result["noi_series"]
        print(f"Average NOI: {noi_series.mean():.0f}")

        disposition_proceeds = result["gross_proceeds"]
        print(f"Total disposition proceeds: {disposition_proceeds.sum():.0f}")
        ```
    """

    # Fields inherited from AnalysisSpecialist base class:
    # - context (DealContext)
    # - deal, timeline, settings, ledger (via properties)
    # - queries (LedgerQueries)

    def process(self) -> None:
        """
        Settings-driven valuation using ledger data.
        Always run - provides data for debt and disposition.

        Updates context with refinancing and exit valuations for downstream passes.
        """
        # Query NOI directly from ledger - already have queries from base class
        noi_series = self.queries.noi()

        # Set NOI series in context for downstream passes
        self.context.noi_series = noi_series  # ← DirectCap valuation needs this!

        # REFINANCING VALUATION: Conservative cap rate on stabilized NOI (for DebtAnalyzer)
        refi_property_value = self._calculate_refi_property_value(noi_series)

        # EXIT VALUATION: User-defined method or cap rate fallback (for DispositionAnalyzer)
        exit_gross_proceeds = self._calculate_exit_gross_proceeds(noi_series)

        # Ferry specific values to context for downstream passes
        self.context.refi_property_value = (
            refi_property_value  # ← For DebtAnalyzer LTV calculations
        )
        self.context.exit_gross_proceeds = (
            exit_gross_proceeds  # ← For DispositionAnalyzer
        )

        # Record calculated valuations in ledger for audit trail and API consistency
        self._record_valuations_in_ledger(refi_property_value, exit_gross_proceeds)

    ###########################################################################
    # VALUATION CALCULATION METHODS
    ###########################################################################

    def _calculate_refi_property_value(self, noi_series: pd.Series) -> pd.Series:
        """
        Calculate property value for refinancing using development-aware valuation.

        Uses dual-approach valuation based on project phase:
        - Development phase: Cost accumulation (land + cumulative capital uses)
        - Stabilized phase: Income approach (annualized NOI / cap rate)

        Phase detection (when method='auto') uses two tests:
        1. NOI test: Current NOI < threshold × stabilized NOI (default 70%)
        2. CapEx test: Month-over-month cost growth > threshold (default 1%)

        Development phase if EITHER test is true. This catches both ground-up
        (low NOI) and value-add (active capex) scenarios.

        Configuration (via settings.valuation):
        - development_valuation_method: 'auto', 'cost', or 'income'
        - development_phase_noi_threshold: NOI threshold (0-1, default 0.70)
        - development_phase_capex_threshold: Cost growth threshold (0-1, default 0.01)

        Args:
            noi_series: Monthly NOI from ledger queries

        Returns:
            Monthly property value time series aligned with deal timeline
        """
        # Get valuation settings
        refi_cap_rate = self.context.settings.valuation.refinancing_cap_rate
        noi_method = self.context.settings.valuation.refinancing_noi_method
        val_method = self.context.settings.valuation.development_valuation_method
        noi_threshold_pct = self.context.settings.valuation.development_phase_noi_threshold
        capex_threshold_pct = self.context.settings.valuation.development_phase_capex_threshold

        # Get cumulative capital uses for cost accumulation approach
        # Query ledger directly for precise timing control
        ledger_df = self.context.ledger.to_dataframe()
        capital_df = ledger_df[ledger_df['flow_purpose'] == 'Capital Use'].copy()
        
        # Calculate cumulative costs by period
        if not capital_df.empty:
            capital_df['period'] = capital_df['date'].dt.to_period('M')
            period_costs = capital_df.groupby('period')['amount'].sum().abs()
            cumulative_costs = period_costs.cumsum()
            # Convert to datetime index for alignment
            cumulative_costs.index = cumulative_costs.index.to_timestamp()
            aligned_costs = self.context.timeline.align_series(cumulative_costs, fill_value=0.0)
        else:
            aligned_costs = pd.Series(0.0, index=self.context.timeline.period_index)

        # Align NOI series with timeline
        aligned_noi = self.context.timeline.align_series(noi_series, fill_value=0.0)

        # Estimate stabilized NOI for development phase detection
        # Use last 12 months average (most reliable), or forward-looking if insufficient history
        if len(aligned_noi) >= 12:
            stabilized_noi = aligned_noi.iloc[-12:].mean()
        else:
            # Early in project: use forward-looking average or peak NOI as proxy
            stabilized_noi = aligned_noi[aligned_noi > 0].mean() if (aligned_noi > 0).any() else 0.0

        # Calculate NOI threshold for phase detection (configurable)
        development_noi_threshold = stabilized_noi * noi_threshold_pct

        # Calculate property values based on development phase
        property_values = []

        for i, period in enumerate(self.context.timeline.period_index):
            # Get period NOI based on methodology
            if noi_method == "ltm":
                # Trailing 12-month average (conservative, lender-friendly)
                start_idx = max(0, i - 11)  # Look back 12 months (including current)
                period_noi = (
                    aligned_noi.iloc[start_idx : i + 1].mean()
                    if i > 0
                    else aligned_noi.iloc[i]
                )
            elif noi_method == "ntm":
                # Forward-looking 12-month average (optimistic)
                end_idx = min(len(aligned_noi), i + 12)  # Look forward 12 months
                period_noi = aligned_noi.iloc[i:end_idx].mean()
            else:  # current
                # Current period NOI (most volatile)
                period_noi = aligned_noi.iloc[i]

            # ============================================================
            # PHASE DETECTION & VALUATION APPROACH SELECTION
            # ============================================================
            
            # Handle forced valuation methods
            if val_method == "cost":
                # Force cost accumulation (user override)
                use_cost_approach = aligned_costs.iloc[i] > 0
            elif val_method == "income":
                # Force income approach (user override)
                use_cost_approach = False
            else:
                # Auto-detect phase using dual criteria (default)
                
                # Criterion A: NOI Threshold Test
                # Low NOI indicates development/lease-up phase
                noi_test = period_noi < development_noi_threshold
                
                # Criterion B: Capital Deployment Test
                # Active capital deployment indicates development/improvement
                cost_growth_rate = 0.0
                if i > 0 and aligned_costs.iloc[i - 1] > 0:
                    cost_growth_rate = (
                        (aligned_costs.iloc[i] - aligned_costs.iloc[i - 1])
                        / aligned_costs.iloc[i - 1]
                    )
                capex_test = cost_growth_rate > capex_threshold_pct
                
                # Use cost approach if EITHER test is true AND we have capital deployed
                use_cost_approach = (noi_test or capex_test) and aligned_costs.iloc[i] > 0
            
            # Apply selected valuation approach
            if use_cost_approach:
                # DEVELOPMENT PHASE: Cost accumulation
                # Property worth = what we've put into it
                property_value = aligned_costs.iloc[i]
            elif refi_cap_rate > 0:
                # STABILIZED PHASE: Income approach
                # Property worth = income stream / required return
                annual_noi = period_noi * 12
                property_value = annual_noi / refi_cap_rate
            else:
                # Fallback: no cap rate configured, cannot value
                property_value = 0.0

            # Ensure non-negative property values
            property_value = max(0.0, property_value)
            property_values.append(property_value)

        return pd.Series(property_values, index=self.context.timeline.period_index)

    def _calculate_exit_gross_proceeds(self, noi_series: pd.Series) -> pd.Series:
        """
        Calculate gross disposition proceeds using exit_valuation.compute_cf() or cap rate fallback.

        This valuation is used by DispositionAnalyzer for exit cash flows.
        Uses user-defined exit strategy with sophisticated fallback options.

        Args:
            noi_series: NOI from ledger

        Returns:
            Gross proceeds time series from exit strategy
        """
        gross_proceeds = pd.Series(0.0, index=self.context.timeline.period_index)

        if not self.context.deal.exit_valuation:
            return gross_proceeds

        # Use exit_valuation.compute_cf() - all AnyValuation types have this method
        try:
            exit_cf = self.context.deal.exit_valuation.compute_cf(self.context)
            if exit_cf is not None and not exit_cf.empty and exit_cf.sum() > 0:
                return exit_cf  # Use computed exit cash flows directly
        except Exception as e:
            # Log the exception for debugging (but continue to fallback)
            logging.warning(f"Exit valuation compute_cf() failed: {e}")
            pass  # Fall back to cap rate calculation

        # Fallback: Cap rate calculation using NOI
        if noi_series.empty or noi_series.sum() <= 0:
            return gross_proceeds

        exit_period = self.context.timeline.period_index[-1]

        # Calculate exit NOI using user-defined methodology (LTM or NTM)
        noi_method = self.context.settings.valuation.exit_noi_method

        if noi_method == "ltm":
            # Trailing 12-month average (conservative, industry standard)
            # Smooths monthly volatility and reflects recent operational performance
            if len(noi_series) >= 12:
                exit_noi = noi_series.iloc[-12:].mean()
            else:
                exit_noi = noi_series.mean()  # Fallback for shorter series
        else:  # ntm
            # Forward-looking/current month NOI (optimistic for growth properties)
            # Uses most recent month as basis for forward projections
            exit_noi = noi_series.iloc[-1] if not noi_series.empty else 0.0

        # Get exit cap rate - fail fast if not available
        exit_cap_rate = self.context.deal.exit_valuation.cap_rate

        if exit_cap_rate > 0 and exit_noi > 0:
            # Convert monthly NOI to annual NOI for cap rate valuation
            annual_noi = (
                exit_noi * 12
            )  # NOI series is monthly, need annual for cap rate
            gross_proceeds[exit_period] = annual_noi / exit_cap_rate

        return gross_proceeds

    def _record_valuations_in_ledger(
        self, refi_property_value: pd.Series, exit_gross_proceeds: pd.Series
    ) -> None:
        """
        Record calculated valuations in ledger as non-cash analytical entries.

        These entries represent property appraisals and valuation snapshots that
        are recorded for audit trail purposes and API consistency. They are marked
        with flow_purpose="Valuation" to distinguish them from actual cash transactions.

        Note: Valuation entries should be excluded from cash flow calculations,
        balance validations, and financial analysis as they represent analytical
        snapshots rather than actual monetary transactions.

        These entries are used for:
        - API consistency (asset_value_at, disposition_valuation methods)
        - Audit trail of property valuations over time
        - LTV calculation snapshots
        - Refinancing analysis support

        Args:
            refi_property_value: Refinancing property value time series
            exit_gross_proceeds: Exit proceeds time series
        """
        # Only record non-zero valuations to avoid cluttering ledger

        # Record refinancing valuations
        non_zero_refi = refi_property_value[refi_property_value > 0]
        if not non_zero_refi.empty:
            refi_metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.VALUATION,
                subcategory=ValuationSubcategoryEnum.ASSET_VALUATION,
                item_name="Non-Cash: Refinancing Valuation",
                source_id=str(self.deal.uid),
                asset_id=str(self.deal.asset.uid),
                pass_num=1,  # Valuation pass
            )
            self.ledger.add_series(non_zero_refi, refi_metadata)

        # Record exit valuations
        non_zero_exit = exit_gross_proceeds[exit_gross_proceeds > 0]
        if not non_zero_exit.empty:
            exit_metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.VALUATION,
                subcategory=ValuationSubcategoryEnum.ASSET_VALUATION,
                item_name="Non-Cash: Exit Appraisal",
                source_id=str(self.deal.uid),
                asset_id=str(self.deal.asset.uid),
                pass_num=1,  # Valuation pass
            )
            self.ledger.add_series(non_zero_exit, exit_metadata)
