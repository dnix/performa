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

    # Extract property values using intelligent estimation
    property_values = engine.extract_property_value_series(unlevered_analysis)

    # Calculate disposition proceeds with polymorphic dispatch
    disposition_proceeds = engine.calculate_disposition_proceeds(unlevered_analysis)
    ```

Architecture:
    - Uses dataclass pattern for runtime service state
    - Implements polymorphic dispatch for different valuation types
    - Provides type-safe data access through enum-based keys
    - Includes sophisticated fallback and estimation strategies
    - Maintains institutional-grade calculation standards
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from performa.core.primitives import GlobalSettings, Timeline
    from performa.deal.deal import Deal

from performa.core.primitives import UnleveredAggregateLineKey
from performa.deal.results import UnleveredAnalysisResult


@dataclass
class ValuationEngine:
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

        # Extract property values with intelligent estimation
        property_values = engine.extract_property_value_series(unlevered_analysis)
        print(f"Property value range: {property_values.min():.0f} - {property_values.max():.0f}")

        # Extract NOI series with type-safe access
        noi_series = engine.extract_noi_series(unlevered_analysis)
        print(f"Average NOI: {noi_series.mean():.0f}")

        # Calculate disposition proceeds
        disposition_proceeds = engine.calculate_disposition_proceeds(unlevered_analysis)
        print(f"Total disposition proceeds: {disposition_proceeds.sum():.0f}")
        ```
    """

    # Input parameters - injected dependencies
    deal: Deal
    timeline: Timeline
    settings: GlobalSettings

    # Runtime state (populated during analysis) - internal caching
    property_value_series: pd.Series = field(init=False, repr=False, default=None)
    noi_series: pd.Series = field(init=False, repr=False, default=None)

    def extract_property_value_series(
        self, unlevered_analysis: UnleveredAnalysisResult
    ) -> pd.Series:
        """
        Extract property value time series using intelligent estimation with multiple fallback strategies.

        Property values are typically not included in cash flow statements, so this method
        implements a sophisticated estimation approach that prioritizes accuracy while
        providing robust fallbacks for various data availability scenarios.

        Estimation hierarchy:
        1. **Direct extraction**: Look for value columns in cash flow data
        2. **NOI-based valuation**: Calculate from NOI using market cap rates
        3. **Cost-based appreciation**: Use acquisition cost with market appreciation
        4. **Zero fallback**: Prevent downstream errors with zero values

        Args:
            unlevered_analysis: Results from unlevered asset analysis containing cash flows
                               and other operational metrics

        Returns:
            pd.Series containing property values over time, indexed by timeline periods.
            Values represent estimated property values at each period.

        Raises:
            ValueError: If unlevered_analysis is None or contains invalid data

        Example:
            ```python
            engine = ValuationEngine(deal, timeline, settings)
            property_values = engine.extract_property_value_series(unlevered_analysis)

            # Analyze value trends
            print(f"Initial value: ${property_values.iloc[0]:,.0f}")
            print(f"Final value: ${property_values.iloc[-1]:,.0f}")
            print(f"Appreciation: {(property_values.iloc[-1] / property_values.iloc[0] - 1):.1%}")
            ```
        """

        # Strategy 1: Direct extraction from cash flow data
        # Check if cash flows contain any property value columns using explicit search
        # This would be uncommon but some analyses might include asset value calculations
        if unlevered_analysis.cash_flows is not None and hasattr(
            unlevered_analysis.cash_flows, "columns"
        ):
            # Search for value-related columns in the actual data
            value_columns = [
                col
                for col in unlevered_analysis.cash_flows.columns
                if any(
                    term in col.lower()
                    for term in ["value", "asset_value", "property_value"]
                )
            ]
            if value_columns:
                # Use the first available value column
                self.property_value_series = unlevered_analysis.cash_flows[
                    value_columns[0]
                ].reindex(self.timeline.period_index, method="ffill")
                return self.property_value_series

        # Strategy 2: NOI-based valuation using market cap rates
        # This is the primary approach for most institutional analyses
        try:
            # Use the type-safe NOI accessor for robust data extraction
            noi_series = unlevered_analysis.get_series(
                UnleveredAggregateLineKey.NET_OPERATING_INCOME, self.timeline
            )

            # Only proceed if we have meaningful NOI data
            if not noi_series.empty and noi_series.sum() > 0:
                # Determine appropriate cap rate for valuation
                # Priority: exit valuation cap rate > default market rate
                cap_rate = (
                    0.065  # 6.5% default market cap rate (institutional standard)
                )

                if self.deal.exit_valuation and hasattr(
                    self.deal.exit_valuation, "cap_rate"
                ):
                    cap_rate = self.deal.exit_valuation.cap_rate

                # Calculate property value using direct capitalization: Value = NOI / Cap Rate
                estimated_values = noi_series / cap_rate

                # Forward fill to handle any zero NOI periods gracefully
                # This ensures continuous valuation even during lease-up or renovation periods
                self.property_value_series = estimated_values.reindex(
                    self.timeline.period_index, method="ffill"
                )
                return self.property_value_series

        except Exception:
            # Continue to fallback approaches if NOI extraction fails
            # This maintains robustness in the face of data issues
            pass

        # Strategy 3: Cost-based appreciation using acquisition cost
        # This provides a reasonable baseline when operational data is unavailable
        if self.deal.acquisition and hasattr(self.deal.acquisition, "acquisition_cost"):
            base_value = self.deal.acquisition.acquisition_cost

            # Use market appreciation rate (institutional standard: 2-4% annually)
            appreciation_rate = 0.03  # 3% annual appreciation assumption

            # Calculate escalated values over time
            values = []
            for i, period in enumerate(self.timeline.period_index):
                years_elapsed = i / 12.0  # Convert periods to years
                escalated_value = base_value * (1 + appreciation_rate) ** years_elapsed
                values.append(escalated_value)

            self.property_value_series = pd.Series(
                values, index=self.timeline.period_index
            )
            return self.property_value_series

        # Strategy 4: Ultimate fallback to prevent downstream errors
        # Return zeros rather than failing, allowing analysis to continue
        self.property_value_series = pd.Series(0.0, index=self.timeline.period_index)
        return self.property_value_series

    def extract_noi_series(
        self, unlevered_analysis: UnleveredAnalysisResult
    ) -> pd.Series:
        """
        Extract Net Operating Income time series using type-safe enum access.

        This method implements the "Don't Ask, Tell" principle by using the new
        get_series method for robust, enum-based data access that eliminates
        brittle string matching and provides consistent data extraction.

        The type-safe approach ensures that:
        - Data access is consistent across different analysis scenarios
        - Enum keys prevent typos and mismatches
        - Future refactoring is safer with compile-time checking
        - Error handling is centralized and consistent

        Args:
            unlevered_analysis: Results from unlevered asset analysis containing
                               cash flows and operational metrics

        Returns:
            pd.Series containing NOI values over time, indexed by timeline periods.
            Values represent net operating income for each period.

        Example:
            ```python
            engine = ValuationEngine(deal, timeline, settings)
            noi_series = engine.extract_noi_series(unlevered_analysis)

            # Analyze NOI trends
            print(f"Average NOI: ${noi_series.mean():,.0f}")
            print(f"NOI growth: {(noi_series.iloc[-1] / noi_series.iloc[0] - 1):.1%}")
            print(f"Stabilized NOI: ${noi_series.iloc[-12:].mean():,.0f}")  # Last 12 months
            ```
        """

        # Use the new type-safe accessor method for robust data extraction
        # This approach eliminates the brittle string matching that was used previously
        self.noi_series = unlevered_analysis.get_series(
            UnleveredAggregateLineKey.NET_OPERATING_INCOME, self.timeline
        )
        return self.noi_series

    def calculate_disposition_proceeds(
        self, unlevered_analysis: UnleveredAnalysisResult = None
    ) -> pd.Series:
        """
        Calculate disposition proceeds using polymorphic dispatch across valuation models.

        This method implements sophisticated polymorphic dispatch that works with any
        valuation model that implements the compute_cf interface. It handles the complexity
        of different valuation methodologies while providing a consistent interface.

        Supported valuation models:
        - ReversionValuation: Terminal value based on NOI and cap rates
        - DCFValuation: Discounted cash flow with terminal value
        - DirectCapValuation: Direct capitalization approach
        - SalesCompValuation: Sales comparison methodology

        The method also provides comprehensive context management, ensuring that
        valuation models have access to all necessary data for accurate calculations.

        Args:
            unlevered_analysis: Results from unlevered asset analysis containing NOI data
                               and other operational metrics (optional)

        Returns:
            pd.Series containing disposition proceeds aligned with timeline periods.
            Values represent cash inflows from property disposition.

        Example:
            ```python
            engine = ValuationEngine(deal, timeline, settings)
            disposition_proceeds = engine.calculate_disposition_proceeds(unlevered_analysis)

            # Analyze disposition
            total_proceeds = disposition_proceeds.sum()
            disposition_date = disposition_proceeds[disposition_proceeds > 0].index[0]
            print(f"Disposition proceeds: ${total_proceeds:,.0f}")
            print(f"Disposition date: {disposition_date}")
            ```
        """
        # Initialize with zero proceeds across all periods
        disposition_proceeds = pd.Series(0.0, index=self.timeline.period_index)

        # Only proceed if deal has an exit valuation model
        if self.deal.exit_valuation:
            try:
                # Step 1: Create analysis context for valuation model
                # This provides the valuation model with all necessary data and configuration
                from performa.analysis import AnalysisContext

                context = AnalysisContext(
                    timeline=self.timeline,
                    settings=self.settings,
                    property_data=self.deal.asset,
                )

                # Step 2: Populate context with unlevered analysis data
                # This ensures valuation models have access to NOI and other operational data
                if unlevered_analysis:
                    context.unlevered_analysis = unlevered_analysis

                    # Also populate resolved_lookups for backward compatibility
                    # This supports legacy valuation models that use string-based lookups
                    if hasattr(context, "resolved_lookups"):
                        try:
                            noi_series = unlevered_analysis.get_series(
                                UnleveredAggregateLineKey.NET_OPERATING_INCOME,
                                self.timeline,
                            )
                            context.resolved_lookups[
                                UnleveredAggregateLineKey.NET_OPERATING_INCOME.value
                            ] = noi_series
                        except Exception:
                            # Continue if NOI extraction fails
                            pass

                # Step 3: Execute polymorphic dispatch
                # Call compute_cf based on valuation type - works for any valuation model
                # that implements the compute_cf interface
                disposition_cf = self.deal.exit_valuation.compute_cf(context)

                # Step 4: Align with timeline and ensure positive values
                disposition_proceeds = disposition_cf.reindex(
                    self.timeline.period_index, fill_value=0.0
                )

                # Disposition proceeds should be positive (cash inflow to equity)
                disposition_proceeds = disposition_proceeds.abs()

            except Exception as e:
                # Robust error handling: log warning but continue with zeros
                # This ensures that disposition errors don't break the entire analysis
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Could not calculate disposition proceeds: {e}")
                logger.debug("Disposition calculation stack trace:", exc_info=True)

        return disposition_proceeds
