# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Disposition Analysis Specialist

Handles property disposition as a ledger-recorded transaction: records gross
proceeds, applies a payoff waterfall to debt, accounts for transaction costs,
and computes net proceeds to equity. Ensures a clear audit trail in the ledger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

import pandas as pd

from ...core.ledger import SeriesMetadata
from ...core.primitives import (
    CalculationPhase,
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    FinancingSubcategoryEnum,
    RevenueSubcategoryEnum,
)
from .base import AnalysisSpecialist

if TYPE_CHECKING:
    from performa.core.ledger import Ledger
    from performa.debt.base import DebtFacilityBase

logger = logging.getLogger(__name__)


@dataclass
class DispositionTransaction:
    """
    Represents a property disposition transaction with all components.

    Attributes:
        gross_proceeds: Total sale proceeds before any deductions
        transaction_costs: Broker fees, legal costs, transfer taxes, etc.
        debt_payoffs: Dictionary of facility name to payoff amount
        net_to_equity: Amount available for equity distribution after all obligations
    """

    gross_proceeds: float
    transaction_costs: float = 0.0
    debt_payoffs: Dict[str, float] = field(default_factory=dict)
    net_to_equity: float = 0.0

    def calculate_net_proceeds(self) -> float:
        """Calculate net proceeds after all deductions.

        NOTE: This is redundant with net_to_equity which is already calculated.
        Only kept for test compatibility - consider removing in future.
        """
        total_debt_payoff = sum(self.debt_payoffs.values())
        return self.gross_proceeds - self.transaction_costs - total_debt_payoff


@dataclass
class DispositionAnalyzer(AnalysisSpecialist):
    """
    Specialist service for analyzing property disposition as a complex transaction.

    This service handles the complete disposition transaction including debt payoff
    waterfall, transaction costs, and net proceeds calculation. It ensures that all
    debt obligations are satisfied before equity receives any proceeds, following
    institutional standards for real estate transactions.

    The DispositionAnalyzer implements:
    - Priority-based debt payoff waterfall
    - Accurate outstanding balance calculations
    - Transaction cost deductions
    - Comprehensive ledger recording for audit trail
    - Net proceeds calculation for equity distribution

    Example:
        ```python
        analyzer = DispositionAnalyzer()
        transaction = analyzer.process_disposition(
            gross_proceeds=10_000_000,
            debt_facilities=[construction_loan, permanent_loan],
            transaction_costs=300_000,
            disposition_date=exit_date,
            ledger=ledger,
            deal_uid="deal_123",
            asset_uid="asset_456"
        )

        print(f"Gross proceeds: ${transaction.gross_proceeds:,.0f}")
        print(f"Total debt payoff: ${sum(transaction.debt_payoffs.values()):,.0f}")
        print(f"Net to equity: ${transaction.net_to_equity:,.0f}")
        ```
    """

    def process(self) -> None:
        """
        Settings-driven disposition processing with institutional transaction mechanics.
        Processes transaction mechanics if exit exists, writes to ledger.
        """
        # DispositionAnalyzer processing disposition transaction
        # Initialize with zero proceeds
        net_proceeds = pd.Series(0.0, index=self.timeline.period_index)

        # Get gross proceeds from context (set by valuation pass)
        gross_proceeds = self.context.exit_gross_proceeds
        if gross_proceeds is None or gross_proceeds.sum() == 0:
            return  # No exit to process

        # Use settings for transaction costs - no hidden defaults
        # TODO: add a parameter for cost of sales
        disposition_cost_rate = self.settings.valuation.costs_of_sale_percentage

        # Process the disposition transaction with settings
        # Calculate transaction costs based on settings
        total_transaction_costs = gross_proceeds.sum() * disposition_cost_rate

        transaction = self.process_disposition(
            gross_proceeds=gross_proceeds,
            debt_facilities=self.deal.financing.facilities
            if self.deal.financing
            else [],
            ledger=self.ledger,
            transaction_costs=total_transaction_costs,
            deal_uid=str(self.deal.uid),
            asset_uid=str(self.deal.asset.uid),
        )

        # Set net proceeds in the disposition period
        disp_period = gross_proceeds[gross_proceeds > 0].index[0]
        net_proceeds[disp_period] = transaction.net_to_equity

        # CRITICAL FIX: Record net proceeds as equity distribution to ledger
        # ALWAYS record the disposition distribution, even if it's zero
        # This ensures the transaction is properly recorded in the ledger
        self._record_equity_distribution(
            ledger=self.ledger,
            amount=transaction.net_to_equity,
            disposition_date=disp_period,
            deal_uid=str(self.deal.uid),
            asset_uid=str(self.deal.asset.uid),
        )
        
        # Store disposition date in context for other analysts to check
        # This prevents post-disposition phantom transactions
        self.context.disposition_date = disp_period

        # Disposition processing complete - all transactions written to ledger

    def process_disposition(
        self,
        gross_proceeds: pd.Series,
        debt_facilities: List["DebtFacilityBase"],
        ledger: "Ledger",
        transaction_costs: float = 0.0,
        disposition_date: Optional[pd.Period] = None,
        deal_uid: str = "unknown",
        asset_uid: str = "unknown",
    ) -> DispositionTransaction:
        """
        Process a property disposition with debt payoff waterfall.

        This method handles the complete disposition transaction:
        1. Records gross sale proceeds
        2. Calculates outstanding debt balances
        3. Applies payoff waterfall in priority order
        4. Deducts transaction costs
        5. Records all transactions to ledger
        6. Returns net proceeds for equity distribution

        Args:
            gross_proceeds: Series of disposition proceeds (typically single period)
            debt_facilities: List of debt facilities to pay off
            ledger: Ledger for transaction recording
            transaction_costs: Total transaction costs (broker fees, legal, etc.)
            disposition_date: Date of disposition (uses last non-zero proceeds date if not provided)
            deal_uid: Deal unique identifier for ledger recording
            asset_uid: Asset unique identifier for ledger recording

        Returns:
            DispositionTransaction with all components and net proceeds
        """
        # Determine disposition date
        if disposition_date is None:
            # Find the period with disposition proceeds
            non_zero_proceeds = gross_proceeds[gross_proceeds > 0]
            if not non_zero_proceeds.empty:
                disposition_date = non_zero_proceeds.index[0]
            else:
                logger.warning("No disposition proceeds found")
                return DispositionTransaction(gross_proceeds=0.0)

        # Get gross proceeds amount
        gross_amount = gross_proceeds.sum()

        if gross_amount <= 0:
            logger.warning(f"No positive disposition proceeds: ${gross_amount:,.0f}")
            return DispositionTransaction(gross_proceeds=0.0)

        logger.info(f"Processing disposition: ${gross_amount:,.0f} gross proceeds")

        # Initialize transaction
        transaction = DispositionTransaction(
            gross_proceeds=gross_amount, transaction_costs=transaction_costs
        )

        # Step 1: Record gross sale proceeds to ledger
        self._record_gross_proceeds(ledger, gross_proceeds, deal_uid, asset_uid)

        # Step 2: Calculate and record transaction costs
        if transaction_costs > 0:
            self._record_transaction_costs(
                ledger, transaction_costs, disposition_date, deal_uid, asset_uid
            )

        # Step 3: Calculate outstanding debt balances and apply payoff waterfall
        available_proceeds = gross_amount - transaction_costs

        for facility in debt_facilities:
            if available_proceeds <= 0:
                logger.warning(
                    f"Insufficient proceeds for {facility.name} payoff. "
                    f"Available: ${available_proceeds:,.0f}"
                )
                break

            # Get outstanding balance
            outstanding = self._get_facility_outstanding_balance(
                facility, disposition_date, ledger
            )

            if outstanding > 0:
                # Determine payoff amount (limited by available proceeds)
                payoff_amount = min(outstanding, available_proceeds)

                # Record payoff
                transaction.debt_payoffs[facility.name] = payoff_amount

                # Record to ledger
                self._record_debt_payoff(
                    ledger,
                    facility.name,
                    payoff_amount,
                    disposition_date,
                    deal_uid,
                    asset_uid,
                )

                # Reduce available proceeds
                available_proceeds -= payoff_amount

                logger.info(
                    f"Paid off {facility.name}: ${payoff_amount:,.0f} "
                    f"(Outstanding was ${outstanding:,.0f})"
                )

        # Step 4: Calculate net to equity
        transaction.net_to_equity = available_proceeds

        # Log summary
        total_debt_payoff = sum(transaction.debt_payoffs.values())
        logger.info(
            f"Disposition summary: "
            f"Gross ${gross_amount:,.0f} - "
            f"Costs ${transaction_costs:,.0f} - "
            f"Debt ${total_debt_payoff:,.0f} = "
            f"Net to equity ${transaction.net_to_equity:,.0f}"
        )

        return transaction

    def _get_facility_outstanding_balance(
        self,
        facility: "DebtFacilityBase",
        disposition_date: pd.Period,
        ledger: "Ledger",
    ) -> float:
        """
        Get outstanding balance for a debt facility at disposition.

        CRITICAL: This now properly checks if a facility was already paid off
        (e.g., construction loan paid during refinancing) by querying the ledger.

        Args:
            facility: Debt facility to get balance for
            disposition_date: Date of disposition
            ledger: Ledger containing debt transactions

        Returns:
            Outstanding balance amount (0 if already paid off)
        """
        # CRITICAL FIX: Check ledger for actual outstanding balance
        # Don't rely on facility's get_outstanding_balance which may not
        # account for refinancing payoffs

        try:
            ledger_df = ledger.ledger_df()

            # Check if this is a construction/renovation facility that was paid off via refinancing
            # Look for refinancing payoff entries in debt service
            if "Construction" in facility.name or "Renovation" in facility.name:
                # Check for refinancing payoff
                refinance_payoff_mask = (
                    (ledger_df["item_name"].str.contains(facility.name, na=False))
                    & (
                        ledger_df["item_name"].str.contains(
                            "Refinancing Payoff", na=False
                        )
                    )
                    & (
                        ledger_df["subcategory"]
                        == FinancingSubcategoryEnum.REFINANCING_PAYOFF
                    )
                )
                if refinance_payoff_mask.any():
                    # Construction/renovation loan was paid off during refinancing
                    payoff_amount = abs(
                        ledger_df[refinance_payoff_mask]["amount"].sum()
                    )
                    logger.debug(
                        f"{facility.name} was paid off during refinancing: ${payoff_amount:,.0f}"
                    )
                    return 0.0

            # Get loan proceeds for this facility
            proceeds_mask = (
                ledger_df["item_name"].str.contains(facility.name, na=False)
            ) & (ledger_df["subcategory"] == FinancingSubcategoryEnum.LOAN_PROCEEDS)
            proceeds = ledger_df[proceeds_mask]["amount"].sum()

            # Get all debt service payments using disaggregated I&P approach
            service_mask = (
                ledger_df["item_name"].str.contains(facility.name, na=False)
            ) & (
                (ledger_df["subcategory"] == FinancingSubcategoryEnum.INTEREST_PAYMENT)
                | (
                    ledger_df["subcategory"]
                    == FinancingSubcategoryEnum.PRINCIPAL_PAYMENT
                )
            )
            # Debt service is negative in ledger
            total_service = abs(ledger_df[service_mask]["amount"].sum())

            # For construction loans paid off via refinancing, proceeds should be 0
            # For permanent loans, proceeds > 0 and we need to check if they're interest-only

            if proceeds <= 0:
                # No proceeds recorded - likely paid off or not yet drawn
                return 0.0

            # For permanent loans, calculate actual remaining balance after principal payments
            if "Permanent" in facility.name or hasattr(facility, "amortization_months"):
                # NEW: Calculate remaining balance after principal payments
                # Get principal payments that have reduced the loan balance
                principal_mask = (
                    ledger_df["item_name"].str.contains(facility.name, na=False)
                ) & (
                    ledger_df["subcategory"]
                    == FinancingSubcategoryEnum.PRINCIPAL_PAYMENT
                )
                total_principal_paid = abs(ledger_df[principal_mask]["amount"].sum())

                # Original loan amount
                original_loan = (
                    facility.loan_amount
                    if hasattr(facility, "loan_amount") and facility.loan_amount
                    else proceeds
                )

                # Remaining balance = Original loan - Principal payments
                remaining_balance = max(0, original_loan - total_principal_paid)

                logger.debug(
                    f"{facility.name}: Original ${original_loan:,.0f}, "
                    f"Principal paid ${total_principal_paid:,.0f}, "
                    f"Remaining ${remaining_balance:,.0f}"
                )

                return remaining_balance

            # For other loans, calculate based on proceeds - principal payments
            # This is simplified - ideally track principal separately from interest
            outstanding = proceeds

            logger.debug(
                f"{facility.name}: Proceeds ${proceeds:,.0f}, "
                f"Service ${total_service:,.0f}, "
                f"Outstanding ${outstanding:,.0f}"
            )

            return outstanding if outstanding > 0 else 0.0

        except Exception as e:
            logger.warning(
                f"Error calculating outstanding balance for {facility.name}: {e}"
            )
            # All debt facilities implement get_outstanding_balance
            balance = facility.get_outstanding_balance(disposition_date)
            # Cap at loan_amount to avoid wild estimates
            if facility.loan_amount and balance > facility.loan_amount:
                return facility.loan_amount
            return max(balance, 0.0)

    def _record_gross_proceeds(
        self, ledger: "Ledger", gross_proceeds: pd.Series, deal_uid: str, asset_uid: str
    ) -> None:
        """Record gross sale proceeds to ledger."""
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,  # Correct: sale proceeds are revenue inflows
            subcategory=RevenueSubcategoryEnum.SALE,  # Sale proceeds
            item_name="Exit Sale Proceeds (Gross)",
            source_id=deal_uid,
            asset_id=asset_uid,
            pass_num=5,  # Disposition pass
        )

        ledger.add_series(gross_proceeds, metadata)

        logger.debug(f"Recorded gross proceeds: ${gross_proceeds.sum():,.0f}")

    def _record_transaction_costs(
        self,
        ledger: "Ledger",
        costs: float,
        disposition_date: pd.Period,
        deal_uid: str,
        asset_uid: str,
    ) -> None:
        """Record transaction costs to ledger."""
        # Transaction costs are negative (outflow)
        cost_series = pd.Series([-costs], index=[disposition_date])

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.CAPITAL,
            subcategory=CapitalSubcategoryEnum.TRANSACTION_COSTS,
            item_name="Disposition Transaction Costs",
            source_id=deal_uid,
            asset_id=asset_uid,
            pass_num=CalculationPhase.VALUATION.value,
        )

        ledger.add_series(cost_series, metadata)

        logger.debug(f"Recorded transaction costs: ${costs:,.0f}")

    def _record_equity_distribution(
        self,
        ledger: "Ledger",
        amount: float,
        disposition_date: pd.Period,
        deal_uid: str,
        asset_uid: str,
    ) -> None:
        """Record net disposition proceeds as equity distribution to partners."""
        # Create equity distribution series (always record, even if zero)
        equity_distribution_series = pd.Series(
            [-amount],  # Negative = outflow from deal to equity partners
            index=pd.PeriodIndex([disposition_date], freq="M"),
            name="Disposition Proceeds",
        )

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,
            subcategory=FinancingSubcategoryEnum.EQUITY_DISTRIBUTION,
            item_name="Disposition Proceeds Distribution",
            source_id=deal_uid,
            asset_id=asset_uid,
            pass_num=5,  # Disposition pass
            entity_type="GP,LP",  # Distribution to all equity partners
        )

        ledger.add_series(equity_distribution_series, metadata)

        if amount == 0:
            logger.info(
                f"💰 Recorded $0 disposition distribution (all proceeds went to debt payoff)"
            )
        else:
            logger.info(f"💰 Recorded equity distribution: ${amount:,.0f} to partners")

    def _record_debt_payoff(
        self,
        ledger: "Ledger",
        facility_name: str,
        payoff_amount: float,
        disposition_date: pd.Period,
        deal_uid: str,
        asset_uid: str,
    ) -> None:
        """Record debt payoff to ledger."""
        # Debt payoff is negative (outflow to pay debt)
        payoff_series = pd.Series([-payoff_amount], index=[disposition_date])

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,
            subcategory=FinancingSubcategoryEnum.PREPAYMENT,
            item_name=f"{facility_name} - Disposition Payoff",
            source_id=deal_uid,
            asset_id=asset_uid,
            pass_num=CalculationPhase.VALUATION.value,
        )

        ledger.add_series(payoff_series, metadata)

        logger.debug(f"Recorded debt payoff for {facility_name}: ${payoff_amount:,.0f}")
