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
        self.context.noi_series = noi_series  # ← For both analysts

    # DELETED: extract_property_value_series() - Replaced by _calculate_property_value()
    # This method extracted from asset_result which is no longer needed
    # Use ValuationEngine.process() instead

    # DELETED: extract_noi_series() - NOI now queried directly from ledger
    # This method extracted from asset_result which is no longer needed
    # Use ValuationEngine.process() instead

    # DELETED: _extract_noi_from_ledger() - Redundant pre-refactor cruft
    # Use self.queries.noi() directly in process() method instead

    # DELETED: calculate_disposition_proceeds() - Replaced by _calculate_disposition_proceeds()
    # This method took unlevered_analysis which is no longer needed
    # Use ValuationEngine.process() instead

    def _calculate_refi_property_value(self, noi_series: pd.Series) -> pd.Series:
        """
        Calculate property value for refinancing based on user-defined NOI methodology.

        This valuation is used by DebtAnalyzer for LTV calculations and loan sizing.
        Supports LTM (trailing 12mo), NTM (forward-looking), or current period methods.

        Args:
            noi_series: NOI from ledger (monthly)

        Returns:
            Property value time series for refinancing
        """
        # Get refinancing settings
        refi_cap_rate = self.context.settings.valuation.refinancing_cap_rate
        noi_method = self.context.settings.valuation.refinancing_noi_method

        if noi_series.empty or noi_series.sum() <= 0:
            return pd.Series(0.0, index=self.context.timeline.period_index)

        if refi_cap_rate <= 0:
            return pd.Series(0.0, index=self.context.timeline.period_index)

        # Align NOI series with timeline
        aligned_noi = self.context.timeline.align_series(noi_series, fill_value=0.0)

        # Calculate property values based on NOI methodology
        property_values = []

        for i, period in enumerate(self.context.timeline.period_index):
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

            # Annualize and apply cap rate
            annual_noi = period_noi * 12
            property_value = annual_noi / refi_cap_rate
            property_values.append(property_value)

        return pd.Series(property_values, index=self.context.timeline.period_index)

    # DELETED: _calculate_property_value() - Replaced by _calculate_refi_property_value()
    # This method contained legacy logic with hidden defaults and complex fallbacks.
    # The new approach separates refinancing (conservative) and exit (user-defined) valuations.

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
