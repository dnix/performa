# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Construction loan facility with ledger integration.

Implements construction loan sizing and cash flow generation with optional
interest reserve handling, multi-tranche support, and direct ledger recording
of proceeds, interest capitalization, and debt service.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Literal, Optional, Union

import pandas as pd
from pydantic import Field, model_validator

from ..core.ledger import Ledger, SeriesMetadata
from ..core.ledger.queries import LedgerQueries
from ..core.primitives import (
    CalculationPhase,
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    FinancingSubcategoryEnum,
    InterestCalculationMethod,
    Timeline,
)
from .base import DebtFacilityBase
from .covenants import CashSweep
from .rates import InterestRate

if TYPE_CHECKING:
    from performa.deal.orchestrator import DealContext

    from .tranche import DebtTranche

logger = logging.getLogger(__name__)


@dataclass
class CovenantAdjustments:
    """
    How covenants modify interest and balance this period.

    Extensible for future covenant types (reserve accounts, distribution blocks, etc.)

    Attributes:
        interest_paid_by_sweep: Amount of interest paid by sweep (reduces reserve draw)
        principal_prepayment: Amount of principal prepayment from sweep
    """

    interest_paid_by_sweep: float = 0.0
    principal_prepayment: float = 0.0


class ConstructionFacility(DebtFacilityBase):
    """
    Institutional-grade construction loan facility with multi-tranche support.

    Supports both simple single-facility construction loans and complex multi-tranche
    structures for sophisticated development financing.

    Construction Modes:
    - Single-facility: Explicit parameters (loan_amount, interest_rate, etc.)
    - Multi-tranche: List of DebtTranche objects for layered financing

    Advanced Features:
    - Interest reserve funding from loan proceeds
    - Flexible draw scheduling (uniform or custom)
    - Interest-only payment structure during construction
    - Integration with ledger-based cash flow analysis

    Assumptions:
    - Interest-only payments throughout construction term
    - Future: milestone-based amortization after stabilization

    Example:
        # Simple construction loan
        construction = ConstructionFacility(
            name="Construction Loan",
            loan_amount=8_000_000,
            interest_rate=0.065,
            loan_term_months=18,  # 18 month construction
            draw_schedule={'2024-01': 4_000_000, '2024-06': 4_000_000}
        )

        # Multi-tranche construction (tests use this pattern)
        construction = ConstructionFacility(
            tranches=[
                DebtTranche(
                    name="Senior Construction",
                    ltc_threshold=0.75,
                    interest_rate=InterestRate(details=FixedRate(rate=0.065)),
                    fee_rate=0.01
                )
            ]
        )

        # Using factory method
        construction = ConstructionFacility.from_uniform_draws(
            name="Construction Loan",
            total_loan_amount=8_000_000,
            interest_rate=0.065,
            construction_months=18
        )
    """

    # Discriminator field for union types (required by FinancingPlan)
    kind: Literal["construction"] = "construction"

    # Override base class fields to support multi-tranche and flexible parameters
    name: Optional[str] = Field(
        None, description="Facility name (can be derived from tranches)"
    )
    loan_amount: Optional[float] = Field(
        None,
        gt=0,
        description="Loan principal amount (can be calculated from tranches)",
    )
    interest_rate: Optional[Union[float, InterestRate]] = Field(
        None, description="Interest rate (can be derived from tranches)"
    )
    loan_term_months: Optional[int] = Field(
        None, gt=0, description="Loan term in months (can be set via loan_term_years)"
    )

    # Multi-tranche construction support
    tranches: Optional[List["DebtTranche"]] = Field(
        None,
        description="List of debt tranches for multi-layered construction financing",
    )

    # Loan term flexibility
    loan_term_years: Optional[int] = Field(
        None, gt=0, description="Loan term in years (converted to months)"
    )

    # Construction-specific settings
    draw_schedule: dict = Field(
        default_factory=dict,
        description="Draw schedule as dict of {period: amount} or uniform if empty",
    )
    interest_only: bool = Field(
        True, description="Whether loan is interest-only during construction period"
    )

    # Interest reserve settings
    fund_interest_from_reserve: bool = Field(
        False, description="Whether to fund interest payments from loan proceeds"
    )
    interest_reserve_rate: Optional[float] = Field(
        default=None,
        ge=0,
        le=0.5,
        description="Interest reserve as percentage of loan amount (only used with SIMPLE method)",
    )

    # Enhanced interest calculation settings
    interest_calculation_method: InterestCalculationMethod = Field(
        default=InterestCalculationMethod.SCHEDULED,
        description="Method for handling construction interest calculation",
    )
    simple_reserve_rate: Optional[float] = Field(
        default=None,
        ge=0,
        le=0.3,
        description="Reserve percentage when using SIMPLE method (required for SIMPLE method, typically 8-12%)",
    )

    # Loan sizing parameters (agnostic to capital structure)
    ltc_ratio: Optional[float] = Field(
        None,
        ge=0,
        le=1.0,
        description="Loan-to-cost ratio for sizing the construction loan (e.g., 0.70 = 70% of project costs)",
    )
    ltc_max: float = Field(
        0.80,
        ge=0,
        le=0.85,
        description="Maximum LTC threshold - lender's covenant that cannot be exceeded",
    )

    # TODO: Add funding cascade strategy (equity-first vs pro-rata vs debt-first)
    # This determines the ORDER of draws, not the SIZE of the loan
    # Currently hardcoded to equity-first in CashFlowEngine

    # Covenant constraints (composed, not inherited)
    cash_sweep: Optional["CashSweep"] = Field(
        default=None,
        description="Optional cash sweep covenant (traps or prepays excess cash)",
    )
    # TODO: Future covenant types (uncomment when implementing)
    # reserves: Optional[List[ReserveAccount]] = None
    # distribution_block: Optional[DistributionBlock] = None
    # mandatory_prepayment: Optional[MandatoryPrepayment] = None

    # NOTE: _effective_loan_amount is set via object.__setattr__ during compute_cf()
    # This is a pragmatic exception to immutability for runtime caching:
    # - Cannot be a Field (Pydantic doesn't allow leading underscores)
    # - Cannot be PrivateAttr (would require init=False everywhere)
    # - Alternative would be external state dict or breaking API
    # - This pattern mirrors @cached_property behavior in Python stdlib
    # Used by: outstanding_balance() → DebtAnalyzer → refinancing payoff calculation

    @model_validator(mode="before")
    def convert_years_to_months(cls, values):
        """Convert loan_term_years to loan_term_months if provided."""
        if isinstance(values, dict):
            loan_term_years = values.get("loan_term_years")
            loan_term_months = values.get("loan_term_months")

            if loan_term_years is not None and loan_term_months is None:
                values["loan_term_months"] = loan_term_years * 12
        return values

    @model_validator(mode="before")
    def validate_construction_parameters(cls, values):
        """Ensure either explicit parameters OR tranches are provided."""
        if isinstance(values, dict):
            tranches = values.get("tranches")

            # Multi-tranche mode: derive parameters from tranches
            if tranches is not None:
                if not tranches:
                    raise ValueError("tranches list cannot be empty")

                # Derive name if not provided
                if values.get("name") is None:
                    if len(tranches) == 1:
                        # Handle both dict and DebtTranche objects
                        first_tranche = tranches[0]
                        if isinstance(first_tranche, dict):
                            values["name"] = first_tranche.get(
                                "name", "Construction Facility"
                            )
                        else:
                            values["name"] = first_tranche.name
                    else:
                        values["name"] = (
                            f"Multi-Tranche Construction ({len(tranches)} tranches)"
                        )

                # Use first tranche's interest rate if not provided
                if values.get("interest_rate") is None:
                    # Handle both dict and DebtTranche objects
                    first_tranche = tranches[0]
                    if isinstance(first_tranche, dict):
                        values["interest_rate"] = first_tranche.get("interest_rate")
                    else:
                        values["interest_rate"] = first_tranche.interest_rate

                # Set default term if not provided
                if values.get("loan_term_months") is None:
                    values["loan_term_months"] = 24  # Default 2-year construction

                # For multi-tranche, estimate loan_amount from first tranche's LTC
                if values.get("loan_amount") is None:
                    first_tranche = tranches[0]
                    if isinstance(first_tranche, dict):
                        ltc_threshold = first_tranche.get("ltc_threshold", 0.75)
                    else:
                        ltc_threshold = first_tranche.ltc_threshold

                # NOTE: For multi-tranche mode, loan_amount will be calculated dynamically
                # in compute_cf based on actual project costs and tranche LTC thresholds
                pass  # loan_amount remains None and will be calculated properly

            # Single-facility mode: validate required parameters
            else:
                if values.get("name") is None:
                    raise ValueError("name is required for single-facility mode")

                # Either loan_amount OR ltc_ratio must be provided
                if (
                    values.get("loan_amount") is None
                    and values.get("ltc_ratio") is None
                ):
                    raise ValueError(
                        "Either loan_amount or ltc_ratio is required for single-facility mode"
                    )

                if values.get("interest_rate") is None:
                    raise ValueError(
                        "interest_rate is required for single-facility mode"
                    )
                if values.get("loan_term_months") is None:
                    raise ValueError(
                        "Either loan_term_months or loan_term_years must be provided"
                    )

        return values

    @classmethod
    def from_uniform_draws(
        cls,
        name: str,
        total_loan_amount: float,
        interest_rate: float,
        construction_months: int,
        **kwargs,
    ) -> "ConstructionFacility":
        """
        Factory method to create facility with uniform monthly draws.

        This is the most common construction loan pattern where the loan
        is drawn evenly over the construction period.

        Args:
            name: Facility name
            total_loan_amount: Total loan commitment
            interest_rate: Annual interest rate
            construction_months: Construction period in months
            **kwargs: Additional facility parameters

        Returns:
            Configured ConstructionFacility instance

        Example:
            construction = ConstructionFacility.from_uniform_draws(
                name="Construction Loan",
                total_loan_amount=8_000_000,
                interest_rate=0.065,
                construction_months=18
            )
        """
        return cls(
            name=name,
            loan_amount=total_loan_amount,
            interest_rate=interest_rate,
            loan_term_months=construction_months,
            draw_schedule={},  # Empty means uniform
            **kwargs,
        )

    @classmethod
    def from_cost_schedule(
        cls,
        name: str,
        cost_schedule: dict,
        ltc_ratio: float,
        interest_rate: float,
        **kwargs,
    ) -> "ConstructionFacility":
        """
        Factory method to create facility from construction cost schedule.

        Args:
            name: Facility name
            cost_schedule: Dict of {period: cost_amount}
            ltc_ratio: Loan-to-cost ratio (0.0 to 1.0)
            interest_rate: Annual interest rate
            **kwargs: Additional facility parameters

        Returns:
            Configured ConstructionFacility instance

        Example:
            costs = {'2024-01': 2_000_000, '2024-06': 3_000_000, '2024-12': 5_000_000}
            construction = ConstructionFacility.from_cost_schedule(
                name="Construction Loan",
                cost_schedule=costs,
                ltc_ratio=0.80,  # 80% LTC
                interest_rate=0.065
            )
        """
        total_costs = sum(cost_schedule.values())
        loan_amount = total_costs * ltc_ratio

        # Create draw schedule proportional to costs
        draw_schedule = {
            period: cost * ltc_ratio for period, cost in cost_schedule.items()
        }

        construction_months = len(cost_schedule)

        return cls(
            name=name,
            loan_amount=loan_amount,
            interest_rate=interest_rate,
            loan_term_months=construction_months,
            draw_schedule=draw_schedule,
            **kwargs,
        )

    def _calculate_loan_commitment(self, context: "DealContext") -> float:
        """
        Calculate the loan commitment based on project costs and interest calculation method.

        This is the key method that solves the construction financing gap by properly
        sizing debt facilities to fund the actual capital needs identified in the ledger.

        Args:
            context: Deal context with ledger access

        Returns:
            float: Calculated loan commitment amount
        """
        # Get base project costs from ledger or context fallback
        current_ledger = context.ledger.ledger_df()
        base_costs = 0.0

        if not current_ledger.empty:
            # Sum capital uses (negative amounts in ledger) to get total project costs
            capital_uses = current_ledger[
                current_ledger["flow_purpose"] == "Capital Use"
            ]
            base_costs = (
                abs(capital_uses["amount"].sum()) if not capital_uses.empty else 0.0
            )

        # Fallback to context.project_costs if ledger has no capital uses yet
        if (
            base_costs == 0
            and hasattr(context, "project_costs")
            and context.project_costs
        ):
            base_costs = context.project_costs

        # Final fallback to self.loan_amount ONLY if it's a real value (not None or tiny placeholder)
        if base_costs == 0 and self.loan_amount and self.loan_amount > 1000:
            # Only use loan_amount if it's a reasonable value (not a $1 placeholder)
            return self.loan_amount

        # Simple mode: if explicit loan_amount provided and no tranches/ltc_ratio, use it
        if self.loan_amount and not self.tranches and not self.ltc_ratio:
            return self.loan_amount

        # Check if we're using ltc_ratio sizing
        if self.ltc_ratio is not None and base_costs > 0:
            # Size by LTC ratio but still respect interest calculation method
            ltc = min(self.ltc_ratio, self.ltc_max)  # Apply ltc_max cap

            # Apply interest calculation method to ltc_ratio sizing as well
            if self.interest_calculation_method == InterestCalculationMethod.NONE:
                return base_costs * ltc

            elif self.interest_calculation_method == InterestCalculationMethod.SIMPLE:
                if self.simple_reserve_rate is None:
                    raise ValueError(
                        "simple_reserve_rate is required when using InterestCalculationMethod.SIMPLE. "
                        "Provide a rate between 0.08-0.12 (8-12% is typical)."
                    )

                # Calculate interest based on actual interest rate and construction duration
                construction_periods = self.loan_term_months or 24
                annual_rate = self._get_effective_rate()

                # Simple interest calculation: assume average balance during construction is 50% of final
                construction_years = construction_periods / 12
                base_loan = base_costs * ltc
                estimated_interest = base_loan * annual_rate * construction_years * 0.5

                # Size loan to cover both base costs and interest
                total_project_with_interest = base_costs + estimated_interest
                return total_project_with_interest * ltc

            elif (
                self.interest_calculation_method == InterestCalculationMethod.SCHEDULED
            ):
                # Sophisticated draw-based calculation using actual draw schedules
                draw_schedule_total = (
                    sum(self.draw_schedule.values())
                    if self.draw_schedule
                    else base_costs
                )

                # Calculate interest on draws using construction timeline
                construction_periods = self.loan_term_months or 24
                annual_rate = self._get_effective_rate()
                monthly_rate = annual_rate / 12

                # Estimate average outstanding balance during construction
                avg_outstanding = (draw_schedule_total * ltc) * 0.5
                total_interest = avg_outstanding * monthly_rate * construction_periods

                # Add interest to project costs and apply LTC
                total_project_with_interest = base_costs + total_interest
                return total_project_with_interest * ltc

            else:
                # Default: use debt ratio without interest adjustment
                return base_costs * ltc

        # Multi-tranche mode: requires project costs and tranches
        if not self.tranches:
            if self.loan_amount:
                return self.loan_amount
            raise ValueError(
                "ConstructionFacility requires either explicit loan_amount, ltc_ratio, or tranches for sizing"
            )

        # Raise explicit error if we can't determine project costs
        if base_costs == 0:
            if self.tranches:
                # Multi-tranche mode REQUIRES project costs
                raise ValueError(
                    "ConstructionFacility in multi-tranche mode REQUIRES project costs but found NONE!\n"
                    "The facility cannot calculate loan amount from LTC without knowing total costs.\n\n"
                    "Current state:\n"
                    "  - No capital uses in ledger (construction may not have started)\n"
                    "  - context.project_costs is not set\n"
                    "  - No explicit loan_amount provided\n\n"
                    "Solution: Ensure DealContext.project_costs is set during analysis, or\n"
                    "use explicit loan_amount instead of tranches for simpler deals."
                )
            else:
                # Single-facility mode should have loan_amount
                raise ValueError(
                    "ConstructionFacility cannot determine loan amount!\n"
                    "Single-facility mode requires explicit loan_amount parameter.\n"
                    "Multi-tranche mode requires project costs in context or ledger."
                )

        # Get maximum LTC across all tranches (multi-tranche facilities fund up to highest LTC)
        ltc = max(tranche.ltc_threshold for tranche in self.tranches)

        # Apply ltc_max cap even in multi-tranche mode
        ltc = min(ltc, self.ltc_max)

        # Calculate loan amount based on interest calculation method
        if self.interest_calculation_method == InterestCalculationMethod.NONE:
            # Simple LTC on base costs
            return base_costs * ltc

        elif self.interest_calculation_method == InterestCalculationMethod.SIMPLE:
            # Calculate construction interest and size loan to cover base costs + interest
            # This method estimates total interest as percentage of loan amount
            if self.simple_reserve_rate is None:
                raise ValueError(
                    "simple_reserve_rate is required when using InterestCalculationMethod.SIMPLE. "
                    "Provide a rate between 0.08-0.12 (8-12% is typical)."
                )

            # Calculate interest based on actual interest rate and construction duration
            construction_periods = self.loan_term_months or 24
            annual_rate = self._get_effective_rate()

            # Simple interest calculation: assume average balance during construction is 50% of final
            # Total interest = (base_loan * ltc) * (annual_rate * construction_years) * 50%
            construction_years = construction_periods / 12
            base_loan = base_costs * ltc
            estimated_interest = base_loan * annual_rate * construction_years * 0.5

            # Alternative: Use simple_reserve_rate as a percentage of loan amount if it's meant as total interest
            # estimated_interest = base_loan * self.simple_reserve_rate

            # Size loan to cover both base costs and interest
            total_project_with_interest = base_costs + estimated_interest
            return total_project_with_interest * ltc

        elif self.interest_calculation_method == InterestCalculationMethod.SCHEDULED:
            # Sophisticated draw-based calculation using actual draw schedules
            # This leverages Performa's draw schedule capabilities
            draw_schedule_total = (
                sum(self.draw_schedule.values()) if self.draw_schedule else base_costs
            )

            # Calculate interest on draws using construction timeline
            construction_periods = self.loan_term_months or 24
            annual_rate = self._get_effective_rate()
            monthly_rate = annual_rate / 12

            # Estimate average outstanding balance during construction
            # (simplified: assume uniform draws, average balance is 50% of final)
            avg_outstanding = (draw_schedule_total * ltc) * 0.5
            total_interest = avg_outstanding * monthly_rate * construction_periods

            # Add interest to project costs and apply LTC
            total_project_with_interest = base_costs + total_interest
            return total_project_with_interest * ltc

        elif self.interest_calculation_method == InterestCalculationMethod.ITERATIVE:
            # Future enhancement: full iterative simulation
            # For now, fall back to SCHEDULED method
            return self._calculate_loan_commitment_scheduled_method(
                context, base_costs, ltc
            )

        else:
            # Default: use base LTC
            return base_costs * ltc

    def _calculate_loan_commitment_scheduled_method(
        self, context: "DealContext", base_costs: float, ltc: float
    ) -> float:
        """Helper for scheduled calculation method."""
        # This would contain the sophisticated draw schedule logic
        # For now, use the same logic as SCHEDULED above
        construction_periods = self.loan_term_months or 24
        annual_rate = self._get_effective_rate()
        monthly_rate = annual_rate / 12

        avg_outstanding = (base_costs * ltc) * 0.5
        total_interest = avg_outstanding * monthly_rate * construction_periods
        total_project_with_interest = base_costs + total_interest
        return total_project_with_interest * ltc

    def compute_cf(self, context: "DealContext") -> pd.Series:
        """
        Compute construction loan cash flows.

        Branches on interest_calculation_method:
        - SIMPLE: Legacy upfront calculation (backward compatible)
        - SCHEDULED: NEW synchronous interest-covenant calculation

        Args:
            context: Deal context with ledger access and deal-level data

        Returns:
            pd.Series: Debt service schedule (empty for construction loans)
        """
        logger.debug(
            f"{self.name}: compute_cf() called with method={self.interest_calculation_method}"
        )

        if self.interest_calculation_method == InterestCalculationMethod.SIMPLE:
            # Legacy path (backward compatible)
            effective_loan_amount = self._calculate_loan_commitment(context)
            # Cache computed value for outstanding_balance() calls
            # Using object.__setattr__ to bypass Pydantic immutability for runtime caching
            object.__setattr__(self, "_effective_loan_amount", effective_loan_amount)  # noqa: PLC2801
            logger.debug(
                f"Recording interest capitalization for {self.name} with SIMPLE method"
            )
            self._record_interest_capitalization(context, effective_loan_amount)
            return self._generate_debt_service_with_amount(
                context, effective_loan_amount
            )

        elif self.interest_calculation_method == InterestCalculationMethod.SCHEDULED:
            # NEW: Synchronous period-by-period calculation
            logger.debug(
                f"Computing interest and covenants synchronously for {self.name}"
            )
            self._compute_interest_and_covenants(context)
            return pd.Series([], dtype=float)  # No recurring debt service

        else:
            raise ValueError(
                f"Unsupported interest calculation method: {self.interest_calculation_method}"
            )

    def process_covenants(self, context: "DealContext") -> None:
        """
        Process all covenant-based restrictions for this facility.

        Called after compute_cf() in a separate orchestrator phase.

        SCHEDULED method:
        - PREPAY: Already processed synchronously (skip)
        - TRAP: Post deposits/releases here (legacy process() method)

        SIMPLE method:
        - All covenants: Process normally

        Current covenants:
        - Cash sweep (if configured)

        Future extensibility (TODO):
        - Reserve accounts (tax, insurance, CapEx)
        - Distribution blocks (DSCR/occupancy requirements)
        - Mandatory prepayments (on refinancing, sale, etc.)
        - Lockbox arrangements
        """
        if self.interest_calculation_method == InterestCalculationMethod.SIMPLE:
            # Legacy: process all covenants
            if self.cash_sweep:
                self.cash_sweep.process(context, self.name)

        elif self.interest_calculation_method == InterestCalculationMethod.SCHEDULED:
            # CRITICAL: Sweep must continue processing POST-CONSTRUCTION
            # During construction: handled synchronously in _compute_interest_and_covenants()
            # After construction: must still process sweep for NOI (months 19-42)
            if self.cash_sweep:
                self.cash_sweep.process(context, self.name)

        # TODO: Process other covenants as they're implemented
        # for reserve in self.reserves or []:
        #     reserve.process(context, self.name)
        #
        # if self.distribution_block:
        #     self.distribution_block.process(context, self.name)

    def _compute_interest_and_covenants(self, context: "DealContext") -> None:
        """
        Synchronously calculate interest and covenants period-by-period.

        Architecture:
        1. Batch queries ONCE upfront (NOI, capital uses) - PERFORMANCE
        2. Loop: calculate interest → apply covenants → update balance
        3. Build ledger series directly (no intermediate storage) - SIMPLICITY
        4. Post all transactions in batch

        Performance:
        - Single DataFrame materialization (~5ms)
        - Single NOI query (~2ms)
        - Loop with O(1) lookups (~2ms for 18-42 periods)
        - Total: ~10-15ms (within 20ms budget)

        This method implements the industry-standard period-by-period interest
        calculation that enables proper interaction with cash sweep covenants.
        """
        balance = 0.0
        monthly_rate = self._get_effective_rate() / 12
        alpha = 0.5  # Within-period draw factor (uniform draws)

        logger.debug(f"{self.name}: Starting synchronous interest-covenant calculation")

        # === CRITICAL PERFORMANCE: Batch queries ONCE ===

        # Query 1: Extract capital uses (single DataFrame materialization)
        ledger_df = context.ledger.to_dataframe()  # ← ONLY to_dataframe() call
        capital_uses_by_period = self._extract_capital_uses_by_period(ledger_df)

        # Query 2: Extract NOI series (single SQL query)
        noi_series = LedgerQueries(context.ledger).noi()

        # === Build series directly (no intermediate storage) ===
        interest_reserve_dict = {}  # Interest paid from reserve (capitalized)
        interest_sweep_dict = {}  # Interest paid from sweep
        prepay_dict = {}  # Prepayments from sweep

        for idx, period in enumerate(context.timeline.period_index):
            month_num = idx + 1

            # Respect loan term
            if self.loan_term_months and month_num > self.loan_term_months:
                break

            # Get data for this period (O(1) lookups)
            cost_draw = capital_uses_by_period.get(period, 0.0)
            period_noi = noi_series.get(period, 0.0)

            # STEP 1: Calculate raw interest
            raw_interest = monthly_rate * (balance + alpha * cost_draw)

            # STEP 2: Apply covenant adjustments
            adjustments = self._calculate_covenant_adjustments(
                period=period,
                raw_interest=raw_interest,
                balance=balance,
                period_noi=period_noi,  # ← Passed (no query)
                context=context,
            )

            # STEP 3: Determine net effects
            interest_from_reserve = raw_interest - adjustments.interest_paid_by_sweep

            # STEP 4: Store in series dicts
            if interest_from_reserve > 0:
                interest_reserve_dict[period] = interest_from_reserve
            if adjustments.interest_paid_by_sweep > 0:
                interest_sweep_dict[period] = adjustments.interest_paid_by_sweep
            if adjustments.principal_prepayment > 0:
                prepay_dict[period] = adjustments.principal_prepayment

            # STEP 5: Update balance for next period
            balance += (
                cost_draw + interest_from_reserve - adjustments.principal_prepayment
            )

        # Cache computed balance for outstanding_balance() calls
        # Using object.__setattr__ to bypass Pydantic immutability for runtime caching
        object.__setattr__(self, "_effective_loan_amount", balance)  # noqa: PLC2801

        # Post all transactions
        self._post_interest_and_covenant_transactions(
            context, balance, interest_reserve_dict, interest_sweep_dict, prepay_dict
        )

        logger.debug(
            f"{self.name}: Synchronous calculation complete, final balance=${balance:,.0f}"
        )

    def _post_interest_and_covenant_transactions(
        self,
        context: "DealContext",
        total_loan_amount: float,
        interest_reserve: Dict[pd.Timestamp, float],
        interest_sweep: Dict[pd.Timestamp, float],
        prepayments: Dict[pd.Timestamp, float],
    ) -> None:
        """
        Post all interest and covenant transactions to ledger in batch.

        Args:
            context: Deal context
            total_loan_amount: Final loan balance (for proceeds)
            interest_reserve: Period → interest from reserve (negative in ledger)
            interest_sweep: Period → interest from sweep (positive in ledger)
            prepayments: Period → prepayments from sweep (negative in ledger)
        """
        timeline = context.timeline

        # 1. Loan proceeds (Day 1)
        if total_loan_amount > 0:
            proceeds_series = pd.Series(
                [total_loan_amount], index=[timeline.period_index[0]]
            )
            context.ledger.add_series(
                proceeds_series,
                SeriesMetadata(
                    category=CashFlowCategoryEnum.FINANCING,
                    subcategory=FinancingSubcategoryEnum.LOAN_PROCEEDS,
                    item_name=f"{self.name} - Proceeds",
                    source_id=self.uid,
                    asset_id=context.deal.asset.uid,
                    pass_num=CalculationPhase.FINANCING.value,
                ),
            )
            logger.debug(f"{self.name}: Posted loan proceeds ${total_loan_amount:,.0f}")

        # 2. Interest from reserve (capitalized, negative)
        if interest_reserve:
            series = pd.Series(
                {p: -amt for p, amt in interest_reserve.items()}, dtype=float
            )
            context.ledger.add_series(
                series,
                SeriesMetadata(
                    category=CashFlowCategoryEnum.FINANCING,
                    subcategory=FinancingSubcategoryEnum.INTEREST_PAYMENT,
                    item_name=f"{self.name} - Interest (from reserve)",
                    source_id=self.uid,
                    asset_id=context.deal.asset.uid,
                    pass_num=CalculationPhase.FINANCING.value,
                ),
            )

        # 3. Interest from sweep (informational, positive)
        if interest_sweep:
            series = pd.Series(interest_sweep, dtype=float)
            context.ledger.add_series(
                series,
                SeriesMetadata(
                    category=CashFlowCategoryEnum.FINANCING,
                    subcategory=FinancingSubcategoryEnum.INTEREST_PAYMENT,
                    item_name=f"{self.name} - Interest (from sweep)",
                    source_id=self.uid,
                    asset_id=context.deal.asset.uid,
                    pass_num=CalculationPhase.FINANCING.value,
                ),
            )

        # 4. Sweep prepayments (negative)
        if prepayments:
            series = pd.Series({p: -amt for p, amt in prepayments.items()}, dtype=float)
            context.ledger.add_series(
                series,
                SeriesMetadata(
                    category=CashFlowCategoryEnum.FINANCING,
                    subcategory=FinancingSubcategoryEnum.SWEEP_PREPAYMENT,
                    item_name=f"{self.name} - Sweep Prepayment",
                    source_id=self.uid,
                    asset_id=context.deal.asset.uid,
                    pass_num=CalculationPhase.FINANCING.value,
                ),
            )

    def _record_interest_capitalization(
        self, context: "DealContext", loan_amount: float
    ) -> None:
        """
        Record capitalized interest in the ledger as soft costs.

        This method implements the critical architectural requirement to record
        interest capitalization as part of the total project costs in the ledger.

        Args:
            context: Deal context with ledger access
            loan_amount: Total loan commitment including interest
        """
        # Calculate the interest component
        current_ledger = context.ledger.ledger_df()
        if current_ledger.empty:
            return

        capital_uses = current_ledger[current_ledger["flow_purpose"] == "Capital Use"]
        base_costs = (
            abs(capital_uses["amount"].sum()) if not capital_uses.empty else 0.0
        )

        if base_costs == 0:
            return

        # Calculate LTC for interest estimation
        if self.tranches and len(self.tranches) > 0:
            # Tranche-based facility: use maximum LTC
            ltc = max(tranche.ltc_threshold for tranche in self.tranches)
        elif self.ltc_ratio is not None:
            # LTC-based facility: use the LTC ratio
            ltc = min(self.ltc_ratio, self.ltc_max)
        else:
            # Fallback: use a reasonable default
            ltc = 0.70

        # Calculate interest component
        base_loan = base_costs * ltc
        interest_component = loan_amount - base_loan

        if interest_component > 0:
            # Record as soft costs in first period
            timeline = context.timeline
            if len(timeline.period_index) > 0:
                interest_series = pd.Series(
                    [-interest_component], index=[timeline.period_index[0]]
                )

                interest_metadata = SeriesMetadata(
                    category=CashFlowCategoryEnum.CAPITAL,
                    subcategory=CapitalSubcategoryEnum.SOFT_COSTS,
                    item_name=f"{self.name} - Capitalized Interest",
                    source_id=self.uid,
                    asset_id=context.deal.asset.uid,
                    pass_num=CalculationPhase.FINANCING.value,
                )
                context.ledger.add_series(interest_series, interest_metadata)

    def _extract_capital_uses_by_period(
        self, ledger_df: pd.DataFrame
    ) -> Dict[pd.Period, float]:
        """
        Pre-aggregate capital uses by period for fast loop lookups.

        CRITICAL PERFORMANCE: Called ONCE before loop. Returns dict for O(1) access.
        This eliminates repeated DataFrame filtering (18-42 queries → 1).

        Args:
            ledger_df: Full ledger as DataFrame (from single to_dataframe() call)

        Returns:
            Dict mapping period (pd.Period) → debt-funded capital use amount

        Example:
            >>> ledger_df = context.ledger.to_dataframe()
            >>> capital_uses = facility._extract_capital_uses_by_period(ledger_df)
            >>> month_1_draw = capital_uses.get(period, 0.0)  # O(1) lookup
        """
        # Filter to Capital Use transactions
        capital_uses = ledger_df[ledger_df["flow_purpose"] == "Capital Use"]

        if capital_uses.empty:
            return {}

        # Group by period and sum (absolute value for costs)
        by_period = capital_uses.groupby("date")["amount"].sum().abs()

        # Apply LTC ratio to get debt-funded portion
        if self.ltc_ratio is not None:
            ltc = self.ltc_ratio
        else:
            # Fallback: use reasonable default
            ltc = 0.70

        debt_funded = by_period * ltc

        # CRITICAL FIX: Convert Timestamp index to Period to match timeline
        # The ledger uses Timestamp, but timeline uses Period
        debt_funded.index = debt_funded.index.to_period("M")

        return debt_funded.to_dict()

    def _calculate_covenant_adjustments(
        self,
        period: pd.Timestamp,
        raw_interest: float,
        balance: float,
        period_noi: float,
        context: "DealContext",
    ) -> CovenantAdjustments:
        """
        Calculate covenant-based adjustments for this period.

        This method delegates to composed covenant objects, maintaining clean
        separation of concerns. Each covenant can adjust interest or balance.

        CRITICAL PERFORMANCE: period_noi passed as parameter to avoid repeated
        ledger queries (18-42 queries → 0).

        Args:
            period: Current period timestamp
            raw_interest: Interest calculated before any adjustments
            balance: Current loan balance
            period_noi: Net Operating Income for this period (from upfront batch query)
            context: Deal context

        Returns:
            CovenantAdjustments with sweep impacts

        Example:
            >>> adjustments = facility._calculate_covenant_adjustments(
            ...     period=pd.Timestamp('2024-01-01'),
            ...     raw_interest=50_000.0,
            ...     balance=10_000_000.0,
            ...     period_noi=200_000.0,
            ...     context=context
            ... )
            >>> # Sweep paid $50k interest, prepaid $100k principal
            >>> adjustments.interest_paid_by_sweep  # 50000.0
            >>> adjustments.principal_prepayment  # 100000.0
        """
        adjustments = CovenantAdjustments()

        # Apply cash sweep covenant if configured
        if self.cash_sweep:
            sweep = self.cash_sweep.calculate_waterfall(
                period=period,
                interest_due=raw_interest,
                current_balance=balance,
                period_noi=period_noi,  # ← Pass as parameter (no query)
                facility_name=self.name,
                context=context,
            )
            adjustments.interest_paid_by_sweep = sweep.to_interest
            adjustments.principal_prepayment = sweep.to_principal

        # Future: Other covenant types would be added here
        # if self.reserves:
        #     for reserve in self.reserves:
        #         reserve_adj = reserve.calculate_adjustment(...)
        #         adjustments.apply(reserve_adj)

        return adjustments

    def _generate_debt_service_with_amount(
        self, context: "DealContext", loan_amount: float
    ) -> pd.Series:
        """
        Generate debt service and write ledger transactions using specified loan amount.

        This method replaces the frozen model mutation hack by accepting the calculated
        loan amount as a parameter and handling ledger writes directly.

        Args:
            context: Deal context with ledger and timeline
            loan_amount: Effective loan amount to use (may differ from self.loan_amount)

        Returns:
            pd.Series: Debt service schedule
        """
        timeline = context.timeline

        # Generate debt service schedule with effective loan amount
        debt_service = self._generate_debt_service(timeline)

        # Write loan proceeds to ledger using effective loan amount
        if loan_amount > 0:
            proceeds_series = pd.Series([loan_amount], index=[timeline.period_index[0]])

            proceeds_metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.FINANCING,
                subcategory=FinancingSubcategoryEnum.LOAN_PROCEEDS,
                item_name=f"{self.name} - Proceeds",
                source_id=self.uid,
                asset_id=context.deal.asset.uid,
                pass_num=CalculationPhase.FINANCING.value,
            )
            context.ledger.add_series(proceeds_series, proceeds_metadata)

        # Write disaggregated debt service to ledger for architectural consistency
        if not debt_service.empty and debt_service.sum() != 0:
            # For construction loans (interest-only), write as separate I&P for consistency
            # Interest payment = debt_service amount, Principal payment = $0

            # Record interest payment (actual cash expense)
            interest_metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.FINANCING,
                subcategory=FinancingSubcategoryEnum.INTEREST_PAYMENT,
                item_name=f"{self.name} - Interest",
                source_id=self.uid,
                asset_id=context.deal.asset.uid,
                pass_num=CalculationPhase.FINANCING.value,
            )
            # Interest payment is outflow (negative in ledger)
            context.ledger.add_series(-debt_service, interest_metadata)

            # Record principal payment as $0 (interest-only assumption)
            # TODO: Future enhancement - milestone-based amortization after construction/stabilization
            zero_principal = pd.Series(0.0, index=debt_service.index)
            principal_metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.FINANCING,
                subcategory=FinancingSubcategoryEnum.PRINCIPAL_PAYMENT,
                item_name=f"{self.name} - Principal",
                source_id=self.uid,
                asset_id=context.deal.asset.uid,
                pass_num=CalculationPhase.FINANCING.value,
            )
            context.ledger.add_series(
                -zero_principal, principal_metadata
            )  # $0 outflow (current assumption)

        return debt_service

    def _generate_debt_service(self, timeline: Timeline) -> pd.Series:
        """
        Generate construction loan cash flows.

        For construction loans, this includes:
        - Loan draws (positive inflows) based on draw_schedule
        - Interest payments (negative outflows) on outstanding balance

        Args:
            timeline: Analysis timeline

        Returns:
            pd.Series: Net cash flows (draws - interest payments)
        """
        periods = len(timeline.period_index)
        debt_service = pd.Series(0.0, index=timeline.period_index)

        if periods == 0:
            return debt_service

        # CRITICAL FIX: Respect loan_term_months to stop debt service after term
        # This ensures construction loans stop when refinanced
        max_periods = periods
        if self.loan_term_months:
            max_periods = min(self.loan_term_months, periods)
            logger.debug(
                f"{self.name}: Limiting debt service to {max_periods} months (loan term)"
            )

        # Generate draw schedule (limited to loan term)
        draws = self._generate_draw_schedule(timeline)

        if self.interest_only:
            # Interest-only payments on outstanding balance
            # CRITICAL FIX: Debt service should be ONLY the interest payment, not net of draws
            outstanding_balance = 0.0
            monthly_rate = self._get_effective_rate() / 12

            for i, period in enumerate(timeline.period_index):
                # Stop generating debt service after loan term
                if i >= max_periods:
                    break

                if i < len(draws):
                    # Add this period's draw to outstanding balance
                    outstanding_balance += draws.iloc[i]

                # Calculate interest payment on outstanding balance
                # For interest-only loans, we only pay interest, not principal
                interest_payment = outstanding_balance * monthly_rate

                # CRITICAL FIX: Return only the interest payment as debt service
                # Draws are handled separately as loan proceeds
                debt_service.iloc[i] = interest_payment
        else:
            # Simple case: just the draws (no interest during construction)
            # But still limit to loan term
            for i in range(min(len(draws), max_periods)):
                debt_service.iloc[i] = draws.iloc[i]

        return debt_service

    def get_outstanding_balance(self, date, financing_cash_flows=None) -> float:
        """
        Calculate outstanding loan balance for refinancing payoff.

        For construction loans, the outstanding balance includes:
        1. Principal (loan amount)
        2. Capitalized interest (if fund_interest_from_reserve=True)

        The capitalized interest is added to the loan balance during construction
        and must be repaid at refinancing.

        Args:
            date: Date for balance calculation
            financing_cash_flows: Optional cash flow history (ledger)

        Returns:
            Outstanding loan balance (principal + capitalized interest)
        """
        # Get base loan amount (principal)
        base_amount = 0.0
        if hasattr(self, "_effective_loan_amount") and self._effective_loan_amount:
            base_amount = self._effective_loan_amount
        elif self.loan_amount and self.loan_amount > 0:
            base_amount = self.loan_amount
        elif self.ltc_ratio is not None:
            # Estimate loan amount as ltc_ratio * typical project cost
            estimated_amount = 20_000_000 * self.ltc_ratio  # Rough estimate
            logger.warning(
                f"Estimating outstanding balance for {self.name}: ${estimated_amount:,.0f}"
            )
            base_amount = estimated_amount
        else:
            logger.warning(
                f"No loan amount available for {self.name} outstanding balance calculation"
            )
            return 0.0

        # Add capitalized interest if funded from reserve
        # Query ledger for capitalized interest transactions
        capitalized_interest = 0.0
        if financing_cash_flows is not None and self.fund_interest_from_reserve:
            try:
                # If financing_cash_flows is a Ledger, query it
                if isinstance(financing_cash_flows, Ledger):
                    ledger_df = financing_cash_flows.to_dataframe()

                    # Find capitalized interest for this facility
                    cap_interest_mask = ledger_df["item_name"].str.contains(
                        f"{self.name} - Capitalized Interest", na=False
                    )

                    if cap_interest_mask.any():
                        # Sum absolute value (interest is negative in ledger)
                        capitalized_interest = abs(
                            ledger_df[cap_interest_mask]["amount"].sum()
                        )

                        logger.debug(
                            f"{self.name}: Base ${base_amount:,.0f} + "
                            f"Cap Interest ${capitalized_interest:,.0f} = "
                            f"Outstanding ${base_amount + capitalized_interest:,.0f}"
                        )
            except Exception as e:
                logger.warning(
                    f"Could not query capitalized interest for {self.name}: {e}. "
                    f"Outstanding balance may be understated."
                )

        return base_amount + capitalized_interest

    def _generate_draw_schedule(self, timeline: Timeline) -> pd.Series:
        """
        Generate loan draw schedule.

        Args:
            timeline: Analysis timeline

        Returns:
            pd.Series: Draw amounts by period
        """
        draws = pd.Series(0.0, index=timeline.period_index)

        # CRITICAL FIX: Limit draws to loan term to prevent zombie loans
        max_draw_periods = len(timeline.period_index)
        if self.loan_term_months:
            max_draw_periods = min(self.loan_term_months, len(timeline.period_index))

        if self.draw_schedule:
            # Use explicit draw schedule (but still respect loan term)
            for period_str, amount in self.draw_schedule.items():
                # Convert period string to timeline index if possible
                try:
                    if period_str in draws.index.astype(str):
                        period_idx = draws.index[draws.index.astype(str) == period_str][
                            0
                        ]
                        # Only add draw if within loan term
                        period_num = draws.index.get_loc(period_idx)
                        if period_num < max_draw_periods:
                            draws.loc[period_idx] = amount
                except:
                    # Fallback: distribute evenly if period matching fails
                    pass

        # If no explicit schedule or matching failed, distribute evenly
        loan_amount_for_draws = self._get_effective_loan_amount_for_draws()
        if draws.sum() == 0 and loan_amount_for_draws and loan_amount_for_draws > 0:
            # Uniform distribution over loan term (respecting term limit)
            draw_periods = max_draw_periods
            monthly_draw = loan_amount_for_draws / draw_periods
            draws.iloc[:draw_periods] = monthly_draw

        return draws

    def _get_effective_loan_amount_for_draws(self) -> Optional[float]:
        """Get effective loan amount for draw scheduling."""
        if self.loan_amount and self.loan_amount > 1000:  # Has explicit amount
            return self.loan_amount
        elif self.tranches:
            # Calculate from tranches if no explicit amount
            return None  # Will be calculated by _calculate_loan_commitment
        else:
            return None
