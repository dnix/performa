# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Funding cascade and levered cash flow engine.

Provides period-by-period funding logic and levered cash flow assembly using the
ledger as the single source of truth. Equity contributions are recorded here;
debt facilities write their own transactions via their `compute_cf` methods.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict

import pandas as pd

from performa.core.ledger import SeriesMetadata
from performa.core.primitives import (
    CashFlowCategoryEnum,
    FinancingSubcategoryEnum,
    TransactionPurpose,
)
from performa.debt.construction import ConstructionFacility

# Deprecated result imports removed - full ledger-driven now
from .base import AnalysisSpecialist
from .disposition import DispositionAnalyzer

if TYPE_CHECKING:
    from performa.core.ledger import Ledger
    from performa.deal.orchestrator import DealContext


logger = logging.getLogger(__name__)


@dataclass
class CashFlowEngine(AnalysisSpecialist):
    """
    Calculate levered cash flows via a funding cascade.

    The engine sequences equity and debt funding, handles interest (cash or
    reserve-funded), and records equity contributions. Debt facilities write
    their own transactions via their `compute_cf` methods.

    Attributes:
        deal: Deal with asset, financing, and partnership structures.
        timeline: Analysis timeline.
        settings: Global settings for cash flow configuration.
    """

    # Fields inherited from AnalysisSpecialist base class:
    # - context (DealContext)
    # - deal, timeline, settings, ledger (via properties)
    # - queries (LedgerQueries)

    def _extract_max_ltc_from_facilities(self) -> float:
        """
        Extract maximum LTC ratio from deal financing facilities.

        Uses explicit type-based dispatch to get LTC settings from facilities.
        Consolidates the scattered LTC logic into one place.

        Returns:
            Maximum LTC ratio from facilities, or standard default if none found
        """

        max_ltc_from_facilities = 0.0

        if self.deal.financing and self.deal.financing.facilities:
            for facility in self.deal.financing.facilities:
                if isinstance(facility, ConstructionFacility):
                    # Check for explicit LTC ratio on facility
                    if facility.ltc_ratio is not None:
                        max_ltc_from_facilities = max(
                            max_ltc_from_facilities, facility.ltc_ratio
                        )

                    # Check for tranche-based LTC (consolidates existing logic)
                    elif facility.tranches is not None:
                        facility_max_ltc = max(
                            tranche.ltc_threshold for tranche in facility.tranches
                        )
                        max_ltc_from_facilities = max(
                            max_ltc_from_facilities, facility_max_ltc
                        )

        # Fallback to standard institutional default if no facility LTC found
        return max_ltc_from_facilities if max_ltc_from_facilities > 0 else 0.75

    def process(self) -> None:
        """
        Settings-driven funding cascade with institutional-grade logic.
        Execute funding cascade using settings for LTC ratios and assumptions.

        Writes all funding transactions to ledger.
        """
        # Extract LTC from facility settings (or use standard default)
        max_ltc = self._extract_max_ltc_from_facilities()

        # Step 1: Calculate what needs funding from ledger
        base_uses = self._calculate_ledger_based_uses(self.ledger, self.timeline)
        if base_uses.sum() == 0:
            return  # No funding required

        # Step 2: Initialize funding components with settings
        funding_components = self._initialize_funding_components(self.context, max_ltc)

        # Step 3: ESSENTIAL LOGIC - Execute funding cascade
        cascade_results = self._execute_funding_cascade(
            base_uses, funding_components, self.ledger
        )

        # Step 4: ESSENTIAL LOGIC - Write funding sources to ledger
        self._add_funding_sources_to_ledger(self.ledger, funding_components)

        # Step 5: Disposition handling removed - now handled by DispositionAnalyzer pass
        # The orchestrator calls DispositionAnalyzer.process() separately

        # Cash flow processing complete - all funding transactions written to ledger

    ###########################################################################
    # LEDGER-BASED CASH FLOW CALCULATIONS
    ###########################################################################

    def _calculate_ledger_based_uses(self, ledger, timeline) -> pd.Series:
        """
        Calculate total uses from ledger transactions.

        This method queries the ledger for all Capital Use and Financing Service
        transactions to determine total funding needs by period.

        Args:
            ledger: The ledger containing all transactions
            timeline: Timeline for period index

        Returns:
            pd.Series with total uses by period
        """
        # Get the current ledger
        current_ledger = ledger.ledger_df()

        if current_ledger.empty:
            raise ValueError(
                "Ledger is empty - CashFlowEngine requires a populated ledger from asset analysis"
            )

        # Query for capital uses ONLY - exclude financing service to avoid circular funding
        # Financing service (debt service) should not be treated as uses
        # that require additional funding - this creates circular dependency
        uses_filter = current_ledger["flow_purpose"].isin([
            TransactionPurpose.CAPITAL_USE.value,
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
            return pd.Series(0.0, index=timeline.period_index, name="Total Uses")

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
        result = period_uses.reindex(timeline.period_index, fill_value=0.0)
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
                    subcategory=FinancingSubcategoryEnum.EQUITY_CONTRIBUTION,
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

    # FIXME: _initialize_funding_components() may be deletion candidate
    # This method initializes structures that could be simplified with pure ledger approach.
    @staticmethod
    def _initialize_funding_components(
        context: "DealContext", max_ltc: float
    ) -> Dict[str, Any]:
        """
        Initialize funding component tracking structures with settings.

        Args:
            context: Deal context with timeline and settings
            max_ltc: Maximum loan-to-cost ratio from settings

        Returns:
            Dictionary with initialized funding component Series
        """
        return {
            "total_uses": pd.Series(0.0, index=context.timeline.period_index),
            "equity_contributions": pd.Series(0.0, index=context.timeline.period_index),
            "debt_draws": pd.Series(0.0, index=context.timeline.period_index),
            "loan_proceeds": pd.Series(0.0, index=context.timeline.period_index),
            "interest_expense": pd.Series(0.0, index=context.timeline.period_index),
            "compounded_interest": pd.Series(0.0, index=context.timeline.period_index),
            "debt_draws_by_tranche": {},
            "equity_cumulative": pd.Series(0.0, index=context.timeline.period_index),
            "max_ltc": max_ltc,  # Include settings in components
        }

    # FIXME: _execute_funding_cascade() may be simplification candidate
    # This 216-line method implements complex funding cascade logic.
    # KEEP FOR NOW: Contains critical equity/debt allocation and interest compounding.
    # FUTURE: Could be simplified if ledger tracking becomes more sophisticated.
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

        # Initialize debt draw tracking for _get_available_debt_funding
        # This must be done here, not inside the method, to preserve state across periods
        self._cumulative_debt_drawn = 0.0

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
                if facility.kind == "construction":
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

                        # Add interest to this period's uses (it needs to be funded now)
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
                equity_target = self._calculate_equity_target(
                    current_total_uses, ledger
                )

                # Calculate funding for this period's uses
                logger.debug(
                    f"Period {i}: uses=${period_uses:,.0f}, equity_target=${equity_target:,.0f}, "
                    f"equity_funded=${equity_funded_cumulative:,.0f}, debt_funded=${debt_funded_cumulative:,.0f}"
                )
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
                logger.debug(
                    f"  Funded with: equity=${period_equity:,.0f}, debt=${period_debt:,.0f}"
                )

                # Update funding components
                funding_components["equity_contributions"][period] = period_equity
                funding_components["debt_draws"][period] = period_debt
                funding_components["loan_proceeds"][period] = period_debt

                # Update cumulative tracking
                equity_funded_cumulative += period_equity
                debt_funded_cumulative += period_debt

                logger.debug(
                    f"  Cumulative totals: equity=${equity_funded_cumulative:,.0f}, debt=${debt_funded_cumulative:,.0f}"
                )

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
        final_equity_target = self._calculate_equity_target(final_total_uses, ledger)

        # Calculate final funding gap
        total_funding = equity_funded_cumulative + debt_funded_cumulative
        funding_gap = final_total_uses - total_funding

        # TODO: Add interest details and funding validation if needed
        interest_details = {"total_interest": 0.0}  # Minimal placeholder

        logger.debug(
            f"Funding cascade complete: equity_funded=${equity_funded_cumulative:,.0f}, "
            f"debt_funded=${debt_funded_cumulative:,.0f}, total_uses=${final_total_uses:,.0f}"
        )

        return {
            "total_project_cost": final_total_uses,  # Total uses including compounded interest
            "equity_target": final_equity_target,
            "equity_funded": equity_funded_cumulative,
            "debt_funded": debt_funded_cumulative,
            "funding_gap": funding_gap,
            "interest_details": interest_details,
        }

    def _calculate_equity_target(self, total_project_cost: float, ledger=None) -> float:
        """Calculate equity target based on available data."""
        if not self.deal.financing:
            return total_project_cost  # All equity deal

        # Check for explicit capital commitments (inferred from data)
        if (
            self.deal.has_equity_partners
            and self.deal.equity_partners.has_explicit_commitments
        ):
            # Use explicit commitments
            total_committed = self.deal.equity_partners.total_committed_capital

            # Validate that commitments can meet equity requirements
            # Calculate what equity SHOULD be based on project costs and debt structure
            required_equity = self._calculate_required_equity_from_ltc(
                total_project_cost
            )

            # Check for capital shortfall
            if total_committed < required_equity:
                shortfall = required_equity - total_committed
                shortfall_pct = (shortfall / required_equity) * 100

                if shortfall_pct > 10:  # >10% shortfall = error
                    raise ValueError(
                        f"CAPITAL SHORTFALL: partner commitments (${total_committed:,.0f}) "
                        f"are {shortfall_pct:.1f}% below required equity (${required_equity:,.0f}). "
                        f"shortfall: ${shortfall:,.0f}. Increase commitments or reduce LTC ratio."
                    )
                elif shortfall_pct > 5:  # 5-10% shortfall = warning
                    logger.warning(
                        f"THIN EQUITY MARGIN: partner commitments (${total_committed:,.0f}) "
                        f"are only {shortfall_pct:.1f}% above required equity (${required_equity:,.0f}). "
                        f"Consider increasing equity buffer."
                    )

            # Check for over-commitment (might indicate parameter issues)
            elif total_committed > required_equity * 1.5:  # >150% over-committed
                excess = total_committed - required_equity
                excess_pct = (excess / required_equity) * 100
                logger.warning(
                    f"📊 EXCESS EQUITY: Partner commitments (${total_committed:,.0f}) "
                    f"exceed estimated requirements (${required_equity:,.0f}) by {excess_pct:.1f}%. "
                    f"Verify LTC parameters or consider increasing debt."
                )

            logger.debug(
                f"Using explicit capital commitments: ${total_committed:,.0f} "
                f"(vs estimated requirement: ${required_equity:,.0f})"
            )
            return total_committed

        # For construction financing, calculate equity based on debt structure
        for facility in self.deal.financing.facilities:
            if hasattr(facility, "kind") and facility.kind == "construction":
                # If facility has ltc_ratio, use it to calculate equity target
                if hasattr(facility, "ltc_ratio") and facility.ltc_ratio is not None:
                    # TODO: Review this calculation thoroughly
                    # Use initial uses to fix equity target
                    # This prevents interest compounding from inflating equity needs
                    # The ltc_ratio determines loan sizing (and thus implied equity need)
                    # Interest is funded by the debt facility itself (interest reserve)

                    # TODO: This calculation assumes equity = (1 - LTC) which only works for
                    # single-loan deals. Need proper capital structure model at Deal level
                    # to handle complex equity structures (GP/LP/Pref/Mezz)

                    # Get initial capital uses (before interest)
                    if ledger:
                        ledger_df = ledger.ledger_df()
                        if not ledger_df.empty and "flow_purpose" in ledger_df.columns:
                            capital_uses = ledger_df[
                                ledger_df["flow_purpose"] == "Capital Use"
                            ]
                        else:
                            capital_uses = pd.DataFrame()
                    else:
                        capital_uses = pd.DataFrame()

                    if not capital_uses.empty:
                        # Sum only the land and hard costs (exclude financing costs)
                        base_uses = capital_uses[
                            ~capital_uses["subcategory"].str.contains(
                                "Financing", na=False
                            )
                        ]["amount"].sum()
                        base_project_cost = (
                            abs(base_uses) if base_uses else total_project_cost
                        )
                    else:
                        # Fallback to total if no breakdown available
                        base_project_cost = total_project_cost

                    # Fixed equity based on LTC ratio (simplified - assumes single loan)
                    equity_target = base_project_cost * (1 - facility.ltc_ratio)
                    logger.debug(
                        f"Fixed equity target: ${equity_target:,.0f} ({1 - facility.ltc_ratio:.0%} of ${base_project_cost:,.0f} base costs)"
                    )
                    return max(equity_target, 0)

                # If facility has explicit loan_amount, use it to derive equity
                if hasattr(facility, "loan_amount") and facility.loan_amount:
                    # Equity is total cost minus loan amount
                    equity_target = total_project_cost - facility.loan_amount
                    logger.debug(
                        f"Equity target from loan_amount: ${equity_target:,.0f} (Cost ${total_project_cost:,.0f} - Loan ${facility.loan_amount:,.0f})"
                    )
                    return max(equity_target, 0)  # Ensure non-negative

                # Check if facility actually has tranches and they're not None
                if hasattr(facility, "tranches") and facility.tranches:
                    first_tranche_ltc = facility.tranches[0].ltc_threshold
                    equity_target = total_project_cost * (1 - first_tranche_ltc)
                    return equity_target

        # Fallback: 25% equity
        logger.warning(
            "Using fallback 25% equity target - no loan amount or tranches found"
        )
        return total_project_cost * 0.25

    def _calculate_required_equity_from_ltc(self, total_project_cost: float) -> float:
        """Calculate required equity based on LTC constraints and debt structure."""
        if not self.deal.financing:
            return total_project_cost  # All equity deal

        # Find the most restrictive LTC constraint
        max_debt_from_ltc = 0.0

        for facility in self.deal.financing.facilities:
            if hasattr(facility, "kind") and facility.kind == "construction":
                if hasattr(facility, "ltc_ratio") and facility.ltc_ratio is not None:
                    # Calculate max debt from this facility's LTC
                    max_debt = total_project_cost * facility.ltc_ratio
                    max_debt_from_ltc = max(max_debt_from_ltc, max_debt)

                elif hasattr(facility, "tranches") and facility.tranches:
                    # For multi-tranche facilities, use highest LTC
                    max_ltc = max(
                        tranche.ltc_threshold for tranche in facility.tranches
                    )
                    max_debt = total_project_cost * max_ltc
                    max_debt_from_ltc = max(max_debt_from_ltc, max_debt)

        # Required equity is total cost minus max available debt
        required_equity = total_project_cost - max_debt_from_ltc
        return max(required_equity, 0)  # Never negative

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

        logger.debug(
            f"_fund_period_uses: period_uses=${period_uses:,.0f}, equity_target=${equity_target:,.0f}, "
            f"equity_funded=${equity_funded:,.0f}, remaining_equity_capacity=${remaining_equity_capacity:,.0f}"
        )

        if remaining_equity_capacity >= period_uses:
            # Fund entirely with equity
            logger.debug(f"  Funding entirely with equity: ${period_uses:,.0f}")
            return period_uses, 0.0
        else:
            # Fund with remaining equity + debt
            period_equity = remaining_equity_capacity
            period_debt_needed = period_uses - period_equity

            logger.debug(f"  Need debt funding: ${period_debt_needed:,.0f}")

            # Get actual debt funding by querying ledger (replaces multi-tranche logic)
            period_debt = self._get_available_debt_funding(
                period_debt_needed, period_idx, ledger
            )

            logger.debug(f"  Got debt funding: ${period_debt:,.0f}")

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

            # For construction/development deals, debt facilities write their
            # full loan commitment as proceeds at origination. This represents the total
            # available funding capacity. We DON'T reduce this by debt service payments -
            # that's a fundamental misunderstanding of how construction loans work.
            #
            # The funding cascade should use this available capacity to fund project uses.
            # Debt service is a separate outflow that happens later, not a reduction in
            # available funding capacity.

            # Calculate total loan capacity from proceeds
            total_loan_capacity = (
                loan_proceeds.sum() if not loan_proceeds.empty else 0.0
            )

            # Track cumulative draws (initialized in _execute_funding_cascade)
            # TODO: Properly track draws vs capacity per facility for multi-tranche support
            if not hasattr(self, "_cumulative_debt_drawn"):
                # Fallback initialization if called outside of funding cascade
                self._cumulative_debt_drawn = 0.0

            # Available capacity is loan capacity minus what we've already drawn
            available_capacity = max(
                0.0, total_loan_capacity - self._cumulative_debt_drawn
            )

            # Return the minimum of what's needed and what's available
            available_funding = min(debt_needed, available_capacity)

            # Update cumulative tracking
            self._cumulative_debt_drawn += available_funding

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

    ###########################################################################
    # DISPOSITION RECORDS
    ###########################################################################

    def _add_disposition_records_to_ledger(
        self, ledger: "Ledger", disposition_proceeds: pd.Series
    ) -> pd.Series:
        """
        Add disposition/exit sale transactions to the ledger WITH DEBT PAYOFF.

        This method now handles disposition as a complex transaction:
        1. Records gross sale proceeds
        2. Calculates and records debt payoffs
        3. Returns NET proceeds available for equity distribution

        Args:
            ledger: The analysis ledger
            disposition_proceeds: Series of GROSS disposition proceeds from valuation

        Returns:
            pd.Series: NET disposition proceeds after debt payoff (for equity distribution)
        """
        if disposition_proceeds is None or (disposition_proceeds == 0).all():
            logger.debug("No disposition proceeds to add to ledger")
            return pd.Series(0.0, index=self.timeline.period_index)

        # Use DispositionAnalyzer to handle the complex transaction
        analyzer = DispositionAnalyzer(self.context)

        # Get debt facilities if they exist
        debt_facilities = []
        if self.deal.financing and self.deal.financing.facilities:
            debt_facilities = self.deal.financing.facilities

        # Process disposition with debt payoff waterfall
        transaction = analyzer.process_disposition(
            gross_proceeds=disposition_proceeds,
            debt_facilities=debt_facilities,
            ledger=ledger,
            transaction_costs=0.0,  # FIXME: Add transaction costs from deal config
            deal_uid=str(self.deal.uid) if self.deal else "unknown",
            asset_uid=str(self.deal.asset.uid)
            if self.deal and self.deal.asset
            else "unknown",
        )

        # Create net proceeds series for equity distribution
        net_proceeds = pd.Series(0.0, index=self.timeline.period_index)

        # Find the disposition period
        disposition_period = (
            disposition_proceeds[disposition_proceeds > 0].index[0]
            if (disposition_proceeds > 0).any()
            else None
        )

        if disposition_period and transaction.net_to_equity > 0:
            net_proceeds[disposition_period] = transaction.net_to_equity

        # Log the impact
        gross_amount = disposition_proceeds.sum()
        total_debt_payoff = sum(transaction.debt_payoffs.values())

        logger.info(
            f"Disposition summary: gross=${gross_amount:,.0f}, debt_payoff=${total_debt_payoff:,.0f}, net_to_equity=${transaction.net_to_equity:,.0f}"
        )

        return net_proceeds
