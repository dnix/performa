# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal Analysis Orchestrator

This module provides the DealCalculator service that orchestrates the complete deal analysis workflow
by delegating to specialist services while maintaining a clean public API and comprehensive functionality.

The DealCalculator serves as the central orchestrator for the entire deal analysis framework, coordinating
the execution of specialist services in the proper sequence to produce comprehensive deal analysis results.
It implements the multi-pass analysis approach that ensures all components have access to the data they need.

The orchestrator follows the established analysis workflow:
1. **Unlevered Asset Analysis** - Pure asset performance without financing effects
2. **Valuation Analysis** - Property value estimation and disposition proceeds calculation
3. **Debt Analysis** - Financing structure analysis with DSCR and covenant monitoring
4. **Cash Flow Analysis** - Institutional-grade funding cascade and levered cash flows
5. **Partnership Analysis** - Equity waterfall and partner distribution calculations
6. **Deal Metrics** - Comprehensive deal-level performance metrics

Key capabilities:
- **Multi-Pass Analysis**: Systematic execution of analysis services in proper sequence
- **Typed State Management**: Maintains strongly-typed intermediate results during analysis
- **Comprehensive Results**: Returns complete DealAnalysisResult with all analysis components
- **Backward Compatibility**: Maintains legacy API support for existing tests and integrations
- **Error Handling**: Robust error handling with graceful degradation and detailed error reporting

The orchestrator implements the "orchestration pattern" where it coordinates specialist services
without duplicating their logic, ensuring clean separation of concerns and maintainability.

Example:
    ```python
    from performa.deal.orchestrator import DealCalculator

    # Create orchestrator with dependencies
    calculator = DealCalculator(deal, timeline, settings)

    # Execute complete analysis workflow
    results = calculator.run()

    # Access comprehensive results
    print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
    print(f"DSCR minimum: {results.financing_analysis.dscr_summary.minimum_dscr:.2f}")
    print(f"Partner count: {len(results.partner_distributions.waterfall_details.partner_results)}")
    ```

Architecture:
    - Uses dataclass pattern for runtime service orchestration
    - Maintains typed state during multi-pass analysis execution
    - Delegates to specialist services for domain-specific logic
    - Returns strongly-typed results with comprehensive component access
    - Provides backward compatibility for existing integrations

Integration:
    - Integrates with all specialist services in the analysis module
    - Maintains compatibility with existing test suites and integrations
    - Provides comprehensive error handling and logging
    - Supports both new typed API and legacy compatibility methods
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import pandas as pd
from pyxirr import xirr

from performa.analysis import run
from performa.analysis.orchestrator import AnalysisContext
from performa.core.ledger import SeriesMetadata
from performa.core.primitives import (
    CalculationPhase,
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    FinancingSubcategoryEnum,
    GlobalSettings,
    Timeline,
    TransactionPurpose,
)
from performa.deal.analysis import (
    CashFlowEngine,
    DebtAnalyzer,
    PartnershipAnalyzer,
    ValuationEngine,
)
from performa.deal.results import (
    DealAnalysisResult,
    DealMetricsResult,
    DealSummary,
    FinancingAnalysisResult,
    FundingCascadeDetails,
    InterestCompoundingDetails,
    LeveredCashFlowResult,
    PartnerDistributionResult,
    UnleveredAnalysisResult,
)

if TYPE_CHECKING:
    from performa.analysis.results import AssetAnalysisResult
    from performa.core.ledger import LedgerBuilder
    from performa.deal.deal import Deal

logger = logging.getLogger(__name__)


@dataclass
class DealContext:
    """
    A mutable container for the complete state of a deal-level analysis run.

    This is the deal-level parallel to AnalysisContext, designed specifically
    for deal-level models like debt facilities, valuations, fees, and partnerships.
    Unlike AnalysisContext which focuses on asset-level operations (leases, expenses),
    DealContext provides deal-centric data and eliminates the semantic mismatch
    that was causing frozen model mutations and defensive programming.

    ARCHITECTURE - DUAL CONTEXT PATTERN:
    - AnalysisContext: For asset-level models (leases, expenses, recovery)
    - DealContext: For deal-level models (debt, valuation, fees, partnership)

    This separation provides:
    - Clean interfaces without defensive hasattr() checks
    - No frozen model mutations (object.__setattr__ hacks)
    - Clear semantic meaning for each model type
    - Proper data access patterns for each domain

    Key Design Principles:
    - Single source of truth via ledger_builder (Pass-the-Builder pattern)
    - Deal-centric data access (full Deal object, not just asset)
    - Deal-level metrics readily available (property value, NOI, project costs)
    - Clean separation from asset-specific data (no recovery states, lease contexts)

    Example:
        ```python
        # Create context for deal-level analysis
        context = DealContext(
            timeline=timeline,
            settings=settings,
            ledger_builder=builder,
            deal=deal,
            property_value=valuation_series,
            noi_series=noi_series,
            project_costs=total_development_cost
        )

        # Use with deal-level models
        debt_service = facility.compute_cf(context)  # No more hacks!
        disposition_value = reversion.calculate(context)
        ```
    """

    # --- Configuration (Set at creation) ---
    timeline: "Timeline"
    settings: "GlobalSettings"
    ledger_builder: "LedgerBuilder"
    deal: "Deal"

    # --- Deal-Level Metrics (Optional - populated as needed) ---
    property_value: Optional[pd.Series] = None
    noi_series: Optional[pd.Series] = None
    project_costs: Optional[float] = None

    def __post_init__(self):
        """Validate required fields after initialization."""
        # Validate that ledger_builder is provided (critical for Pass-the-Builder pattern)
        if self.ledger_builder is None:
            raise ValueError(
                "DealContext requires a ledger_builder instance. "
                "This enforces the Pass-the-Builder pattern where a single LedgerBuilder "
                "is created at the API level and passed through all deal analysis components."
            )

        # Validate that deal is provided
        if self.deal is None:
            raise ValueError(
                "DealContext requires a deal instance for deal-level operations."
            )

    @classmethod
    def from_analysis_context(
        cls,
        analysis_context: AnalysisContext,
        deal: "Deal",
        property_value: Optional[pd.Series] = None,
        noi_series: Optional[pd.Series] = None,
        project_costs: Optional[float] = None,
    ) -> "DealContext":
        """
        Factory method to create DealContext from existing AnalysisContext.

        This provides a migration path during the transition period and enables
        creating deal contexts from asset analysis results.

        Args:
            analysis_context: Existing AnalysisContext from asset analysis
            deal: Deal object for deal-level operations
            property_value: Optional property value series for valuations
            noi_series: Optional NOI series for debt analysis
            project_costs: Optional total project costs for development deals

        Returns:
            New DealContext with deal-specific configuration

        Example:
            ```python
            # Convert asset context to deal context
            deal_context = DealContext.from_analysis_context(
                analysis_context=asset_context,
                deal=deal,
                noi_series=noi_from_asset_analysis,
                property_value=property_value_series
            )

            # Now use with deal models
            debt_service = facility.compute_cf(deal_context)
            ```
        """
        return cls(
            timeline=analysis_context.timeline,
            settings=analysis_context.settings,
            ledger_builder=analysis_context.ledger_builder,
            deal=deal,
            property_value=property_value,
            noi_series=noi_series,
            project_costs=project_costs,
        )


@dataclass
class DealCalculator:
    """
    Service class that orchestrates the complete deal analysis workflow.

    This class encapsulates the multi-step analysis logic as internal state,
    providing a clean, maintainable structure for complex deal analysis.

    The analysis proceeds through distinct sequential steps:
    1. Unlevered asset analysis using the core analysis engine
    2. Financing integration and debt service calculations
    3. Performance metrics calculation (DSCR time series)
    4. Levered cash flow calculation with funding cascade
    5. Partner distribution calculations (equity waterfall)
    6. Deal-level performance metrics calculation

    Architecture:
    - Uses dataclass for runtime service (not a data model)
    - Maintains mutable typed state during analysis using Pydantic models
    - Returns strongly-typed result models
    - Delegates to specialist services for complex logic

    Example:
        ```python
        calculator = DealCalculator(deal, timeline, settings)
        results = calculator.run()

        # Access strongly-typed results
        print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
        print(f"Partner count: {len(results.partner_distributions.partner_results)}")
        ```
    """

    # Input Parameters
    deal: Deal
    timeline: Timeline
    settings: GlobalSettings
    asset_analysis: Optional["AssetAnalysisResult"] = (
        None  # Pre-computed asset analysis to reuse
    )

    # Typed Result State (populated during analysis)
    deal_summary: DealSummary = field(
        init=False, repr=False, default_factory=DealSummary
    )
    unlevered_analysis: UnleveredAnalysisResult = field(
        init=False, repr=False, default_factory=UnleveredAnalysisResult
    )
    financing_analysis: FinancingAnalysisResult = field(
        init=False, repr=False, default_factory=FinancingAnalysisResult
    )
    levered_cash_flows: LeveredCashFlowResult = field(
        init=False, repr=False, default_factory=LeveredCashFlowResult
    )
    partner_distributions: PartnerDistributionResult = field(
        init=False, repr=False, default=None
    )
    deal_metrics: DealMetricsResult = field(
        init=False, repr=False, default_factory=DealMetricsResult
    )

    def run(self, ledger_builder: "LedgerBuilder") -> DealAnalysisResult:
        """
        Execute the complete deal analysis workflow by delegating to specialist services.

        Args:
            ledger_builder: The analysis ledger builder (Pass-the-Builder pattern).
                Must be the same instance used throughout the analysis.

        Returns:
            Strongly-typed DealAnalysisResult containing all analysis components

        Raises:
            ValueError: If deal structure is invalid
            RuntimeError: If analysis fails during execution
        """
        try:
            # Initialize deal summary
            self._populate_deal_summary()

            # === PASS 1: Asset Analysis (Ledger-Based) ===
            if self.asset_analysis is not None:
                # Use pre-computed asset analysis (Pass-the-Builder pattern)
                # The ledger_builder already contains asset transactions
                asset_result = self.asset_analysis
            else:
                # Run fresh asset analysis with provided ledger builder
                asset_result = run(
                    model=self.deal.asset,
                    timeline=self.timeline,
                    settings=self.settings,
                    ledger_builder=ledger_builder,
                )

            # Continue with same builder (pass-the-builder pattern)
            # ledger_builder is the same instance used by asset analysis

            # Create backward compatibility wrapper using ledger data
            self.unlevered_analysis = UnleveredAnalysisResult(
                scenario=asset_result.scenario,
                cash_flows=asset_result.summary_df,  # Use actual cash flow summary
                models=asset_result.models if hasattr(asset_result, "models") else [],
            )

            # === ORCHESTRATION STATE PATTERN ===
            # Calculate initial project costs from deal structure for financing sizing
            initial_project_costs = 0.0

            # Add acquisition costs if available
            if self.deal.acquisition:
                # Get acquisition value (can be scalar or Series)
                if isinstance(self.deal.acquisition.value, (int, float)):
                    acquisition_value = self.deal.acquisition.value
                elif hasattr(self.deal.acquisition.value, "sum"):
                    acquisition_value = self.deal.acquisition.value.sum()
                else:
                    acquisition_value = 0.0

                initial_project_costs += acquisition_value
                # Add closing costs (percentage of acquisition value)
                if acquisition_value > 0 and self.deal.acquisition.closing_costs_rate:
                    initial_project_costs += (
                        acquisition_value * self.deal.acquisition.closing_costs_rate
                    )

            # Add renovation/development costs if available
            if hasattr(self.deal.asset, "renovation_budget"):
                initial_project_costs += self.deal.asset.renovation_budget or 0.0
            elif hasattr(self.deal.asset, "construction_plan"):
                if hasattr(self.deal.asset.construction_plan, "total_cost"):
                    initial_project_costs += (
                        self.deal.asset.construction_plan.total_cost or 0.0
                    )

            # Create DealContext for deal-level orchestration (Phase 5 implementation)
            # This will be progressively populated with results from each phase
            deal_context = DealContext(
                timeline=self.timeline,
                settings=self.settings,
                ledger_builder=ledger_builder,
                deal=self.deal,
                # Pass initial project costs for construction financing sizing
                project_costs=initial_project_costs
                if initial_project_costs > 0
                else None,
                # noi_series, property_value will be populated progressively
            )

            # === PASS 2: Add Deal Transactions to Ledger ===
            # Add acquisition costs BEFORE funding cascade so they're included in uses
            self._add_acquisition_records(ledger_builder)

            # === PASS 3: Valuation Analysis (needed for debt analysis) ===
            valuation_engine = ValuationEngine(
                deal=self.deal, timeline=self.timeline, settings=self.settings
            )

            property_value_series = valuation_engine.extract_property_value_series(
                self.unlevered_analysis
            )
            noi_series = valuation_engine.extract_noi_series(self.unlevered_analysis)
            disposition_proceeds = valuation_engine.calculate_disposition_proceeds(
                ledger_builder, self.unlevered_analysis
            )

            # === ORCHESTRATION STATE PATTERN ===
            # Populate DealContext with valuation results (Phase 5 implementation)
            deal_context.property_value = property_value_series
            deal_context.noi_series = noi_series

            # Calculate and populate project costs for debt analysis
            try:
                current_ledger = ledger_builder.get_current_ledger()
                if not current_ledger.empty:
                    # Sum all capital/development costs as project costs
                    try:
                        capital_mask = (
                            current_ledger["category"] == CashFlowCategoryEnum.CAPITAL
                        )
                        capital_txns = current_ledger[capital_mask]
                    except:
                        # Fallback: String contains match
                        capital_mask = (
                            current_ledger["category"]
                            .astype(str)
                            .str.contains("CAPITAL", case=False, na=False)
                        )
                        capital_txns = current_ledger[capital_mask]

                    deal_context.project_costs = abs(
                        capital_txns["amount"].sum()
                    )  # Use absolute value for costs
            except Exception as e:
                logger.warning(f"Failed to calculate project costs: {e}")
                deal_context.project_costs = None

            # === PASS 4: Debt Analysis (BEFORE funding cascade) ===
            debt_analyzer = DebtAnalyzer(
                deal=self.deal, timeline=self.timeline, settings=self.settings
            )
            self.financing_analysis = debt_analyzer.analyze_financing_structure(
                property_value_series=property_value_series,
                noi_series=noi_series,
                unlevered_analysis=self.unlevered_analysis,
                ledger_builder=ledger_builder,
                deal_context=deal_context,  # Pass DealContext for proper debt facility processing
            )

            # === PASS 4 (continued): Add Remaining Deal Transactions to Ledger ===
            # NOTE: Financing records are handled by DebtAnalyzer._process_facilities()
            self._add_partnership_records(ledger_builder)

            # === PASS 5: Create Funding Cascade Summary ===
            # Create funding cascade details functionally (no mutation)
            funding_cascade_details = self._create_funding_cascade_summary(
                ledger_builder
            )

            # === PASS 6: Cash Flow Analysis ===
            # CashFlowEngine handles the actual funding cascade mechanics (period-by-period funding)
            cash_flow_engine = CashFlowEngine(
                deal=self.deal, timeline=self.timeline, settings=self.settings
            )
            self.levered_cash_flows = cash_flow_engine.calculate_levered_cash_flows(
                unlevered_analysis=self.unlevered_analysis,
                financing_analysis=self.financing_analysis,
                ledger_builder=ledger_builder,
                disposition_proceeds=disposition_proceeds,
                funding_cascade_details=funding_cascade_details,  # Pass details to engine
            )

            # === PASS 5: Partnership Analysis ===
            partnership_analyzer = PartnershipAnalyzer(
                deal=self.deal, timeline=self.timeline, settings=self.settings
            )
            self.partner_distributions = partnership_analyzer.calculate_partner_distributions(
                levered_cash_flows=self.levered_cash_flows.levered_cash_flows,
                ledger_builder=ledger_builder,  # Pass ledger builder for distribution recording
            )

            # === PASS 6: Deal Metrics ===
            self._calculate_deal_metrics()

            # Return the final typed result with ledger-based asset analysis
            return DealAnalysisResult(
                deal_summary=self.deal_summary,
                asset_analysis=asset_result,  # NEW: Ledger-based result
                unlevered_analysis=self.unlevered_analysis,  # DEPRECATED: Backward compatibility
                financing_analysis=self.financing_analysis
                if self.financing_analysis.has_financing
                else None,
                levered_cash_flows=self.levered_cash_flows,
                partner_distributions=self.partner_distributions,
                deal_metrics=self.deal_metrics,
            )

        except Exception as e:
            raise RuntimeError(f"Deal analysis failed: {str(e)}") from e

    # === FUNDING CASCADE ORCHESTRATION ===
    # These methods orchestrate the institutional funding cascade for development deals.

    def _create_funding_cascade_summary(
        self, builder: "LedgerBuilder"
    ) -> Optional["FundingCascadeDetails"]:
        """
        Create a static funding cascade summary from ledger for reporting purposes.

        This method runs AFTER CashFlowEngine has executed the actual funding cascade
        mechanics. It queries the final ledger state to create a summary report showing:
        - Total Uses breakdown by category
        - Funding sources (equity vs debt)
        - Key metrics for reporting

        Note: The actual funding mechanics (period-by-period funding with interest
        compounding) are handled by CashFlowEngine._execute_funding_cascade().
        """
        # Get current ledger with all asset-level transactions
        ledger = builder.get_current_ledger()
        logger.debug(
            f"Funding cascade: Processing ledger with {len(ledger)} transactions"
        )

        if ledger.empty:
            logger.warning(
                "Funding cascade: Ledger is empty, creating zero funding cascade"
            )
            return self._create_zero_funding_cascade()

        # Calculate total uses from ledger (all negative amounts = outflows/costs)
        uses_by_period = self._calculate_uses_from_ledger(ledger)
        total_uses = uses_by_period.sum()

        logger.debug(f"Funding cascade: Total uses calculated as ${total_uses:,.2f}")

        if total_uses <= 0:
            logger.warning(
                "Funding cascade: No uses found, creating zero funding cascade"
            )
            return self._create_zero_funding_cascade()

        # Create uses breakdown DataFrame from actual ledger transactions
        uses_breakdown = self._create_uses_breakdown_from_ledger(ledger)

        # Create and return funding cascade details
        funding_cascade_details = self._create_funding_cascade_details(
            uses_breakdown, total_uses
        )

        logger.debug("Funding cascade orchestration completed")
        return funding_cascade_details

    def _calculate_uses_from_ledger(self, ledger: pd.DataFrame) -> pd.Series:
        """Calculate period-by-period uses (outflows) from ledger transactions."""

        # Filter for capital use transactions (costs/outflows)
        # Use flow_purpose instead of amount sign for correct classification
        capital_uses = ledger[
            ledger["flow_purpose"] == TransactionPurpose.CAPITAL_USE.value
        ].copy()

        if capital_uses.empty:
            return pd.Series(0.0, index=self.timeline.period_index)

        # Capital use amounts are negative (outflows), make them positive for uses calculation
        # Take absolute value first, then group by period and sum (all amounts are positive uses)
        capital_uses["amount"] = capital_uses["amount"].abs()
        uses_by_period = capital_uses.groupby("date")["amount"].sum()

        # Convert date index to Period index to match timeline
        if len(uses_by_period) > 0:
            if hasattr(uses_by_period.index[0], "to_period"):
                # Timestamp index
                uses_by_period.index = uses_by_period.index.to_period("M")
            else:
                # datetime.date index - convert to Period
                uses_by_period.index = pd.PeriodIndex([
                    pd.Period(date, "M") for date in uses_by_period.index
                ])

        # Reindex to full timeline
        uses_series = uses_by_period.reindex(self.timeline.period_index, fill_value=0.0)

        return uses_series

    def _create_uses_breakdown_from_ledger(self, ledger: pd.DataFrame) -> pd.DataFrame:
        """Create detailed uses breakdown from ledger transactions by category."""

        # Initialize breakdown DataFrame
        uses_df = pd.DataFrame(
            0.0,
            index=self.timeline.period_index,
            columns=[
                "Acquisition Costs",
                "Construction Costs",
                "Other Project Costs",
                "Total Uses",
            ],
        )

        if ledger.empty:
            logger.warning("Uses breakdown: Ledger is empty")
            return uses_df

        logger.debug(f"Uses breakdown: Ledger has {len(ledger)} transactions")
        logger.debug(f"Flow purposes in ledger: {ledger['flow_purpose'].unique()}")

        # Filter for capital use transactions
        capital_uses = ledger[
            ledger["flow_purpose"] == TransactionPurpose.CAPITAL_USE.value
        ].copy()

        if capital_uses.empty:
            logger.warning("Uses breakdown: No CAPITAL_USE transactions found")
            logger.debug(
                f"Available transactions by flow_purpose: {ledger['flow_purpose'].value_counts()}"
            )
            return uses_df

        logger.debug(
            f"Uses breakdown: Found {len(capital_uses)} CAPITAL_USE transactions"
        )

        # Group by date and subcategory to break down uses
        for _, transaction in capital_uses.iterrows():
            date = transaction["date"]
            amount = abs(transaction["amount"])  # Ensure positive
            subcategory = transaction.get("subcategory", "")

            logger.debug(
                f"Processing transaction: date={date}, amount={amount}, subcategory='{subcategory}'"
            )

            # Convert date to period for indexing
            if hasattr(date, "to_period"):
                period = date.to_period("M")
            elif hasattr(date, "date"):
                period = pd.Period(date.date(), freq="M")
            else:
                period = pd.Period(date, freq="M")

            # Skip if period not in timeline
            if period not in uses_df.index:
                logger.warning(f"Period {period} not in timeline, skipping")
                continue

            # Categorize by subcategory
            # Handle both enum string representation and enum value
            if (
                subcategory == CapitalSubcategoryEnum.PURCHASE_PRICE.value
                or subcategory == str(CapitalSubcategoryEnum.PURCHASE_PRICE)
            ):
                logger.debug(
                    f"Categorizing as Acquisition Costs: {amount} in period {period}"
                )
                old_val = uses_df.loc[period, "Acquisition Costs"]
                uses_df.loc[period, "Acquisition Costs"] += amount
                new_val = uses_df.loc[period, "Acquisition Costs"]
                logger.debug(f"Acquisition Costs updated: {old_val} -> {new_val}")
            elif (
                subcategory == CapitalSubcategoryEnum.CLOSING_COSTS.value
                or subcategory == str(CapitalSubcategoryEnum.CLOSING_COSTS)
            ):
                logger.debug(
                    f"Categorizing closing costs as Acquisition Costs: {amount} in period {period}"
                )
                old_val = uses_df.loc[period, "Acquisition Costs"]
                uses_df.loc[period, "Acquisition Costs"] += amount
                new_val = uses_df.loc[period, "Acquisition Costs"]
                logger.debug(f"Acquisition Costs updated: {old_val} -> {new_val}")
            elif subcategory in [
                CapitalSubcategoryEnum.HARD_COSTS.value,
                CapitalSubcategoryEnum.SOFT_COSTS.value,
                CapitalSubcategoryEnum.SITE_WORK.value,
            ]:
                logger.debug(f"Categorizing as Construction Costs: {amount}")
                uses_df.loc[period, "Construction Costs"] += amount
            else:
                logger.debug(
                    f"Categorizing as Other Project Costs: {amount} (subcategory: {subcategory})"
                )
                uses_df.loc[period, "Other Project Costs"] += amount

            # Add to total uses
            uses_df.loc[period, "Total Uses"] += amount

        logger.debug(f"Final uses_df summary:")
        logger.debug(f"  Acquisition Costs total: {uses_df['Acquisition Costs'].sum()}")
        logger.debug(f"  Total Uses total: {uses_df['Total Uses'].sum()}")

        return uses_df

    def _create_funding_cascade_details(
        self, uses_breakdown: pd.DataFrame, total_uses: float
    ) -> "FundingCascadeDetails":
        """Create funding cascade details based on calculated uses."""

        # For all-equity deals, equity funds 100% of uses
        if not self.deal.financing:
            equity_target = total_uses
            ltc_ratio = 0.0
        else:
            # Get LTC ratio from construction facilities
            ltc_ratio = 0.0
            if self.deal.financing.facilities:
                for facility in self.deal.financing.facilities:
                    if hasattr(facility, "max_ltc"):
                        ltc_ratio = max(ltc_ratio, float(facility.max_ltc))
                    elif hasattr(facility, "tranches") and facility.tranches:
                        # For construction facilities with tranches, use max LTC threshold
                        for tranche in facility.tranches:
                            ltc_ratio = max(ltc_ratio, float(tranche.ltc_threshold))

            equity_target = total_uses * (1 - ltc_ratio)

        # Calculate equity contributions by period (proportional to uses)
        total_uses_by_period = uses_breakdown["Total Uses"]
        if total_uses > 0:
            equity_contributions = total_uses_by_period * (equity_target / total_uses)
        else:
            equity_contributions = pd.Series(0.0, index=self.timeline.period_index)

        # Create interest compounding details (placeholder for now)
        # FIXME: placeholder!
        interest_details = InterestCompoundingDetails(
            base_uses=total_uses_by_period,
            compounded_interest=pd.Series(0.0, index=total_uses_by_period.index),
            total_uses_with_interest=total_uses_by_period,
            equity_target=equity_target,
            equity_funded=equity_contributions.sum(),
            debt_funded=total_uses - equity_target,
            funding_gap=0.0,
            total_project_cost=total_uses,
        )

        # Create and return funding cascade details
        return FundingCascadeDetails(
            uses_breakdown=uses_breakdown,
            equity_target=equity_target,
            equity_contributed_cumulative=equity_contributions.cumsum(),
            interest_compounding_details=interest_details,
        )

    def _create_zero_funding_cascade(self) -> "FundingCascadeDetails":
        """Create zero funding cascade for deals with no uses."""

        zero_series = pd.Series(0.0, index=self.timeline.period_index)

        uses_breakdown = pd.DataFrame({
            "Acquisition Costs": zero_series,
            "Construction Costs": zero_series,
            "Other Project Costs": zero_series,
            "Total Uses": zero_series,
        })

        interest_details = InterestCompoundingDetails(
            base_uses=zero_series,
            compounded_interest=zero_series,
            total_uses_with_interest=zero_series,
            equity_target=0.0,
            equity_funded=0.0,
            debt_funded=0.0,
            funding_gap=0.0,
            total_project_cost=0.0,
        )

        return FundingCascadeDetails(
            uses_breakdown=uses_breakdown,
            equity_target=0.0,
            equity_contributed_cumulative=zero_series,
            interest_compounding_details=interest_details,
        )

    def _populate_deal_summary(self) -> None:
        """Initialize deal summary with basic deal characteristics."""
        self.deal_summary.deal_name = self.deal.name
        self.deal_summary.deal_type = self.deal.deal_type
        self.deal_summary.asset_type = self.deal.asset.property_type.value
        self.deal_summary.is_development = self.deal.is_development_deal
        self.deal_summary.has_financing = self.deal.financing is not None
        self.deal_summary.has_disposition = self.deal.exit_valuation is not None

    def _calculate_deal_metrics(self) -> None:
        """
        Calculate deal-level performance metrics.

        This calculates key metrics like IRR, equity multiple, and other
        deal-level performance indicators from the levered cash flows.
        """
        # Get levered cash flows
        cash_flows = self.levered_cash_flows.levered_cash_flows
        if cash_flows is None or len(cash_flows) == 0:
            return

        try:
            # Calculate basic metrics
            negative_flows = cash_flows[cash_flows < 0]
            positive_flows = cash_flows[cash_flows > 0]

            total_equity_invested = abs(negative_flows.sum())
            total_equity_returned = positive_flows.sum()
            net_profit = cash_flows.sum()

            # Calculate hold period
            hold_period_years = len(self.timeline.period_index) / 12.0

            # Calculate equity multiple
            equity_multiple = None
            if total_equity_invested > 0:
                equity_multiple = total_equity_returned / total_equity_invested

            # Calculate IRR using PyXIRR
            irr = None
            if len(cash_flows) > 1 and total_equity_invested > 0:
                try:
                    dates = [
                        period.to_timestamp().date() for period in cash_flows.index
                    ]
                    irr = xirr(dates, cash_flows.values)
                    if irr is not None:
                        irr = float(irr)
                except Exception:
                    pass

            # Calculate total return
            total_return = None
            if total_equity_invested > 0:
                total_return = (
                    total_equity_returned - total_equity_invested
                ) / total_equity_invested

            # Calculate annual yield
            annual_yield = None
            if total_return is not None and hold_period_years > 0:
                annual_yield = total_return / hold_period_years

            # Calculate cash-on-cash return (first year)
            cash_on_cash = None
            if total_equity_invested > 0 and len(cash_flows) > 12:
                first_year_distributions = positive_flows[:12].sum()
                cash_on_cash = first_year_distributions / total_equity_invested

            # Update metrics using dot notation
            self.deal_metrics.irr = irr
            self.deal_metrics.equity_multiple = equity_multiple
            self.deal_metrics.total_return = total_return
            self.deal_metrics.annual_yield = annual_yield
            self.deal_metrics.cash_on_cash = cash_on_cash
            self.deal_metrics.total_equity_invested = total_equity_invested
            self.deal_metrics.total_equity_returned = total_equity_returned
            self.deal_metrics.net_profit = net_profit
            self.deal_metrics.hold_period_years = hold_period_years

        except Exception:
            # Fallback: Return empty metrics if calculation fails
            # FIXME: Consider logging this error in production
            pass

    # === TRANSACTION INTEGRATION METHODS ===
    # These methods flow deal-level transactions through the ledger builder

    def _add_acquisition_records(self, builder: "LedgerBuilder") -> None:
        """Add acquisition and fee transactions to ledger."""
        if not self.deal.acquisition:
            logger.debug("No acquisition terms to add to ledger")
            return

        try:
            acquisition_date = self.deal.acquisition.acquisition_date
            purchase_price = self.deal.acquisition.value
            closing_costs_rate = self.deal.acquisition.closing_costs_rate
        except AttributeError as e:
            logger.error(f"Failed to access acquisition attributes: {e}")
            return

        # Purchase price (negative amount representing outflow/use)
        acquisition_period = pd.Period(acquisition_date, freq="M")
        purchase_price_series = pd.Series(
            [-purchase_price],
            index=pd.PeriodIndex([acquisition_period], freq="M"),
            name="Purchase Price",
        )

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.CAPITAL,
            subcategory=CapitalSubcategoryEnum.PURCHASE_PRICE,
            item_name="Property Acquisition",
            source_id=str(self.deal.uid),
            asset_id=self.deal.asset.uid,
            pass_num=CalculationPhase.ACQUISITION.value,  # Acquisition phase
        )
        builder.add_series(purchase_price_series, metadata)
        logger.debug(f"Added acquisition purchase price: ${purchase_price:,.0f}")

        # Closing costs (negative amount representing outflow/use)
        closing_costs = purchase_price * closing_costs_rate
        closing_costs_series = pd.Series(
            [-1 * closing_costs],
            index=pd.PeriodIndex([acquisition_period], freq="M"),
            name="Closing Costs",
        )

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.CAPITAL,
            subcategory=CapitalSubcategoryEnum.CLOSING_COSTS,
            item_name="Acquisition Closing Costs",
            source_id=str(self.deal.uid),
            asset_id=self.deal.asset.uid,
            pass_num=CalculationPhase.ACQUISITION.value,  # Acquisition phase
        )
        builder.add_series(closing_costs_series, metadata)
        logger.debug(f"Added acquisition closing costs: ${closing_costs:,.0f}")

        # Add deal fees if they exist
        if hasattr(self.deal, "deal_fees") and self.deal.deal_fees:
            logger.debug(f"Adding {len(self.deal.deal_fees)} deal fees")
            for fee in self.deal.deal_fees:
                try:
                    fee_cf = fee.compute_cf(self.timeline)
                    metadata = SeriesMetadata(
                        category=CashFlowCategoryEnum.CAPITAL,
                        subcategory=CapitalSubcategoryEnum.OTHER,  # Use proper enum for fees
                        item_name=f"Fee - {getattr(fee, 'name', 'Unknown')}",
                        source_id=str(getattr(fee, "uid", fee)),
                        asset_id=self.deal.asset.uid,
                    )
                    builder.add_series(fee_cf, metadata)
                    logger.debug(f"Added deal fee: {getattr(fee, 'name', 'Unknown')}")
                except Exception as e:
                    logger.warning(f"Failed to add deal fee: {e}")
        else:
            logger.debug("No deal fees to add")

    def _add_partnership_records(self, builder: "LedgerBuilder") -> None:
        """Add partnership transactions to ledger."""
        if not self.deal.equity_partners:
            logger.debug("No partnership to add to ledger")
            return

        # Calculate required equity (purchase price + closing costs - loan proceeds)
        try:
            total_cost = self.deal.acquisition.value * (
                1 + self.deal.acquisition.closing_costs_rate
            )
            loan_amount = (
                self.deal.acquisition.value * self.deal.financing.ltv_ratio
                if self.deal.financing
                else 0
            )
            required_equity = total_cost - loan_amount
            acquisition_date = self.deal.acquisition.acquisition_date
        except AttributeError as e:
            logger.error(f"Failed to access partnership attributes: {e}")
            return

        # ARCHITECTURAL CONSISTENCY: Use PeriodIndex like all other models
        acquisition_period = pd.Period(acquisition_date, freq="M")
        equity_contribution_series = pd.Series(
            [required_equity],
            index=pd.PeriodIndex([acquisition_period], freq="M"),
            name="Partner Capital Contributions",
        )

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,  # Partnership contributions are financing
            subcategory=FinancingSubcategoryEnum.EQUITY_CONTRIBUTION,  # Use proper enum
            item_name="Initial Equity Investment",
            source_id=str(self.deal.uid),
            asset_id=self.deal.asset.uid,
            pass_num=CalculationPhase.PARTNERSHIP.value,  # Partnership phase
        )
        builder.add_series(equity_contribution_series, metadata)
        logger.debug(f"Added equity contribution: ${required_equity:,.0f}")
        # TODO: Add partnership flows after they're calculated
        pass
