# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Construction loan facility with explicit sizing and ledger integration.

This module provides the Phase 1 implementation of ConstructionFacility that
prioritizes explicitness and stability over complex multi-tranche functionality.
"""

import logging
from typing import TYPE_CHECKING, List, Literal, Optional, Union

import pandas as pd
from pydantic import Field, model_validator

from ..core.ledger import SeriesMetadata
from ..core.primitives import (
    CalculationPhase,
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    FinancingSubcategoryEnum,
    InterestCalculationMethod,
    Timeline,
)
from .base import DebtFacilityBase
from .rates import InterestRate

if TYPE_CHECKING:
    from performa.deal.orchestrator import DealContext

    from .tranche import DebtTranche

logger = logging.getLogger(__name__)


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
    interest_reserve_rate: float = Field(
        0.0, ge=0, le=0.5, description="Interest reserve as percentage of loan amount"
    )

    # Enhanced interest calculation settings
    interest_calculation_method: InterestCalculationMethod = Field(
        default=InterestCalculationMethod.NONE,
        description="Method for handling construction interest calculation",
    )
    simple_reserve_rate: Optional[float] = Field(
        default=None,
        ge=0,
        le=0.3,
        description="Reserve percentage when using SIMPLE method (required for SIMPLE method, typically 8-12%)",
    )

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

                    # For multi-tranche mode, loan_amount will be calculated dynamically
                    # in compute_cf based on actual project costs and tranche LTC thresholds
                    values["loan_amount"] = (
                        1.0  # Placeholder - will be recalculated in compute_cf
                    )

            # Single-facility mode: validate required parameters
            else:
                if values.get("name") is None:
                    raise ValueError("name is required for single-facility mode")
                if values.get("loan_amount") is None:
                    raise ValueError("loan_amount is required for single-facility mode")
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
        current_ledger = context.ledger_builder.get_current_ledger()
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

        # Final fallback to self.loan_amount if explicitly set
        if base_costs == 0 and self.loan_amount:
            return self.loan_amount

        # No silent failures! Raise explicit error if we can't determine project costs
        if base_costs == 0:
            raise ValueError(
                "ConstructionFacility cannot determine project costs for loan sizing. "
                "Either provide an explicit loan_amount, ensure project costs are in the ledger, "
                "or pass project_costs in the DealContext. "
                "Current state: ledger has no capital uses, context.project_costs is not set, "
                "and no loan_amount was specified."
            )

        # Get maximum LTC across all tranches (multi-tranche facilities fund up to highest LTC)
        if not self.tranches or len(self.tranches) == 0:
            raise ValueError(
                "ConstructionFacility requires at least one tranche to determine LTC"
            )
        ltc = max(tranche.ltc_threshold for tranche in self.tranches)

        # Calculate loan amount based on interest calculation method
        if self.interest_calculation_method == InterestCalculationMethod.NONE:
            # Simple LTC on base costs
            return base_costs * ltc

        elif self.interest_calculation_method == InterestCalculationMethod.SIMPLE:
            # Algebraic solution with interest reserve (no iteration needed!)
            # Loan = (Base × LTC) / (1 - Reserve% × LTC)
            if self.simple_reserve_rate is None:
                raise ValueError(
                    "simple_reserve_rate is required when using InterestCalculationMethod.SIMPLE. "
                    "Provide a rate between 0.08-0.12 (8-12% is typical)."
                )
            denominator = 1 - (self.simple_reserve_rate * ltc)
            if denominator <= 0:
                raise ValueError(
                    f"Simple reserve rate ({self.simple_reserve_rate:.1%}) and "
                    f"LTC ({ltc:.1%}) combination is invalid - denominator is {denominator:.4f}"
                )
            return (base_costs * ltc) / denominator

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
        Compute construction loan cash flows using the new ledger-first approach.

        This method implements the unified financing architecture by:
        1. Querying the ledger for actual project costs (base project costs)
        2. Using the selected interest calculation method to determine loan commitment
        3. Recording both loan proceeds and interest capitalization in the ledger
        4. Generating debt service schedule

        Args:
            context: Deal context with ledger access and deal-level data

        Returns:
            pd.Series: Debt service schedule
        """
        # Calculate proper loan commitment using new method
        effective_loan_amount = self._calculate_loan_commitment(context)

        # Write interest capitalization to ledger if using SIMPLE or SCHEDULED methods
        if self.interest_calculation_method in [
            InterestCalculationMethod.SIMPLE,
            InterestCalculationMethod.SCHEDULED,
        ]:
            self._record_interest_capitalization(context, effective_loan_amount)

        # Generate debt service with calculated loan amount
        return self._generate_debt_service_with_amount(context, effective_loan_amount)

    def _record_interest_capitalization(
        self, context: "DealContext", loan_amount: float
    ) -> None:
        """
        Record capitalized interest in the ledger as soft costs.

        This method implements the critical architectural requirement to record
        interest capitalization as part of the total project costs in the ledger.

        Args:
            context: Deal context with ledger builder access
            loan_amount: Total loan commitment including interest
        """
        # Calculate the interest component
        current_ledger = context.ledger_builder.get_current_ledger()
        if current_ledger.empty:
            return

        capital_uses = current_ledger[current_ledger["flow_purpose"] == "Capital Use"]
        base_costs = (
            abs(capital_uses["amount"].sum()) if not capital_uses.empty else 0.0
        )

        if base_costs == 0:
            return

        # Get maximum LTC across all tranches
        if not self.tranches or len(self.tranches) == 0:
            return  # Can't calculate without tranche info
        ltc = max(tranche.ltc_threshold for tranche in self.tranches)

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
                context.ledger_builder.add_series(interest_series, interest_metadata)

    def _generate_debt_service_with_amount(
        self, context: "DealContext", loan_amount: float
    ) -> pd.Series:
        """
        Generate debt service and write ledger transactions using specified loan amount.

        This method replaces the frozen model mutation hack by accepting the calculated
        loan amount as a parameter and handling ledger writes directly.

        Args:
            context: Deal context with ledger builder and timeline
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
            context.ledger_builder.add_series(proceeds_series, proceeds_metadata)

        # Write debt service to ledger (negative outflows)
        if not debt_service.empty and debt_service.sum() != 0:
            service_metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.FINANCING,
                subcategory=FinancingSubcategoryEnum.DEBT_SERVICE,
                item_name=f"{self.name} - Debt Service",
                source_id=self.uid,
                asset_id=context.deal.asset.uid,
                pass_num=CalculationPhase.FINANCING.value,
            )
            # Debt service is outflow (negative in ledger)
            context.ledger_builder.add_series(-debt_service, service_metadata)

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

        # Generate draw schedule
        draws = self._generate_draw_schedule(timeline)

        if self.interest_only:
            # Interest-only payments on outstanding balance
            outstanding_balance = 0.0
            monthly_rate = self._get_effective_rate() / 12

            for i, period in enumerate(timeline.period_index):
                if i < len(draws):
                    # Add this period's draw to outstanding balance
                    outstanding_balance += draws.iloc[i]

                    # Calculate interest on average balance during period
                    # (approximation: interest on balance after draw)
                    interest_payment = outstanding_balance * monthly_rate

                    # Net cash flow = draw - interest
                    debt_service.iloc[i] = draws.iloc[i] - interest_payment
        else:
            # Simple case: just the draws (no interest during construction)
            debt_service = draws

        return debt_service

    def _generate_draw_schedule(self, timeline: Timeline) -> pd.Series:
        """
        Generate loan draw schedule.

        Args:
            timeline: Analysis timeline

        Returns:
            pd.Series: Draw amounts by period
        """
        draws = pd.Series(0.0, index=timeline.period_index)

        if self.draw_schedule:
            # Use explicit draw schedule
            for period_str, amount in self.draw_schedule.items():
                # Convert period string to timeline index if possible
                # For now, assume period_str matches timeline format
                try:
                    if period_str in draws.index.astype(str):
                        period_idx = draws.index[draws.index.astype(str) == period_str][
                            0
                        ]
                        draws.loc[period_idx] = amount
                except:
                    # Fallback: distribute evenly if period matching fails
                    pass

        # If no explicit schedule or matching failed, distribute evenly
        if draws.sum() == 0 and self.loan_amount > 0:
            # Uniform distribution over loan term
            draw_periods = min(len(timeline.period_index), self.loan_term_months)
            monthly_draw = self.loan_amount / draw_periods
            draws.iloc[:draw_periods] = monthly_draw

        return draws
