# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Cash Flow Engine Specialist

This module provides the CashFlowEngine service that handles institutional-grade funding cascade
and levered cash flow calculations with interest reserves and
sophisticated equity/debt coordination mechanisms.

The CashFlowEngine represents the core financial engineering component of the deal analysis framework,
implementing the complex funding cascade logic that determines how project uses are funded and
how cash flows are distributed to equity investors.

Key capabilities:
- **Institutional Funding Cascade**: Period-by-period funding logic with equity-first, debt-second priority
- **Multi-Tranche Debt Funding**: Sophisticated LTC threshold-based debt draw management
- **Interest Compounding**: Comprehensive interest calculations with cash interest
- **Interest Reserve Management**: Institutional-grade interest reserve capacity and utilization
- **Equity Coordination**: Dynamic equity target calculation with funding gap analysis
- **Cash Flow Assembly**: Complete levered cash flow assembly with component tracking

The service implements institutional standards used in commercial real estate development financing,
including the complex funding cascade logic that determines:
- How equity and debt are sequenced during the funding process
- When and how interest compounds into additional funding requirements
- How interest reserves are utilized vs. cash interest payments
- How funding gaps are identified and managed

Funding Cascade Logic:
    The engine implements a sophisticated period-by-period funding cascade:

    1. **Calculate Period Uses**: Acquisition, construction, fees, and other project costs
    2. **Initialize Funding State**: Set up equity targets and debt tranche tracking
    3. **Iterative Funding Loop**: For each period:
       - Calculate interest on previous period's outstanding debt balance
       - Add interest to current period's uses (if cash interest) or reserve (if reserve-funded)
       - Fund period uses with equity-first, then debt-second priority
       - Update outstanding balances and cumulative funding tracking
    4. **Assemble Results**: Create comprehensive cash flow components and summaries

Example:
    ```python
    from performa.deal.analysis import CashFlowEngine

    # Create cash flow engine
    engine = CashFlowEngine(deal, timeline, settings)

    # Calculate levered cash flows through funding cascade
    levered_results = engine.calculate_levered_cash_flows(
        unlevered_analysis=unlevered_analysis,
        financing_analysis=financing_analysis,
        disposition_proceeds=disposition_proceeds
    )

    # Access comprehensive results
    cascade_details = levered_results.funding_cascade_details
    print(f"Total project cost: ${cascade_details.interest_compounding_details.total_project_cost:,.0f}")
    print(f"Equity funded: ${cascade_details.interest_compounding_details.equity_funded:,.0f}")
    print(f"Debt funded: ${cascade_details.interest_compounding_details.debt_funded:,.0f}")
    ```

Architecture:
    - Uses dataclass pattern for runtime service state management
    - Implements institutional-grade funding cascade algorithms
    - Provides comprehensive component tracking and audit trails
    - Supports complex multi-tranche debt structures
    - Integrates with broader deal analysis workflow through typed interfaces

Institutional Standards:
    - Follows commercial real estate development financing practices
    - Implements funding cascade logic used by institutional lenders
    - Provides comprehensive interest calculations per institutional standards
    - Supports interest reserve management used in institutional deals
    - Maintains audit trails required for institutional financing
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

import pandas as pd

from performa.analysis import AnalysisContext
from performa.core.ledger import SeriesMetadata
from performa.core.primitives import (
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
    FinancingSubcategoryEnum,
    TransactionPurpose,
    UnleveredAggregateLineKey,
)
from performa.core.primitives.enums import (
    CalculationPhase,
    CapitalSubcategoryEnum,
)
from performa.deal.results import (
    CashFlowComponents,
    CashFlowSummary,
    FinancingAnalysisResult,
    FundingCascadeDetails,
    InterestCompoundingDetails,
    InterestReserveDetails,
    LeveredCashFlowResult,
    UnleveredAnalysisResult,
)

if TYPE_CHECKING:
    from performa.core.ledger import Ledger
    from performa.core.primitives import GlobalSettings, Timeline
    from performa.deal.deal import Deal


logger = logging.getLogger(__name__)


@dataclass
class CashFlowEngine:
    """
    Specialist service for calculating levered cash flows through institutional-grade funding cascade.

    This service represents the core financial engineering component that implements the sophisticated
    funding cascade logic used in commercial real estate development financing. It handles the complex
    sequencing of equity and debt funding, interest calculations, and cash flow assembly.

    The CashFlowEngine implements institutional standards for funding cascade logic, including:
    - Period-by-period iterative funding with proper state management
    - Dynamic equity target calculation based on total project costs
    - Multi-tranche debt funding with LTC threshold enforcement
    - Comprehensive interest handling (cash vs. reserve-funded)
    - Detailed component tracking for audit and analysis purposes

    Key features:
    - **Institutional Funding Cascade**: Implements the standard equity-first, debt-second funding priority
    - **Multi-Tranche Debt Support**: Handles complex debt structures with multiple tranches and LTC thresholds
    - **Interest Compounding**: Sophisticated interest calculations with cash and reserve options
    - **Dynamic Equity Targets**: Calculates equity targets that adjust as interest compounds
    - **Component Tracking**: Maintains detailed audit trails of all funding components
    - **Gap Analysis**: Identifies and reports funding gaps for risk management

    The funding cascade process:
    1. Calculate period-by-period uses (acquisition, construction, fees)
    2. Initialize funding state with equity targets and debt tranche tracking
    3. Execute iterative funding loop with interest compounding
    4. Assemble comprehensive levered cash flow results

    Attributes:
        deal: The deal containing asset, financing, and partnership structures
        timeline: Analysis timeline for funding cascade calculations
        settings: Global settings for cash flow configuration
        levered_cash_flows: Runtime state populated during analysis (internal use)

    Example:
        ```python
        # Create cash flow engine
        engine = CashFlowEngine(deal, timeline, settings)

        # Execute funding cascade
        results = engine.calculate_levered_cash_flows(
            unlevered_analysis=unlevered_analysis,
            financing_analysis=financing_analysis,
            disposition_proceeds=disposition_proceeds
        )

        # Analyze funding cascade results
        cascade_details = results.funding_cascade_details
        print(f"Equity target: ${cascade_details.equity_target:,.0f}")
        print(f"Debt funded: ${cascade_details.interest_compounding_details.debt_funded:,.0f}")
        print(f"Funding gap: ${cascade_details.interest_compounding_details.funding_gap:,.0f}")

        # Access component cash flows
        components = results.cash_flow_components
        print(f"Total uses: ${components.total_uses.sum():,.0f}")
        print(f"Interest expense: ${components.interest_expense.sum():,.0f}")
        ```
    """

    # Input parameters
    deal: Deal
    timeline: Timeline
    settings: GlobalSettings

    # Runtime state (populated during analysis)
    levered_cash_flows: LeveredCashFlowResult = field(
        init=False, repr=False, default_factory=LeveredCashFlowResult
    )

    def calculate_levered_cash_flows(
        self,
        unlevered_analysis: UnleveredAnalysisResult,
        financing_analysis: FinancingAnalysisResult,
        ledger: "Ledger",
        disposition_proceeds: Optional[pd.Series] = None,
        funding_cascade_details: Optional["FundingCascadeDetails"] = None,
    ) -> LeveredCashFlowResult:
        """
        Calculate levered cash flows through institutional-grade funding cascade.

        This method executes the complete funding cascade process to determine
        how project uses are funded and calculates the resulting levered cash flows.

        Process includes:
        1. Period-by-period Uses calculation (acquisition, construction, fees)
        2. Equity-first funding up to target LTC thresholds
        3. Debt-second funding with proper LTC constraints
        4. Interest compounding with reserve options
        5. Final levered cash flow assembly with detailed component tracking

        Args:
            unlevered_analysis: Results from unlevered asset analysis
            financing_analysis: Results from debt analysis
            ledger: The analysis ledger (Pass-the-Builder pattern).
                Must be the same instance used throughout the analysis.
            disposition_proceeds: Disposition proceeds from valuation analysis (optional)

        Returns:
            LeveredCashFlowResult containing all cash flow components and analysis
        """
        # === Step 1: Calculate Period Uses ===
        # Use ledger-based uses calculation (single source of truth)
        # ledger contains the asset-level transactions from prior analysis
        base_uses = self._calculate_ledger_based_uses(ledger)

        # Note: uses_breakdown is created by DealCalculator during funding cascade orchestration
        # CashFlowEngine focuses on the funding mechanics, not the categorization

        # === Step 2: Initialize Funding Components ===
        funding_components = self._initialize_funding_components()

        # === Step 3: Execute Funding Cascade ===
        cascade_results = self._execute_funding_cascade(
            base_uses, funding_components, ledger
        )

        # === Step 3.5: Add Funding Sources to Ledger ===
        self._add_funding_sources_to_ledger(ledger, funding_components)

        # === Step 4: Calculate disposition proceeds if not provided ===
        if disposition_proceeds is None:
            disposition_proceeds = self._calculate_disposition_proceeds(
                ledger, unlevered_analysis
            )

        # === Step 4.5: Add disposition to ledger ===
        self._add_disposition_records_to_ledger(ledger, disposition_proceeds)

        # === Step 5: Assemble Final Results ===
        # Note: uses_breakdown is created by DealCalculator, CashFlowEngine uses base_uses
        return self._assemble_levered_cash_flow_results(
            base_uses,
            cascade_results,
            funding_components,
            unlevered_analysis,
            financing_analysis,
            disposition_proceeds,
            funding_cascade_details,
        )

    def _calculate_period_uses(self) -> pd.DataFrame:
        """
        Calculate total Uses (cash outflows) for each period.

        Returns:
            DataFrame with period-by-period Uses breakdown
        """
        # Initialize Uses DataFrame
        uses_df = pd.DataFrame(
            0.0,
            index=self.timeline.period_index,
            columns=[
                "Acquisition Costs",
                "Construction Costs",
                "Developer Fees",
                "Other Project Costs",
                "Total Uses",
            ],
        )

        # 1. Calculate acquisition costs
        if self.deal.acquisition:
            try:
                context = AnalysisContext(
                    timeline=self.timeline,
                    settings=self.settings,
                    property_data=self.deal.asset,
                )
                acquisition_cf = self.deal.acquisition.compute_cf(context)

                # Acquisition costs are positive (costs) - use directly for Uses
                acquisition_uses = acquisition_cf
                uses_df["Acquisition Costs"] = acquisition_uses.reindex(
                    self.timeline.period_index, fill_value=0.0
                )

            except Exception as e:
                # Log warning but continue analysis
                logger.warning(f"Acquisition cost calculation failed: {e}")

        # 2. Calculate construction costs from CapitalPlan
        if (
            hasattr(self.deal.asset, "construction_plan")
            and self.deal.asset.construction_plan
        ):
            try:
                context = AnalysisContext(
                    timeline=self.timeline,
                    settings=self.settings,
                    property_data=self.deal.asset,
                )

                # Sum construction costs from all capital items
                for capital_item in self.deal.asset.construction_plan.capital_items:
                    item_cf = capital_item.compute_cf(context)

                    # Capital costs are typically positive, but represent cash outflows (Uses)
                    item_uses = item_cf.abs()
                    uses_df["Construction Costs"] += item_uses.reindex(
                        self.timeline.period_index, fill_value=0.0
                    )

            except Exception as e:
                # Log warning but continue analysis
                logger.warning(f"Construction cost calculation failed: {e}")

        # 3. Calculate developer fees
        if self.deal.deal_fees:
            try:
                for fee in self.deal.deal_fees:
                    fee_cf = fee.compute_cf(self.timeline)
                    uses_df["Developer Fees"] += fee_cf.reindex(
                        self.timeline.period_index, fill_value=0.0
                    )

            except Exception as e:
                # Log warning but continue analysis
                logger.warning(f"Deal fee calculation failed: {e}")

        # 4. Calculate total Uses for each period
        uses_df["Total Uses"] = (
            uses_df["Acquisition Costs"]
            + uses_df["Construction Costs"]
            + uses_df["Developer Fees"]
            + uses_df["Other Project Costs"]
        )

        return uses_df

    def _calculate_ledger_based_uses(self, ledger) -> pd.Series:
        """
        Calculate total uses from ledger transactions.

        This method queries the ledger for all Capital Use and Financing Service
        transactions to determine total funding needs by period.

        Args:
            ledger: The ledger containing all transactions

        Returns:
            pd.Series with total uses by period
        """
        # Get the current ledger
        current_ledger = ledger.ledger_df()

        if current_ledger.empty:
            raise ValueError(
                "Ledger is empty - CashFlowEngine requires a populated ledger from asset analysis"
            )

        # Query for all capital uses and financing service transactions
        uses_filter = current_ledger["flow_purpose"].isin([
            TransactionPurpose.CAPITAL_USE.value,
            TransactionPurpose.FINANCING_SERVICE.value,
        ])
        uses_transactions = current_ledger[uses_filter]

        logger.debug(
            f"CashFlowEngine: Ledger has {len(current_ledger)} total transactions"
        )
        logger.debug(f"CashFlowEngine: Found {len(uses_transactions)} use transactions")
        logger.debug(
            f"CashFlowEngine: Flow purposes in ledger: {current_ledger['flow_purpose'].unique()}"
        )

        if uses_transactions.empty:
            logger.warning("CashFlowEngine: No use transactions found")
            return pd.Series(0.0, index=self.timeline.period_index, name="Total Uses")

        # Take absolute value first, then group by date and sum (all amounts are positive uses)
        uses_transactions = uses_transactions.copy()
        uses_transactions["amount"] = uses_transactions["amount"].abs()
        period_uses = uses_transactions.groupby("date")["amount"].sum()

        # Convert date index to Period index to match timeline
        if len(period_uses) > 0:
            # Convert datetime.date or Timestamp index to Period index
            if hasattr(period_uses.index[0], "to_period"):
                # Timestamp index
                period_uses.index = period_uses.index.to_period("M")
            else:
                # datetime.date index - convert to Period
                period_uses.index = pd.PeriodIndex([
                    pd.Period(date, "M") for date in period_uses.index
                ])

        logger.debug(f"CashFlowEngine: Period uses before reindex: {period_uses.sum()}")
        logger.debug(
            f"CashFlowEngine: Period uses index type after conversion: {type(period_uses.index[0]) if len(period_uses) > 0 else 'empty'}"
        )

        # Reindex to full timeline and fill missing with zeros
        result = period_uses.reindex(self.timeline.period_index, fill_value=0.0)
        logger.debug(f"CashFlowEngine: Final result sum: {result.sum()}")

        return result

    def _add_funding_sources_to_ledger(self, ledger, funding_components):
        """
        Add funding source transactions (equity only) to the ledger.

        This method adds equity contributions to the ledger. Debt flows are NOT added here
        because they are already written by debt facilities via their compute_cf method.
        This avoids duplicate ledger entries and maintains single source of truth.

        Args:
            ledger: The ledger to add transactions to
            funding_components: Dict containing funding series from cascade
        """
        # Add equity contributions as Capital Source
        if "equity_contributions" in funding_components:
            equity_series = funding_components["equity_contributions"]
            # Only add if there are non-zero contributions
            if equity_series.sum() > 0:
                metadata = SeriesMetadata(
                    category=CashFlowCategoryEnum.FINANCING,
                    subcategory=ExpenseSubcategoryEnum.OPEX,  # FIXME: Need proper financing subcategory enum
                    item_name="Equity Contributions",
                    source_id=self.deal.uid,  # Deal is the source
                    asset_id=self.deal.asset.uid,
                    deal_id=self.deal.uid,
                    pass_num=2,  # Funding is pass 2
                )
                ledger.add_series(equity_series, metadata)

        # NOTE: Debt draws are NOT added here because they are already written by debt facilities
        # via their compute_cf method. This avoids duplicate ledger entries.

        # NOTE: Interest expense is also NOT added here because debt service (which includes
        # interest) is already written by debt facilities via their compute_cf method.

    def _initialize_funding_components(self) -> Dict[str, Any]:
        """
        Initialize funding component tracking structures.

        Returns:
            Dictionary with initialized funding component Series
        """
        return {
            "total_uses": pd.Series(0.0, index=self.timeline.period_index),
            "equity_contributions": pd.Series(0.0, index=self.timeline.period_index),
            "debt_draws": pd.Series(0.0, index=self.timeline.period_index),
            "loan_proceeds": pd.Series(0.0, index=self.timeline.period_index),
            "interest_expense": pd.Series(0.0, index=self.timeline.period_index),
            "compounded_interest": pd.Series(0.0, index=self.timeline.period_index),
            "debt_draws_by_tranche": self._initialize_tranche_tracking(),
            "equity_cumulative": pd.Series(0.0, index=self.timeline.period_index),
        }

    def _initialize_tranche_tracking(self) -> Dict[str, pd.Series]:
        """Initialize debt tranche tracking structures."""
        debt_draws_by_tranche = {}
        if self.deal.financing:
            for facility in self.deal.financing.facilities:
                if hasattr(facility, "kind") and facility.kind == "construction":
                    # Check if facility has tranches and they're not None
                    if hasattr(facility, "tranches") and facility.tranches:
                        for tranche in facility.tranches:
                            debt_draws_by_tranche[tranche.name] = pd.Series(
                                0.0, index=self.timeline.period_index
                            )

        return debt_draws_by_tranche

    def _execute_funding_cascade(
        self,
        base_uses: pd.Series,
        funding_components: Dict[str, Any],
        ledger: "Ledger",
    ) -> Dict[str, Any]:
        """
        Execute institutional-grade funding cascade with proper iterative logic.

        This implements the robust period-by-period iterative funding cascade where:
        1. Initialize state variables (base_uses, working_uses, balances)
        2. Process each period iteratively
        3. Fund period uses with equity-first, then debt logic
        4. Calculate interest on PREVIOUS period's outstanding balance
        5. Capitalize interest into NEXT period's uses (compounding)
        6. Continue until all periods are funded

        Args:
            base_uses: Base uses before interest compounding
            funding_components: Initialized funding component structures

        Returns:
            Dictionary with cascade results and detailed tracking
        """
        # === STEP 1: Initialize State Variables ===
        # Working uses will be modified with interest compounding
        working_uses = base_uses.copy()

        # Initialize balance tracking
        outstanding_debt_balance = pd.Series(0.0, index=self.timeline.period_index)

        # Initialize cumulative funding tracking
        equity_funded_cumulative = 0.0
        debt_funded_cumulative = 0.0

        # Initialize funding component series
        funding_components["total_uses"] = working_uses.copy()
        funding_components["equity_contributions"] = pd.Series(
            0.0, index=self.timeline.period_index
        )
        funding_components["debt_draws"] = pd.Series(
            0.0, index=self.timeline.period_index
        )
        funding_components["loan_proceeds"] = pd.Series(
            0.0, index=self.timeline.period_index
        )
        funding_components["interest_expense"] = pd.Series(
            0.0, index=self.timeline.period_index
        )
        funding_components["compounded_interest"] = pd.Series(
            0.0, index=self.timeline.period_index
        )
        funding_components["equity_cumulative"] = pd.Series(
            0.0, index=self.timeline.period_index
        )

        # Get interest rate and reserve settings
        cash_annual_rate = 0.06  # Default 6% cash interest
        fund_interest_from_reserve = False  # Default to cash interest

        if self.deal.financing:
            for facility in self.deal.financing.facilities:
                if hasattr(facility, "kind") and facility.kind == "construction":
                    # Check if interest should be funded from reserve
                    if hasattr(facility, "fund_interest_from_reserve"):
                        fund_interest_from_reserve = facility.fund_interest_from_reserve

                    if facility.tranches:
                        # Use first tranche rates
                        tranche = facility.tranches[0]
                        if hasattr(tranche, "interest_rate") and hasattr(
                            tranche.interest_rate, "effective_rate"
                        ):
                            cash_annual_rate = float(
                                tranche.interest_rate.effective_rate
                            )
                    break

        cash_monthly_rate = cash_annual_rate / 12

        # === STEP 2: Iterative Funding Loop ===
        # This is the heart of the funding cascade - we process each period sequentially
        # because interest from previous periods affects current period funding requirements
        for i, period in enumerate(self.timeline.period_index):
            # === Step 2.1: Calculate Interest on Previous Period's Balance ===
            # Interest is always calculated on the PREVIOUS period's outstanding balance
            # This follows institutional lending practice where interest accrues on existing debt
            if i > 0:
                # Get the debt balance from the previous period
                previous_balance = outstanding_debt_balance.iloc[i - 1]

                if previous_balance > 0:
                    # Calculate monthly interest using the facility's interest rate
                    cash_interest = previous_balance * cash_monthly_rate

                    # Handle different interest funding mechanisms
                    if fund_interest_from_reserve:
                        # RESERVE-FUNDED INTEREST: Common in construction loans
                        # Interest is paid from a pre-funded reserve, not from cash flow
                        funding_components["interest_expense"][period] = 0.0

                        # Track interest funded from reserve for audit purposes
                        if "interest_reserve_utilized" not in funding_components:
                            funding_components["interest_reserve_utilized"] = pd.Series(
                                0.0, index=self.timeline.period_index
                            )
                        funding_components["interest_reserve_utilized"][period] = (
                            cash_interest
                        )

                        # IMPORTANT: Reserve-funded interest does NOT become additional uses
                        # The reserve was already pre-funded, so no additional funding needed
                    else:
                        # CASH INTEREST: Standard approach where interest must be funded
                        # This is the most common approach in development financing
                        funding_components["interest_expense"][period] = cash_interest

                        # CRITICAL: Add interest to THIS period's uses (it needs to be funded now)
                        # This is what creates the compounding effect - interest becomes part of uses
                        working_uses[period] += cash_interest
                        funding_components["compounded_interest"][period] += (
                            cash_interest
                        )

            # === Step 2.2: Fund This Period's Uses ===
            period_uses = working_uses[period]

            if period_uses > 0:
                # Calculate dynamic equity target based on current working uses
                # This ensures equity target adjusts as interest compounds
                current_total_uses = working_uses.sum()
                equity_target = self._calculate_equity_target(current_total_uses)

                # Calculate funding for this period's uses
                period_equity, period_debt = self._fund_period_uses(
                    period_uses,
                    equity_target,
                    equity_funded_cumulative,
                    debt_funded_cumulative,
                    i,
                    funding_components,
                    working_uses,
                    ledger,
                )

                # Update funding components
                funding_components["equity_contributions"][period] = period_equity
                funding_components["debt_draws"][period] = period_debt
                funding_components["loan_proceeds"][period] = period_debt

                # Update cumulative tracking
                equity_funded_cumulative += period_equity
                debt_funded_cumulative += period_debt

                # Update outstanding debt balance
                outstanding_debt_balance.iloc[i] = (
                    outstanding_debt_balance.iloc[i - 1] if i > 0 else 0.0
                )
                outstanding_debt_balance.iloc[i] += period_debt
            elif i > 0:
                outstanding_debt_balance.iloc[i] = outstanding_debt_balance.iloc[i - 1]

            # Update cumulative equity series for all periods
            funding_components["equity_cumulative"][period] = equity_funded_cumulative

        # === STEP 3: Update Final State ===
        # Final total uses includes all compounded interest
        funding_components["total_uses"] = working_uses

        # Calculate final equity target based on total uses with interest
        final_total_uses = working_uses.sum()
        final_equity_target = self._calculate_equity_target(final_total_uses)

        # Compile interest details
        interest_details = self._compile_interest_details(funding_components)

        # Calculate final funding gap
        total_funding = equity_funded_cumulative + debt_funded_cumulative
        funding_gap = final_total_uses - total_funding

        return {
            "total_project_cost": final_total_uses,  # Total uses including compounded interest
            "equity_target": final_equity_target,
            "equity_funded": equity_funded_cumulative,
            "debt_funded": debt_funded_cumulative,
            "funding_gap": funding_gap,
            "interest_details": interest_details,
        }

    def _calculate_equity_target(self, total_project_cost: float) -> float:
        """Calculate equity target based on financing structure."""
        if not self.deal.financing:
            return total_project_cost  # All equity deal

        # For construction financing, use the first tranche's LTC as equity target
        for facility in self.deal.financing.facilities:
            if hasattr(facility, "kind") and facility.kind == "construction":
                # Check if facility actually has tranches and they're not None
                if hasattr(facility, "tranches") and facility.tranches:
                    first_tranche_ltc = facility.tranches[0].ltc_threshold
                    equity_target = total_project_cost * (1 - first_tranche_ltc)
                    return equity_target

        # Fallback: 25% equity
        return total_project_cost * 0.25

    def _fund_period_uses(
        self,
        period_uses: float,
        equity_target: float,
        equity_funded: float,
        debt_funded: float,
        period_idx: int,
        funding_components: Dict[str, Any],
        working_uses: pd.Series,
        ledger: "Ledger",
    ) -> tuple[float, float]:
        """
        Fund period uses with equity-first, then ledger-based debt funding logic.

        This method implements the equity-first funding priority, then queries the
        ledger for available debt funding capacity instead of calculating complex
        multi-tranche logic in parallel. This maintains single source of truth.

        Args:
            period_uses: Total uses for this period
            equity_target: Target equity contribution
            equity_funded: Cumulative equity funded so far
            debt_funded: Cumulative debt funded so far
            period_idx: Current period index
            funding_components: Funding components for tranche tracking
            working_uses: Working uses series for cumulative calculations
            ledger: Ledger containing debt facility transactions

        Returns:
            Tuple of (period_equity, period_debt)
        """
        remaining_equity_capacity = max(0, equity_target - equity_funded)

        if remaining_equity_capacity >= period_uses:
            # Fund entirely with equity
            return period_uses, 0.0
        else:
            # Fund with remaining equity + debt
            period_equity = remaining_equity_capacity
            period_debt_needed = period_uses - period_equity

            # Get actual debt funding by querying ledger (replaces multi-tranche logic)
            period_debt = self._get_available_debt_funding(
                period_debt_needed, period_idx, ledger
            )

            return period_equity, period_debt

    def _get_available_debt_funding(
        self,
        debt_needed: float,
        period_idx: int,
        ledger: "Ledger",
    ) -> float:
        """
        Query ledger for available debt funding capacity.

        This method handles the case where debt facilities write total loan proceeds
        at origination but the funding cascade needs to distribute that capacity
        across periods based on actual funding needs.

        Args:
            debt_needed: Amount of debt funding needed this period
            period_idx: Current period index
            ledger: Ledger containing debt facility transactions

        Returns:
            Available debt funding for this period (up to debt_needed)
        """
        if not self.deal.financing:
            return 0.0

        try:
            # Get current ledger DataFrame and create queries interface
            current_ledger_df = ledger.ledger_df()

            # Query ledger directly for financing transactions (bypass LedgerQueries due to enum serialization issues)
            financing_txns = current_ledger_df[
                current_ledger_df["category"] == CashFlowCategoryEnum.FINANCING
            ]

            # Get loan proceeds transactions using enum for reliable matching
            loan_proc_txns = financing_txns[
                financing_txns["subcategory"] == FinancingSubcategoryEnum.LOAN_PROCEEDS
            ]
            loan_proceeds = (
                loan_proc_txns["amount"]
                if not loan_proc_txns.empty
                else pd.Series([], dtype=float)
            )

            # Get debt service transactions up to current period
            debt_svc_txns = financing_txns[
                financing_txns["subcategory"] == FinancingSubcategoryEnum.DEBT_SERVICE
            ]
            # Filter by date if we have date info
            if not debt_svc_txns.empty and "date" in debt_svc_txns.columns:
                period_date = (
                    self.timeline.period_index[period_idx].to_timestamp().date()
                )
                debt_svc_txns = debt_svc_txns[debt_svc_txns["date"] <= period_date]
            debt_service = (
                debt_svc_txns["amount"]
                if not debt_svc_txns.empty
                else pd.Series([], dtype=float)
            )

            # Calculate total loan capacity and what's been used so far
            total_loan_capacity = (
                loan_proceeds.sum() if not loan_proceeds.empty else 0.0
            )
            total_debt_service_paid = (
                abs(debt_service.sum()) if not debt_service.empty else 0.0
            )

            # Available capacity is total loan capacity minus debt service already paid
            available_capacity = max(0.0, total_loan_capacity - total_debt_service_paid)

            # Return the minimum of what's needed and what's available
            available_funding = min(debt_needed, available_capacity)

            logger.debug(
                f"Debt funding query - Period {period_idx}: needed=${debt_needed:,.0f}, "
                f"available=${available_capacity:,.0f}, providing=${available_funding:,.0f}"
            )

            return available_funding

        except Exception as e:
            logger.warning(f"Failed to query ledger for debt funding: {e}")
            # Fallback to no debt funding if query fails
            return 0.0

    # Note: Interest calculation is now integrated into _execute_funding_cascade
    # This method has been removed as it's now handled iteratively in the cascade

    def _compile_interest_details(
        self, funding_components: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compile detailed interest tracking information with interest reserves."""
        # Get interest reserve utilization if available
        interest_reserve_utilized = funding_components.get(
            "interest_reserve_utilized",
            pd.Series(0.0, index=self.timeline.period_index),
        )

        # Interest calculations use cash interest only

        # Calculate total interest (cash interest only)
        total_interest = funding_components["interest_expense"]

        # Calculate outstanding balance (debt only)
        outstanding_balance = funding_components["debt_draws"].cumsum()

        return {
            "cash_interest": funding_components["interest_expense"],
            "total_interest": total_interest,
            "outstanding_balance": outstanding_balance,
            "interest_reserve_utilized": interest_reserve_utilized,
        }

    def _assemble_levered_cash_flow_results(
        self,
        base_uses: pd.Series,
        cascade_results: Dict[str, Any],
        funding_components: Dict[str, Any],
        unlevered_analysis: UnleveredAnalysisResult,
        financing_analysis: FinancingAnalysisResult,
        disposition_proceeds: pd.Series,
        funding_cascade_details: Optional["FundingCascadeDetails"] = None,
    ) -> "LeveredCashFlowResult":
        """
        Assemble final levered cash flow results with all components.

        Args:
            base_uses: Period-by-period total uses (Series)
            cascade_results: Results from funding cascade execution
            funding_components: Funding component tracking
            unlevered_analysis: Unlevered analysis results
            financing_analysis: Financing analysis results
            disposition_proceeds: Disposition proceeds from valuation
        """
        # Calculate levered cash flows using project financing perspective (matches old implementation)
        # Formula: Levered CF = -Uses + Equity + Debt + Operating CF + Disposition - Debt Service

        # Start with project funding mechanics
        levered_cash_flows = (
            -funding_components["total_uses"]
            + funding_components["equity_contributions"]
            + funding_components["debt_draws"]
        )

        # Add unlevered cash flows (operating performance)
        unlevered_cash_flows = self._extract_unlevered_cash_flows(unlevered_analysis)
        levered_cash_flows += unlevered_cash_flows

        # Add disposition proceeds (positive cash inflow at end)
        levered_cash_flows += disposition_proceeds

        # Subtract debt service (reduces cash available to equity)
        debt_service_series = self._calculate_debt_service_series(financing_analysis)
        levered_cash_flows -= debt_service_series

        # Add refinancing events if they exist (additional proceeds to equity)
        if hasattr(financing_analysis, "refinancing_cash_flows"):
            refinancing_cf = financing_analysis.refinancing_cash_flows
            # Add net refinancing proceeds (this is the key value for equity investors)
            levered_cash_flows += refinancing_cf["net_refinancing_proceeds"].reindex(
                self.timeline.period_index, fill_value=0.0
            )

        # Calculate loan payoff series using the new helper method
        loan_payoff_series = self._calculate_loan_payoff_series(financing_analysis)

        # Add refinancing loan payoffs if they exist
        if hasattr(financing_analysis, "refinancing_cash_flows"):
            refinancing_loan_payoffs = financing_analysis.refinancing_cash_flows.get(
                "loan_payoffs", pd.Series(0.0, index=self.timeline.period_index)
            )
            loan_payoff_series += refinancing_loan_payoffs.reindex(
                self.timeline.period_index, fill_value=0.0
            )

        # Assemble cash flow components from equity investor perspective
        cash_flow_components = CashFlowComponents(
            unlevered_cash_flows=unlevered_cash_flows,
            acquisition_costs=funding_components[
                "total_uses"
            ],  # Total uses (positive outflows)
            loan_proceeds=funding_components["loan_proceeds"],
            debt_service=debt_service_series,
            disposition_proceeds=disposition_proceeds,
            loan_payoff=loan_payoff_series,
            total_uses=funding_components["total_uses"],
            equity_contributions=funding_components[
                "equity_contributions"
            ],  # Positive values (outflows)
            debt_draws=funding_components["debt_draws"],
            interest_expense=funding_components["interest_expense"],
        )

        cash_flow_summary = CashFlowSummary(
            total_investment=cascade_results["equity_funded"],
            total_distributions=self._calculate_total_distributions(
                unlevered_analysis, disposition_proceeds
            ),
            net_cash_flow=levered_cash_flows.sum(),
        )

        # Create detailed funding cascade components
        # Ensure mathematical consistency: total_uses = base_uses + compounded_interest
        # The funding cascade modifies working_uses during execution, so we need to ensure
        # the base_uses we report matches what was actually used in the calculation
        actual_base_uses = (
            funding_components["total_uses"] - funding_components["compounded_interest"]
        )

        interest_compounding_details = InterestCompoundingDetails(
            base_uses=actual_base_uses,
            compounded_interest=funding_components["compounded_interest"],
            total_uses_with_interest=funding_components["total_uses"],
            equity_target=cascade_results["equity_target"],
            equity_funded=cascade_results["equity_funded"],
            debt_funded=cascade_results["debt_funded"],
            funding_gap=cascade_results["funding_gap"],
            total_project_cost=cascade_results["total_project_cost"],
        )

        # NOTE: Advanced interest features not implemented in MVP
        # Future: support for complex interest structures
        advanced_interest_details = None

        # Calculate interest reserve capacity properly
        interest_reserve_capacity = self._calculate_interest_reserve_capacity(
            cascade_results["total_project_cost"]
        )

        # Calculate interest reserve details
        interest_reserve_details = InterestReserveDetails(
            interest_funded_from_reserve=cascade_results["interest_details"].get(
                "interest_reserve_utilized",
                pd.Series(0.0, index=self.timeline.period_index),
            ),
            interest_reserve_capacity=pd.Series(
                interest_reserve_capacity, index=self.timeline.period_index
            ),
            interest_reserve_utilization=cascade_results["interest_details"].get(
                "interest_reserve_utilized",
                pd.Series(0.0, index=self.timeline.period_index),
            ),
        )

        # Update funding cascade details with tranche data from actual cascade execution
        if funding_cascade_details is not None:
            # Update with actual tranche tracking data from funding cascade execution
            funding_cascade_details.debt_draws_by_tranche = funding_components[
                "debt_draws_by_tranche"
            ]

        # Create and return the complete LeveredCashFlowResult
        return LeveredCashFlowResult(
            levered_cash_flows=levered_cash_flows,
            cash_flow_components=cash_flow_components,
            cash_flow_summary=cash_flow_summary,
            funding_cascade_details=funding_cascade_details,
        )

    def _extract_unlevered_cash_flows(
        self, unlevered_analysis: UnleveredAnalysisResult
    ) -> pd.Series:
        """
        Extract unlevered cash flows from the asset analysis.

        Args:
            unlevered_analysis: Results from unlevered asset analysis

        Returns:
            Net unlevered cash flows series aligned with timeline
        """
        if unlevered_analysis.cash_flows is not None:
            cash_flows = unlevered_analysis.cash_flows

            # Try to extract net cash flows from the analysis
            if hasattr(cash_flows, "columns"):
                # If DataFrame, try to get net cash flows column
                net_cf_columns = [
                    col
                    for col in cash_flows.columns
                    if "net" in col.lower() or "cash" in col.lower()
                ]
                if net_cf_columns:
                    return cash_flows[net_cf_columns[0]].reindex(
                        self.timeline.period_index, fill_value=0.0
                    )
                else:
                    # Sum all positive columns minus all negative columns
                    positive_cols = [
                        col for col in cash_flows.columns if (cash_flows[col] > 0).any()
                    ]
                    negative_cols = [
                        col for col in cash_flows.columns if (cash_flows[col] < 0).any()
                    ]

                    net_cf = (
                        cash_flows[positive_cols].sum(axis=1)
                        - cash_flows[negative_cols].sum(axis=1).abs()
                    )
                    return net_cf.reindex(self.timeline.period_index, fill_value=0.0)
            elif hasattr(cash_flows, "index"):
                # If Series, use directly
                return cash_flows.reindex(self.timeline.period_index, fill_value=0.0)

        # Fallback: return zeros if no cash flows found
        return pd.Series(0.0, index=self.timeline.period_index)

    def _calculate_debt_service_series(
        self, financing_analysis: FinancingAnalysisResult
    ) -> pd.Series:
        """
        Calculate debt service time series from financing analysis results.

        Args:
            financing_analysis: Results from financing analysis (already computed by DebtAnalyzer)

        Returns:
            Total debt service series aligned with timeline
        """
        total_debt_service = pd.Series(0.0, index=self.timeline.period_index)

        # Use debt service data already computed by DebtAnalyzer
        if financing_analysis.has_financing and financing_analysis.debt_service:
            for (
                facility_name,
                debt_service_series,
            ) in financing_analysis.debt_service.items():
                if debt_service_series is not None:
                    try:
                        # Ensure proper alignment with timeline
                        aligned_debt_service = debt_service_series.reindex(
                            self.timeline.period_index, fill_value=0.0
                        )
                        total_debt_service += aligned_debt_service
                    except Exception as e:
                        logger.warning(
                            f"Could not process debt service for {facility_name}: {e}"
                        )

        return total_debt_service

    def _calculate_loan_payoff_series(
        self, financing_analysis: FinancingAnalysisResult
    ) -> pd.Series:
        """
        Calculate loan payoff amounts for refinancing or disposition.

        Args:
            financing_analysis: Results from financing analysis

        Returns:
            Loan payoff series aligned with timeline
        """
        loan_payoff = pd.Series(0.0, index=self.timeline.period_index)

        if self.deal.financing:
            # Build combined financing cash flows DataFrame from analysis results
            financing_cash_flows_data = {}

            # Add debt service series
            for facility_name, debt_series in financing_analysis.debt_service.items():
                if debt_series is not None:
                    financing_cash_flows_data[f"{facility_name} Interest"] = debt_series

            # Add loan proceeds series (as draws)
            for (
                facility_name,
                proceeds_series,
            ) in financing_analysis.loan_proceeds.items():
                if proceeds_series is not None:
                    financing_cash_flows_data[f"{facility_name} Draw"] = proceeds_series

            # Create combined DataFrame
            if financing_cash_flows_data:
                financing_cash_flows = pd.DataFrame(
                    financing_cash_flows_data, index=self.timeline.period_index
                ).fillna(0.0)
            else:
                financing_cash_flows = pd.DataFrame(index=self.timeline.period_index)

            for facility in self.deal.financing.facilities:
                try:
                    # Check if facility has outstanding balance calculation
                    if hasattr(facility, "get_outstanding_balance"):
                        for period in self.timeline.period_index:
                            period_date = period.to_timestamp().date()
                            balance = facility.get_outstanding_balance(
                                period_date, financing_cash_flows
                            )
                            if balance > 0:
                                # Check if this is a refinancing or disposition period
                                if (
                                    self.deal.exit_valuation
                                    and hasattr(
                                        self.deal.exit_valuation, "disposition_date"
                                    )
                                    and period
                                    == self.deal.exit_valuation.disposition_date
                                ):
                                    loan_payoff[period] += balance
                                elif (
                                    hasattr(facility, "refinance_timing")
                                    and facility.refinance_timing
                                ):
                                    refinance_period = self.timeline.period_index[
                                        facility.refinance_timing - 1
                                    ]
                                    if period == refinance_period:
                                        loan_payoff[period] += balance

                except Exception as e:
                    # Log warning but continue
                    logger.warning(
                        f"Could not calculate loan payoff for {facility.name}: {e}"
                    )

        return loan_payoff

    def _calculate_total_distributions(
        self,
        unlevered_analysis: UnleveredAnalysisResult,
        disposition_proceeds: pd.Series,
    ) -> float:
        """
        Calculate total distributions from asset operations.

        Args:
            unlevered_analysis: Results from unlevered asset analysis
            disposition_proceeds: Disposition proceeds from valuation

        Returns:
            Total distributions amount
        """
        # Calculate total distributions from unlevered cash flows
        unlevered_cf = self._extract_unlevered_cash_flows(unlevered_analysis)
        positive_cash_flows = unlevered_cf[unlevered_cf > 0].sum()

        # Add disposition proceeds if applicable
        total_disposition = disposition_proceeds.sum()

        return positive_cash_flows + total_disposition

    def _calculate_interest_reserve_capacity(self, total_project_cost: float) -> float:
        """
        Calculate interest reserve capacity based on facility parameters.

        Args:
            total_project_cost: Total project cost including interest

        Returns:
            Interest reserve capacity amount
        """
        if not self.deal.financing:
            return 0.0

        # Get construction facilities to calculate capacity
        for facility in self.deal.financing.facilities:
            if hasattr(facility, "kind") and facility.kind == "construction":
                total_facility_capacity = 0.0

                # Check if facility has tranches
                if hasattr(facility, "tranches") and facility.tranches:
                    for i, tranche in enumerate(facility.tranches):
                        if i == 0:
                            # First tranche: from 0 to its LTC threshold
                            tranche_capacity = (
                                total_project_cost * tranche.ltc_threshold
                            )
                        else:
                            # Subsequent tranches: from previous LTC to current LTC
                            prev_tranche_ltc = facility.tranches[i - 1].ltc_threshold
                            tranche_capacity = total_project_cost * (
                                tranche.ltc_threshold - prev_tranche_ltc
                            )
                        total_facility_capacity += tranche_capacity

                # Interest reserve capacity based on facility's configurable rate
                interest_reserve_rate = getattr(facility, "interest_reserve_rate", 0.15)
                return total_facility_capacity * interest_reserve_rate

        return 0.0

    def _calculate_disposition_proceeds(
        self,
        ledger: "Ledger",
        unlevered_analysis: UnleveredAnalysisResult = None,
    ) -> pd.Series:
        """
        Calculate disposition proceeds if there's a disposition event.

        Args:
            ledger: The analysis ledger (Pass-the-Builder pattern).
                Must be the same instance used throughout the analysis.
            unlevered_analysis: Results from unlevered asset analysis containing NOI data

        Returns:
            Disposition proceeds series aligned with timeline
        """
        disposition_proceeds = pd.Series(0.0, index=self.timeline.period_index)

        if self.deal.exit_valuation:
            try:
                # Calculate disposition proceeds from the disposition model
                # ledger is required parameter
                context = AnalysisContext(
                    timeline=self.timeline,
                    settings=self.settings,
                    property_data=self.deal.asset,
                    ledger=ledger,
                )

                # Pass unlevered analysis to the context so valuation models can access NOI
                if unlevered_analysis:
                    context.unlevered_analysis = unlevered_analysis

                    # Also populate resolved_lookups for backward compatibility
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
                            pass

                # Get disposition cash flows
                disposition_cf = self.deal.exit_valuation.compute_cf(context)
                disposition_proceeds = disposition_cf.reindex(
                    self.timeline.period_index, fill_value=0.0
                )

                # Disposition proceeds should be positive
                disposition_proceeds = disposition_proceeds.abs()

            except Exception as e:
                # Log warning but continue
                logger.warning(f"Could not calculate disposition proceeds: {e}")

        return disposition_proceeds

    def _add_disposition_records_to_ledger(
        self, ledger: "Ledger", disposition_proceeds: pd.Series
    ) -> None:
        """
        Add disposition/exit sale transactions to the ledger.

        Args:
            ledger: The analysis ledger
            disposition_proceeds: Series of disposition proceeds
        """
        if disposition_proceeds is None or (disposition_proceeds == 0).all():
            logger.debug("No disposition proceeds to add to ledger")
            return

        # Disposition proceeds (positive = cash inflow from sale)
        # Use OTHER subcategory since DISPOSITION doesn't exist
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.CAPITAL,
            subcategory=CapitalSubcategoryEnum.OTHER,
            item_name="Exit Sale Proceeds",
            source_id=str(self.deal.uid) if self.deal else "unknown",
            asset_id=self.deal.asset.uid
            if self.deal and self.deal.asset
            else "unknown",
            pass_num=CalculationPhase.VALUATION.value,
        )

        ledger.add_series(disposition_proceeds, metadata)

        total_disposition = disposition_proceeds.sum()
        if total_disposition > 0:
            logger.info(
                f"✅ Added disposition proceeds to ledger: ${total_disposition:,.0f}"
            )
