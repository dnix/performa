# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Debt covenant implementations.

This module contains covenant constraint classes that enforce lender requirements
on debt facilities. Covenants are composed into facilities and processed after
debt service calculations.

Architecture:
- Each covenant is a standalone class with single responsibility
- Covenants have access to ledger for querying deal metrics (NOI, DSCR, etc.)
- Covenants post their own transactions to the ledger
- Facilities compose covenants and delegate processing to them

Current Covenants:
- CashSweep: Trap or prepay excess operating cash

Future Extensibility (TODO):
- ReserveAccount: Tax/insurance/CapEx escrow funding
- DistributionBlock: Prevent distributions if covenants violated
- MandatoryPrepayment: Require prepayment on specific events
- Lockbox: Revenue flows to lender-controlled account
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd
from pydantic import Field

from ..core.ledger import SeriesMetadata
from ..core.ledger.queries import LedgerQueries
from ..core.primitives import (
    CalculationPhase,
    CashFlowCategoryEnum,
    FinancingSubcategoryEnum,
    Model,
    SweepMode,
)

if TYPE_CHECKING:
    from ..deal.orchestrator import DealContext

logger = logging.getLogger(__name__)


@dataclass
class SweepAdjustment:
    """
    Result of sweep waterfall calculation.

    Attributes:
        to_interest: Sweep cash applied to interest (reduces reserve draw)
        to_principal: Sweep cash applied to principal (prepayment)
    """

    to_interest: float
    to_principal: float


# TODO: Future extensibility - base class for all covenants
# class CovenantBase(Model):
#     """Base class for all debt covenant constraints."""
#     def process(self, context: DealContext, facility_name: str) -> None:
#         raise NotImplementedError


class CashSweep(Model):
    """
    Lender cash sweep covenant.

    Traps or prepays excess operating cash until a specific date/event.
    Common in construction loans to prevent distributions during lease-up.

    Modes:
        TRAP: Hold excess cash in escrow, release when sweep ends
        PREPAY: Apply excess cash to principal prepayment immediately

    Economics:
        TRAP: Cash comes back later (timing drag on IRR)
        PREPAY: Reduces loan balance → lower interest → higher IRR

    Attributes:
        mode: Sweep mode (TRAP or PREPAY)
        end_month: Month when sweep ends (1-based), typically set to stabilization
            or refinancing month. Automatically set by helper functions.

    Example:
        Construction loan with 12-month sweep until refinancing:

        sweep = CashSweep(
            mode=SweepMode.TRAP,
            end_month=42  # Month when refinancing occurs
        )

        construction = ConstructionFacility(
            ...,
            cash_sweep=sweep
        )
    """

    mode: SweepMode = Field(
        ..., description="Sweep mode: TRAP (escrow) or PREPAY (mandatory prepayment)"
    )

    end_month: int = Field(
        ...,
        ge=1,
        description=(
            "Month when sweep ends (1-based). "
            "Typically set to stabilization or refinancing month. "
            "Automatically set by create_construction_to_permanent_plan() helper."
        ),
    )

    # TODO: Add covenant-based trigger support for permanent loan sweeps
    # Implementation uses time-based triggers (end_month).
    # Covenant-based triggers could activate/deactivate based on ongoing metrics:
    #   - covenant_triggers: Optional[List[CovenantTrigger]] = None
    #   - Trigger types: DSCRTrigger, LTVTrigger, OccupancyTrigger, DebtYieldTrigger
    #   - Each trigger evaluates metrics each period via ledger queries
    #   - Sweep activates when ANY trigger fires (OR logic)
    #   - Sweep deactivates when ALL triggers cured for grace_periods
    #   - Supports both construction (time-based) and permanent (covenant-based) loans
    #
    # This would enable realistic permanent loan modeling where sweeps respond to
    # covenant violations rather than just fixed dates.

    def process(self, context: "DealContext", facility_name: str) -> None:
        """
        Process cash sweep covenant for all periods.

        This method handles the full sweep lifecycle: calculating excess cash,
        applying sweep rules, and posting ledger transactions.

        Used for:
        - SIMPLE interest method (all sweep types) - full processing
        - SCHEDULED + TRAP mode - deposit/release posting only

        Note: For SCHEDULED + PREPAY mode, the calculation is handled synchronously
        by calculate_waterfall() during interest calculation, so this method is skipped.

        For each period where sweep is active:
        1. Calculate excess operating cash
        2. Apply sweep (trap or prepay) based on mode
        3. Release trapped cash when sweep ends (TRAP only)

        Args:
            context: Deal context with ledger access
            facility_name: Name of the debt facility this sweep belongs to
        """
        # Track trapped balance across periods (for TRAP mode)
        trapped_balance = 0.0

        # Get facility reference for balance manipulation (PREPAY mode)
        facility = self._get_facility(context, facility_name)

        # PERFORMANCE: Query NOI once upfront instead of per-period
        queries = LedgerQueries(context.ledger)
        noi_series = queries.noi()

        # Process each period
        for idx, period_date in enumerate(context.timeline.period_index):
            # Month number is 1-based (month 1, 2, 3, ...)
            month_num = idx + 1

            # Calculate excess cash for this period
            excess_cash = self._calculate_excess_cash(
                context, facility_name, period_date, noi_series
            )

            if month_num < self.end_month:
                # SWEEP IS ACTIVE: Apply sweep to excess cash
                if excess_cash > 0:
                    if self.mode == SweepMode.TRAP:
                        # TRAP MODE: Hold in escrow
                        trapped_balance += excess_cash
                        self._post_sweep_deposit(
                            context, period_date, excess_cash, facility_name
                        )

                    elif self.mode == SweepMode.PREPAY:
                        # PREPAY MODE: Apply to principal immediately
                        # Post prepayment transaction to ledger (balance reduction is implicit via ledger)
                        self._post_sweep_prepayment(
                            context, period_date, excess_cash, facility_name
                        )

            elif month_num == self.end_month:
                # SWEEP ENDS: Release any trapped funds
                if self.mode == SweepMode.TRAP and trapped_balance > 0:
                    self._post_sweep_release(
                        context, period_date, trapped_balance, facility_name
                    )
                    trapped_balance = 0.0
                # Note: PREPAY mode has no release (prepayments already reduced balance)

    def calculate_waterfall(
        self,
        period: pd.Timestamp,
        interest_due: float,
        current_balance: float,
        period_noi: float,  # ← CRITICAL: Passed (no query)
        facility_name: str,
        context: "DealContext",
    ) -> SweepAdjustment:
        """
        Calculate sweep waterfall for this period.

        CRITICAL PERFORMANCE: period_noi passed as parameter to avoid
        repeated ledger queries.

        This is a CALCULATION method only - does NOT post to ledger.
        Ledger posting handled by ConstructionFacility.

        Waterfall:
        1. Apply to interest first (reduces reserve draw)
        2. Apply remainder to principal (prepayment)

        Args:
            period: Current period
            interest_due: Interest due before sweep
            current_balance: Current loan balance
            period_noi: NOI for period (from upfront query)
            facility_name: Facility name (for logging)
            context: Deal context (for timeline access)

        Returns:
            SweepAdjustment with amounts applied to interest/principal
        """
        # Get month number (1-based)
        try:
            # Normalize Timestamp to Period to match timeline's PeriodIndex
            p = period
            if not isinstance(p, pd.Period):
                p = pd.Period(p, freq=context.timeline.period_index.freq)
            month_num = context.timeline.period_index.get_loc(p) + 1
        except KeyError:
            # Period not in timeline - sweep not active
            month_num = self.end_month  # Treat as inactive

        # Only PREPAY mode applies adjustments in this method
        # (TRAP mode posts deposits/releases separately via process())
        if self.mode == SweepMode.PREPAY and month_num < self.end_month:
            # WATERFALL MECHANICS (per Argus/Rockport standard):
            # 1. Calculate how much cash can pay interest (CashToDS)
            # 2. Calculate excess cash after debt service
            # 3. Apply excess to prepayment
            #
            # Example: period_noi=400, interest_due=283
            #   cash_to_interest = min(400, 283) = 283 (cash pays all interest)
            #   excess = 400 - 283 = 117 (leftover for prepayment)
            #   Result: 283 from cash + 0 from reserve, 117 prepayment

            cash_to_interest = min(period_noi, interest_due)
            excess_cash = max(0.0, period_noi - cash_to_interest)

            # Cap prepayment by outstanding balance (cannot prepay more than owed)
            capped_principal = max(0.0, min(excess_cash, current_balance))

            # Return adjustments if there's any cash available
            if cash_to_interest > 0 or capped_principal > 0:
                return SweepAdjustment(
                    to_interest=cash_to_interest, to_principal=capped_principal
                )

        # All other cases: no adjustment
        return SweepAdjustment(to_interest=0.0, to_principal=0.0)

    def _get_facility(self, context: "DealContext", facility_name: str):
        """
        Get facility object by name for balance manipulation.

        Args:
            context: Deal context
            facility_name: Name of the facility to find

        Returns:
            The debt facility object

        Raises:
            ValueError: If facility not found
        """
        for facility in context.deal.financing.facilities:
            if facility.name == facility_name:
                return facility
        raise ValueError(f"Facility not found: {facility_name}")

    def _calculate_excess_cash(
        self,
        context: "DealContext",
        facility_name: str,
        period_date: pd.Timestamp,
        noi_series: pd.Series,
    ) -> float:
        """
        Calculate excess operating cash available for sweep in this period.

        Formula:
            Excess = Operating Cash Flow (NOI) - Debt Service (if paid in cash)

        For construction loans with capitalized interest, debt service is 0,
        so excess = NOI (all operating cash is excess).

        Args:
            context: Deal context
            facility_name: Name of the facility
            period_date: Date of the period
            noi_series: Pre-queried NOI series (for performance)

        Returns:
            Excess cash amount (positive = cash available, zero/negative = no excess)
        """
        # Get operating cash flow for this period from pre-queried series
        period_noi = noi_series.get(period_date, 0.0)

        # Get debt service for this facility in this period
        # (For capitalized interest construction loans, this is typically 0)
        facility_ds = self._get_facility_debt_service(
            context, facility_name, period_date
        )

        # Excess = NOI + Debt Service
        # Note: debt_service is already negative (outflow), so adding it reduces NOI
        # Example: 200k NOI + (-50k debt service) = 150k excess
        excess = period_noi + facility_ds

        return max(0.0, excess)  # Only positive excess is swept

    def _get_facility_debt_service(
        self, context: "DealContext", facility_name: str, period_date: pd.Timestamp
    ) -> float:
        """
        Get debt service paid by THIS facility in this period.

        NOTE: For capitalized interest, this returns 0 (no cash service).

        Args:
            context: Deal context
            facility_name: Name of the facility
            period_date: Date of the period

        Returns:
            Debt service amount (negative = cash outflow)
        """
        # Query ledger for this facility's debt service in this period
        ledger_df = context.ledger.to_dataframe()

        facility_ds = ledger_df[
            (ledger_df["item_name"].str.contains(facility_name, na=False))
            & (ledger_df["date"] == period_date)
            & (ledger_df["category"] == "Financing")
            & (ledger_df["subcategory"].isin(["Interest Payment", "Principal Payment"]))
        ]["amount"].sum()

        return facility_ds  # Negative value (outflow)

    def _post_sweep_deposit(
        self,
        context: "DealContext",
        date: pd.Timestamp,
        amount: float,
        facility_name: str,
    ) -> None:
        """
        Post cash sweep deposit transaction (TRAP mode).

        Traps excess cash in lender-controlled escrow account.
        This reduces cash available for equity distributions.

        Args:
            context: Deal context
            date: Transaction date
            amount: Amount to trap
            facility_name: Name of the facility
        """
        facility = self._get_facility(context, facility_name)
        sweep_series = pd.Series([-amount], index=[date])

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,
            subcategory=FinancingSubcategoryEnum.CASH_SWEEP_DEPOSIT,
            item_name=f"{facility_name} - Cash Sweep Deposit (Trapped)",
            source_id=facility.uid,
            asset_id=context.deal.asset.uid,
            pass_num=CalculationPhase.FINANCING.value,
        )

        context.ledger.add_series(sweep_series, metadata)

    def _post_sweep_release(
        self,
        context: "DealContext",
        date: pd.Timestamp,
        amount: float,
        facility_name: str,
    ) -> None:
        """
        Post cash sweep release transaction (TRAP mode).

        Releases trapped cash from escrow when sweep ends.
        This makes cash available for equity distributions.

        CRITICAL: Must use FINANCING_SERVICE flow purpose to prevent
        this from leaking into project_cash_flow (unlevered).

        Args:
            context: Deal context
            date: Transaction date
            amount: Amount to release
            facility_name: Name of the facility
        """
        facility = self._get_facility(context, facility_name)
        release_series = pd.Series([amount], index=[date])

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,
            subcategory=FinancingSubcategoryEnum.CASH_SWEEP_RELEASE,
            item_name=f"{facility_name} - Cash Sweep Release",
            source_id=facility.uid,
            asset_id=context.deal.asset.uid,
            pass_num=CalculationPhase.FINANCING.value,
        )

        context.ledger.add_series(release_series, metadata)

    def _post_sweep_prepayment(
        self,
        context: "DealContext",
        date: pd.Timestamp,
        amount: float,
        facility_name: str,
    ) -> None:
        """
        Post mandatory sweep prepayment transaction (PREPAY mode).

        Applies excess cash to principal prepayment immediately.
        This reduces the loan balance and future interest expense.

        NOTE: Caller must also reduce facility.outstanding_balance!

        Args:
            context: Deal context
            date: Transaction date
            amount: Amount to prepay
            facility_name: Name of the facility
        """
        facility = self._get_facility(context, facility_name)
        prepay_series = pd.Series([-amount], index=[date])

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,
            subcategory=FinancingSubcategoryEnum.SWEEP_PREPAYMENT,
            item_name=f"{facility_name} - Mandatory Sweep Prepayment",
            source_id=facility.uid,
            asset_id=context.deal.asset.uid,
            pass_num=CalculationPhase.FINANCING.value,
        )

        context.ledger.add_series(prepay_series, metadata)
