# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Debt Analysis Specialist

Provides debt facility processing (construction and permanent), refinancing
integration, DSCR calculations, and covenant metrics. All transactions are
recorded to the ledger; queries against the ledger provide inputs for metrics.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np
import pandas as pd

from performa.core.ledger.records import SeriesMetadata
from performa.core.primitives import (
    CalculationPhase,
    Timeline,
)
from performa.core.primitives.enums import (
    CashFlowCategoryEnum,
    FinancingSubcategoryEnum,
)
from performa.debt.construction import ConstructionFacility
from performa.debt.permanent import PermanentFacility

# Deprecated result imports removed - full ledger-driven now
from .base import AnalysisSpecialist

if TYPE_CHECKING:
    from performa.core.ledger import Ledger
    from performa.core.primitives import Timeline


logger = logging.getLogger(__name__)


@dataclass
class DebtAnalyzer(AnalysisSpecialist):
    """
    Analyze debt facilities and financing structure.

    Processes facilities (which write transactions to the ledger), then handles
    refinancing and computes DSCR metrics from ledger queries.
    """

    # Fields inherited from AnalysisSpecialist base class:
    # - context (DealContext)
    # - deal, timeline, settings, ledger (via properties)
    # - queries (LedgerQueries)

    def process(self) -> None:
        """
        Settings-driven debt processing with institutional-grade covenant monitoring.
        Always processes facilities and writes debt transactions to ledger.

        Three-phase processing:
        1. Debt service calculations (compute_cf)
        2. Covenant processing (process_covenants)
        3. Refinancing transactions

        Covenant processing happens after debt service so that ledger data
        (NOI, debt service) is available for covenant calculations.
        """
        # Handle no financing case internally
        if not self.deal.financing:
            return  # No debt facilities to process

        # Note: Facility-specific covenant settings extracted from facility.ongoing_dscr_min, etc.

        # PHASE 1: Process debt service for each facility
        for facility in self.deal.financing.facilities:
            # Facility writes debt transactions to ledger
            facility.compute_cf(self.context)

        # PHASE 2: Process covenant constraints (NEW)
        # Must happen AFTER compute_cf() so debt service is in ledger
        for facility in self.deal.financing.facilities:
            # Delegate covenant processing to facility
            # (Facility delegates to composed covenant objects)
            facility.process_covenants(self.context)

        # PHASE 3: Handle refinancing AFTER facilities and covenants processed
        # This ensures construction loan amounts are in the ledger
        if (
            self.deal.financing.has_construction_financing
            and self.deal.financing.has_permanent_financing
        ):
            try:
                # Get data for refinancing calculations (populated by valuation pass)
                property_value_series = self.context.refi_property_value
                noi_series = self.context.noi_series

                # Process refinancing transactions
                self._process_refinancing_transactions(
                    property_value_series=property_value_series,
                    noi_series=noi_series,
                    ledger=self.context.ledger,
                )

            except Exception as e:
                # Log but don't fail - refinancing is important but not critical
                logger.warning(f"Failed to process refinancing: {e}")
                logger.warning(f"Traceback: {traceback.format_exc()}")

        # Debt processing complete - all facility transactions written to ledger

    ###########################################################################
    # DEBT SERVICE CALCULATIONS
    ###########################################################################

    def _calculate_enhanced_debt_service(self, permanent_facility) -> pd.Series:
        """
        Calculate enhanced debt service for permanent facilities with institutional features.

        This method implements sophisticated debt service calculations that mirror institutional
        lending practices, including support for interest-only periods, floating rate indexes,
        and dynamic refinancing scenarios commonly used in commercial real estate financing.

        Enhanced features supported:
        - **Interest-Only Periods**: Supports I/O periods during initial loan terms
        - **Dynamic Floating Rates**: Integrates with rate index curves (SOFR, LIBOR, etc.)
        - **Refinancing Integration**: Calculates debt service starting from refinancing dates
        - **Amortization Scheduling**: Proper institutional-grade amortization calculations
        - **Timeline Alignment**: Ensures debt service aligns with project timeline

        The method handles complex scenarios where permanent facilities are originated
        through refinancing transactions, requiring careful timeline management and
        loan amount determination from refinancing events.

        Args:
            permanent_facility: PermanentFacility object with enhanced institutional features
                               including refinancing timing, loan terms, and rate specifications

        Returns:
            pd.Series containing enhanced debt service payments aligned with the project
            timeline, with proper handling of refinancing timing and rate dynamics

        Example:
            ```python
            # For a refinanced permanent loan
            debt_service = analyzer._calculate_enhanced_debt_service(permanent_facility)

            # Analyze debt service pattern
            print(f"Total debt service: ${debt_service.sum():,.0f}")
            print(f"Average payment: ${debt_service.mean():,.0f}")
            print(f"Peak payment: ${debt_service.max():,.0f}")
            ```
        """
        try:
            # Check if this facility has dynamic refinancing
            if permanent_facility.refinance_timing is not None:
                # For facilities that are originated via refinancing, we need to calculate
                # debt service starting from the refinance timing
                refinance_period_idx = permanent_facility.refinance_timing - 1
                if refinance_period_idx < len(self.timeline.period_index):
                    # Create a sub-timeline starting from refinancing
                    refinance_start = self.timeline.period_index[refinance_period_idx]

                    # Calculate loan amount from refinancing transaction
                    loan_amount = self._get_refinanced_loan_amount(permanent_facility)

                    if loan_amount > 0:
                        # Create timeline for the permanent loan term
                        loan_timeline = Timeline(
                            start_date=refinance_start,
                            duration_months=permanent_facility.loan_term_years * 12,
                        )

                        # Calculate enhanced amortization
                        amortization = permanent_facility.calculate_amortization(
                            timeline=loan_timeline,
                            loan_amount=loan_amount,
                            index_curve=self._get_rate_index_curve(),
                        )

                        # Extract debt service from amortization
                        schedule, _ = amortization.amortization_schedule
                        debt_service_series = schedule["Total Payment"]

                        # Align with main timeline
                        full_debt_service = pd.Series(
                            0.0, index=self.timeline.period_index
                        )
                        for i, payment in enumerate(debt_service_series):
                            timeline_idx = refinance_period_idx + i
                            if timeline_idx < len(self.timeline.period_index):
                                full_debt_service.iloc[timeline_idx] = payment

                        return full_debt_service

            # Fallback to standard debt service calculation
            return permanent_facility.calculate_debt_service(self.timeline)

        except Exception as e:
            # Log warning and fallback to basic calculation
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Enhanced debt service calculation failed for {permanent_facility.name}: {e}"
            )
            return permanent_facility.calculate_debt_service(self.timeline)

    def _get_refinanced_loan_amount(self, permanent_facility) -> float:
        """Get the loan amount from refinancing transactions for this facility."""
        # financing_analysis doesn't exist anymore - just use facility's loan amount
        # TODO: If we need dynamic refinancing amounts, implement a different approach

        # Fallback to facility's specified loan amount
        return permanent_facility.loan_amount or 0.0

    def _get_rate_index_curve(
        self, start_rate: float = 0.045, end_rate: float = 0.055
    ) -> pd.Series:
        """
        Get rate index curve for dynamic rate calculations.

        Args:
            start_rate: Starting rate for the curve (default: 4.5%)
            end_rate: Ending rate for the curve (default: 5.5%)

        In a real implementation, this would come from market data or user input.
        For now, we'll create a reasonable SOFR curve.
        """
        # Create a sample SOFR curve with configurable start and end rates
        periods = len(self.timeline.period_index)

        # Linear interpolation
        rates = np.linspace(start_rate, end_rate, periods)

        return pd.Series(rates, index=self.timeline.period_index)

    def _process_refinancing_transactions(
        self, property_value_series: pd.Series, noi_series: pd.Series, ledger: "Ledger"
    ) -> None:
        """
        Process refinancing transactions and integrate cash flow impacts.

        This method handles the complete refinancing workflow including:
        - Refinancing transaction calculation
        - Cash flow event processing
        - Covenant monitoring setup for new loans

        Args:
            property_value_series: Property value time series for refinancing analysis
            noi_series: NOI time series for covenant monitoring
            ledger: Ledger instance for recording refinancing transactions
        """
        # Ledger is available via self.context.ledger
        try:
            # Calculate refinancing transactions with enhanced data
            refinancing_transactions = (
                self.deal.financing.calculate_refinancing_transactions(
                    timeline=self.timeline,
                    property_value_series=property_value_series,
                    noi_series=noi_series,
                    financing_cash_flows=None,  # Will be provided in future iterations
                )
            )
            # Don't store in financing_analysis - it doesn't exist anymore

            # Log refinancing transactions
            if refinancing_transactions:
                logger.info(
                    f"Found {len(refinancing_transactions)} refinancing transactions"
                )
                for trans in refinancing_transactions:
                    logger.info(
                        f"  - {trans.get('transaction_type')}: payoff=${trans.get('payoff_amount', 0):,.0f}, new=${trans.get('new_loan_amount', 0):,.0f}"
                    )
            else:
                logger.info("No refinancing transactions found")

            # Process refinancing cash flow impacts
            self._process_refinancing_cash_flows(refinancing_transactions)

        except Exception as e:
            # Log the error but continue with empty transactions
            logger.error(f"ERROR in refinancing: {str(e)}")
            logger.error(traceback.format_exc())
            # Don't store in financing_analysis - it doesn't exist anymore

    def _process_refinancing_cash_flows(
        self, refinancing_transactions: List[Dict[str, Any]]
    ) -> None:
        """
        Process refinancing transactions and integrate cash flow impacts.

        This method handles the cash flow events from refinancing:
        - Loan payoffs (negative cash flow)
        - New loan proceeds (positive cash flow)
        - Net proceeds to borrower
        - Setup covenant monitoring for new loans

        Args:
            refinancing_transactions: List of refinancing transaction dictionaries
        """
        if not refinancing_transactions:
            return

        # Initialize refinancing cash flow tracking (store locally, not on result)
        refinancing_cash_flows = {
            "loan_payoffs": pd.Series(0.0, index=self.timeline.period_index),
            "new_loan_proceeds": pd.Series(0.0, index=self.timeline.period_index),
            "closing_costs": pd.Series(0.0, index=self.timeline.period_index),
            "net_refinancing_proceeds": pd.Series(
                0.0, index=self.timeline.period_index
            ),
        }

        for transaction in refinancing_transactions:
            transaction_date = transaction.get("transaction_date")

            if transaction_date in self.timeline.period_index:
                # Record cash flow events
                payoff_amount = transaction.get("payoff_amount", 0.0)
                new_loan_amount = transaction.get("new_loan_amount", 0.0)
                closing_costs = transaction.get("closing_costs", 0.0)
                net_proceeds = transaction.get("net_proceeds", 0.0)

                # Update cash flow series
                refinancing_cash_flows["loan_payoffs"][
                    transaction_date
                ] = -payoff_amount
                refinancing_cash_flows["new_loan_proceeds"][transaction_date] = (
                    new_loan_amount
                )
                refinancing_cash_flows["closing_costs"][
                    transaction_date
                ] = -closing_costs
                refinancing_cash_flows["net_refinancing_proceeds"][transaction_date] = (
                    net_proceeds
                )

                # Log payoff amount
                logger.info(
                    f"Initial payoff_amount for {transaction_date}: ${payoff_amount:,.0f}"
                )

                # Handle construction loan repayment
                # If payoff_amount is -1, we need to get it from the ledger
                if payoff_amount == -1.0 and self.context.ledger:
                    # Get actual construction loan amount from ledger (principal + capitalized interest)
                    ledger_df = self.context.ledger.ledger_df()

                    # Get loan proceeds (principal)
                    const_proceeds = ledger_df[
                        (ledger_df["item_name"].str.contains("Construction", na=False))
                        & (
                            ledger_df["subcategory"]
                            == FinancingSubcategoryEnum.LOAN_PROCEEDS
                        )
                    ]
                    payoff_amount = (
                        const_proceeds["amount"].sum()
                        if not const_proceeds.empty
                        else 0.0
                    )

                    # Add capitalized interest to payoff amount
                    # Capitalized interest increases the loan balance and must be repaid
                    cap_interest = ledger_df[
                        (
                            ledger_df["item_name"].str.contains(
                                "Capitalized Interest", na=False
                            )
                        )
                    ]
                    if not cap_interest.empty:
                        capitalized_amount = abs(cap_interest["amount"].sum())
                        payoff_amount += capitalized_amount
                    else:
                        capitalized_amount = 0.0

                    # CRITICAL: Subtract sweep prepayments from outstanding balance
                    # Prepayments reduce the construction loan balance, so payoff should be lower
                    sweep_prepayments = ledger_df[
                        (ledger_df["item_name"].str.contains("Construction", na=False))
                        & (
                            ledger_df["subcategory"]
                            == FinancingSubcategoryEnum.SWEEP_PREPAYMENT
                        )
                    ]
                    prepayment_amount = (
                        abs(sweep_prepayments["amount"].sum())
                        if not sweep_prepayments.empty
                        else 0.0
                    )

                    if prepayment_amount > 0:
                        logger.info(
                            f"Construction loan payoff: ${const_proceeds['amount'].sum():,.0f} principal + "
                            f"${capitalized_amount:,.0f} capitalized interest - "
                            f"${prepayment_amount:,.0f} sweep prepayments = "
                            f"${payoff_amount - prepayment_amount:,.0f} outstanding balance"
                        )
                        payoff_amount -= prepayment_amount
                    else:
                        logger.info(
                            f"Construction loan payoff: ${const_proceeds['amount'].sum():,.0f} principal + "
                            f"${capitalized_amount:,.0f} capitalized interest = "
                            f"${payoff_amount:,.0f} outstanding balance"
                        )

                    # Update the transaction record
                    transaction["payoff_amount"] = payoff_amount

                # REAL LOAN PAYOFF APPROACH FOR REFINANCING
                # Actually pay off the old loan instead of just adjusting
                if payoff_amount > 0 and self.context.ledger:
                    # Record the actual loan PAYOFF as debt service (negative)
                    # This truly eliminates the old loan liability
                    payoff_series = pd.Series(
                        [-payoff_amount],  # Negative debt service (outflow)
                        index=[transaction_date],
                    )

                    # Find the construction facility being paid off
                    construction_facility_name = "Construction Loan"
                    for facility in self.deal.financing.facilities:
                        if (
                            "Construction" in facility.name
                            or "Renovation" in facility.name
                        ):
                            construction_facility_name = facility.name
                            break

                    # Record as refinancing payoff for the construction loan
                    payoff_metadata = SeriesMetadata(
                        category=CashFlowCategoryEnum.FINANCING,
                        subcategory=FinancingSubcategoryEnum.REFINANCING_PAYOFF,
                        item_name=f"{construction_facility_name} - Refinancing Payoff",
                        source_id=self.deal.uid,
                        asset_id=self.deal.asset.uid,
                        pass_num=CalculationPhase.FINANCING.value,
                    )

                    # Add payoff to ledger
                    self.context.ledger.add_series(payoff_series, payoff_metadata)
                    logger.info(
                        f"✅ Recorded loan payoff: ${payoff_amount:,.0f} "
                        f"for {construction_facility_name} via refinancing"
                    )

                    # Record new loan proceeds from refinancing
                    if new_loan_amount > 0:
                        proceeds_series = pd.Series(
                            [new_loan_amount], index=[transaction_date]
                        )

                        proceeds_metadata = SeriesMetadata(
                            category=CashFlowCategoryEnum.FINANCING,
                            subcategory=FinancingSubcategoryEnum.REFINANCING_PROCEEDS,
                            item_name=f"{transaction.get('new_facility', 'Permanent Loan')} - Refinancing Proceeds",
                            source_id=self.deal.uid,
                            asset_id=self.deal.asset.uid,
                            pass_num=CalculationPhase.FINANCING.value,
                        )

                        self.ledger.add_series(proceeds_series, proceeds_metadata)
                        logger.info(
                            f"✅ Recorded refinancing proceeds: ${new_loan_amount:,.0f} "
                            f"for {transaction.get('new_facility', 'permanent loan')}"
                        )

                    # Distribute net refinancing proceeds to equity partners
                    # CRITICAL: Recalculate net_proceeds here after payoff_amount is updated
                    # Net proceeds = New loan - Payoff - Closing costs
                    actual_net_proceeds = (
                        new_loan_amount - payoff_amount - closing_costs
                    )

                    if actual_net_proceeds > 0:
                        # Positive net proceeds = cash-out to equity
                        distribution_series = pd.Series(
                            [
                                -actual_net_proceeds
                            ],  # Negative = outflow from deal to equity
                            index=[transaction_date],
                        )

                        distribution_metadata = SeriesMetadata(
                            category=CashFlowCategoryEnum.FINANCING,
                            subcategory=FinancingSubcategoryEnum.EQUITY_DISTRIBUTION,
                            item_name="Refinancing Cash-Out Distribution",
                            source_id=self.deal.uid,
                            asset_id=self.deal.asset.uid,
                            pass_num=CalculationPhase.FINANCING.value,
                            entity_type="GP,LP",  # Distribution to all equity partners
                        )

                        self.ledger.add_series(
                            distribution_series, distribution_metadata
                        )
                        logger.info(
                            f"💰 Recorded refinancing cash-out distribution to equity: ${actual_net_proceeds:,.0f}"
                        )

                    elif actual_net_proceeds < 0:
                        # Negative net proceeds = equity contribution required
                        # When permanent loan doesn't cover construction payoff, equity must fill gap
                        contribution_series = pd.Series(
                            [
                                abs(actual_net_proceeds)
                            ],  # Positive = inflow to deal from equity
                            index=[transaction_date],
                        )

                        contribution_metadata = SeriesMetadata(
                            category=CashFlowCategoryEnum.FINANCING,
                            subcategory=FinancingSubcategoryEnum.EQUITY_CONTRIBUTION,
                            item_name="Refinancing Equity Contribution",
                            source_id=self.deal.uid,
                            asset_id=self.deal.asset.uid,
                            pass_num=CalculationPhase.FINANCING.value,
                            entity_type="GP,LP",  # Contribution from all equity partners
                        )

                        self.ledger.add_series(
                            contribution_series, contribution_metadata
                        )
                        logger.info(
                            f"💸 Recorded refinancing equity contribution: ${abs(actual_net_proceeds):,.0f} "
                            f"(permanent loan insufficient to cover construction payoff)"
                        )

                # Setup covenant monitoring for new permanent loans
                covenant_monitoring = transaction.get("covenant_monitoring", {})
                # TODO: Integrate covenant monitoring with the new permanent loan

    def _calculate_dscr_time_series(
        self, noi_series: pd.Series, debt_service_series: pd.Series
    ) -> pd.Series:
        """
        Calculate DSCR time series with proper handling of edge cases.

        Args:
            noi_series: Net Operating Income time series
            debt_service_series: Total debt service time series

        Returns:
            DSCR time series with institutional-grade calculation
        """

        # Calculate DSCR for each period where debt service is positive
        # DSCR = NOI / Debt Service
        # Handle division by zero and negative values appropriately

        dscr_series = pd.Series(index=self.timeline.period_index, dtype=float)

        for period in self.timeline.period_index:
            noi = noi_series.get(period, 0.0)
            debt_service = debt_service_series.get(period, 0.0)

            if debt_service > 0:
                dscr = noi / debt_service
                # Cap extremely high DSCR values for practical analysis
                dscr_series[period] = min(dscr, 100.0)  # Cap at 100x coverage
            elif debt_service == 0 and noi >= 0:
                # No debt service but positive NOI = infinite coverage (set to high value)
                dscr_series[period] = 100.0
            else:
                # Negative NOI or other edge cases
                dscr_series[period] = 0.0

        return dscr_series

    def _extract_facility_covenant_thresholds(self) -> List[float]:
        """
        Extract DSCR covenant thresholds from deal facilities.

        Uses explicit type-based dispatch - we know our facility types and their capabilities.
        This is important for covenant monitoring!

        Returns:
            List of covenant thresholds from facilities, or empty list if none found
        """

        thresholds = []

        if self.deal.financing and self.deal.financing.facilities:
            for facility in self.deal.financing.facilities:
                if isinstance(facility, PermanentFacility):
                    # PermanentFacility has covenant settings
                    if facility.ongoing_dscr_min is not None:
                        thresholds.append(facility.ongoing_dscr_min)
                    if facility.dscr_hurdle is not None:
                        thresholds.append(facility.dscr_hurdle)

                elif isinstance(facility, ConstructionFacility):
                    # ConstructionFacility typically doesn't have ongoing covenant monitoring
                    # (Construction loans are usually interest-only with no DSCR covenants)
                    pass

                # If we add more facility types, handle them explicitly here

        # Remove duplicates and sort
        return sorted(list(set(thresholds))) if thresholds else []

    def calculate_dscr_metrics(self) -> Dict[str, Any]:
        """
        Calculate comprehensive DSCR metrics for covenant monitoring.

        THIS IS CRITICAL FOR LENDER REQUIREMENTS!
        Returns DSCR time series and covenant analysis.

        Returns:
            Dict containing:
            - dscr_series: Period-by-period DSCR values
            - minimum_dscr: Minimum DSCR across all periods
            - average_dscr: Average DSCR
            - periods_below_threshold: Count of periods below each covenant threshold
            - covenant_breaches: List of periods where covenants are breached
        """
        # If deal has no financing, return empty metrics
        if not self.deal.financing or not self.deal.financing.facilities:
            return {
                "dscr_series": None,
                "minimum_dscr": None,
                "average_dscr": None,
                "median_dscr": None,
                "covenant_analysis": {},
                "trend_slope": None,
                "trend_direction": None,
            }

        # Get NOI from ledger
        noi_series = self.queries.noi()

        # Get debt service from ledger
        debt_service = self.queries.debt_service()

        # Calculate DSCR time series
        dscr_series = self._calculate_dscr_time_series(noi_series, debt_service)

        # Get facility-specific covenant thresholds
        facility_thresholds = self._extract_facility_covenant_thresholds()

        # Calculate comprehensive metrics
        metrics = {
            "dscr_series": dscr_series,
            "minimum_dscr": float(dscr_series.min()) if not dscr_series.empty else None,
            "average_dscr": float(dscr_series.mean())
            if not dscr_series.empty
            else None,
            "median_dscr": float(dscr_series.median())
            if not dscr_series.empty
            else None,
        }

        # Covenant analysis - use facility-specific or standard thresholds
        covenant_thresholds = (
            facility_thresholds
            if facility_thresholds
            else [1.0, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.5]
        )

        metrics["covenant_analysis"] = {}
        for threshold in covenant_thresholds:
            periods_below = (dscr_series < threshold).sum()
            metrics["covenant_analysis"][f"periods_below_{threshold:.2f}"] = int(
                periods_below
            )

            # Find specific breach periods
            breach_periods = dscr_series[dscr_series < threshold].index.tolist()
            if breach_periods:
                metrics["covenant_analysis"][f"breach_periods_{threshold:.2f}"] = (
                    breach_periods
                )

        # Trend analysis
        if len(dscr_series) > 1:
            x = range(len(dscr_series))
            trend_slope = np.polyfit(x, dscr_series.values, 1)[0]
            metrics["trend_slope"] = float(trend_slope)
            metrics["trend_direction"] = (
                "improving"
                if trend_slope > 0
                else "declining"
                if trend_slope < 0
                else "stable"
            )

        return metrics
