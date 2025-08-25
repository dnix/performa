# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Financing Plan - Container for Debt Facilities

This module defines the FinancingPlan which orchestrates a sequence of debt facilities
to support complex financing scenarios like construction-to-permanent workflows.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field, model_validator

from ..core.primitives import Model
from .construction import ConstructionFacility
from .permanent import PermanentFacility
from .types import AnyDebtFacility


class FinancingPlan(Model):
    """
    Container for a sequence of debt facilities over an asset's lifecycle.

    This enables complex financing scenarios like:
    - Construction loan → Permanent loan refinancing
    - Bridge loan → Permanent loan refinancing
    - Multiple permanent loans with different terms
    - Debt facilities with different timing and terms

    The FinancingPlan orchestrates the sequence and transitions between facilities,
    while each facility handles its own debt service calculations.

    Key Features:
    - Supports multiple debt facilities in sequence
    - Handles refinancing transitions (construction → permanent)
    - Maintains facility timing and coordination
    - Integrates with Deal-level cash flow orchestration

    Examples:
        # Simple permanent financing
        plan = FinancingPlan(
            name="Permanent Financing",
            facilities=[permanent_loan]
        )

        # Construction-to-permanent financing
        plan = FinancingPlan(
            name="Construction-to-Permanent",
            facilities=[construction_loan, permanent_loan]
        )

        # Complex multi-facility financing
        plan = FinancingPlan(
            name="Multi-Phase Financing",
            facilities=[
                construction_loan,
                bridge_loan,
                permanent_loan_1,
                permanent_loan_2
            ]
        )
    """

    # Core Identity
    name: str = Field(..., description="Name of the financing plan")
    description: Optional[str] = Field(
        default=None, description="Description of financing strategy"
    )

    # Debt Facilities Sequence
    facilities: List[AnyDebtFacility] = Field(
        ..., description="List of debt facilities in chronological order", min_length=1
    )

    @property
    def primary_facility(self) -> AnyDebtFacility:
        """
        Get the primary (first) debt facility in the plan.

        Returns:
            The first debt facility in the sequence
        """
        return self.facilities[0]

    @property
    def has_construction_financing(self) -> bool:
        """Check if the plan includes construction financing."""
        return any(
            isinstance(facility, ConstructionFacility) for facility in self.facilities
        )

    @property
    def has_permanent_financing(self) -> bool:
        """Check if the plan includes permanent financing."""
        return any(
            isinstance(facility, PermanentFacility) for facility in self.facilities
        )

    @property
    def has_refinancing(self) -> bool:
        """Check if the plan includes a refinancing transition."""
        return len(self.facilities) > 1

    @property
    def construction_facilities(self) -> List[ConstructionFacility]:
        """Get all construction facilities in the plan."""
        return [
            facility
            for facility in self.facilities
            if isinstance(facility, ConstructionFacility)
        ]

    @property
    def permanent_facilities(self) -> List[PermanentFacility]:
        """Get all permanent facilities in the plan."""
        return [
            facility
            for facility in self.facilities
            if isinstance(facility, PermanentFacility)
        ]

    @model_validator(mode="after")
    def validate_facility_sequence(self) -> "FinancingPlan":
        """
        Validate that the facility sequence makes business sense.

        Business rules:
        - Construction facilities should come before permanent facilities
        - Multiple facilities should have logical sequencing
        - Refinancing scenarios should be valid
        """
        if len(self.facilities) < 1:
            raise ValueError("FinancingPlan must have at least one debt facility")

        # Check construction-to-permanent sequencing
        construction_facilities = self.construction_facilities
        permanent_facilities = self.permanent_facilities

        if construction_facilities and permanent_facilities:
            # Find indices of construction and permanent facilities
            construction_indices = [
                i
                for i, facility in enumerate(self.facilities)
                if isinstance(facility, ConstructionFacility)
            ]
            permanent_indices = [
                i
                for i, facility in enumerate(self.facilities)
                if isinstance(facility, PermanentFacility)
            ]

            # Construction should generally come before permanent
            if construction_indices and permanent_indices:
                last_construction_idx = max(construction_indices)
                first_permanent_idx = min(permanent_indices)

                if last_construction_idx > first_permanent_idx:
                    # This might be valid in some cases, but warn for now
                    # In future we could add more sophisticated validation
                    pass

        return self

    def get_facility_by_name(self, name: str) -> Optional[AnyDebtFacility]:
        """
        Get a facility by its name.

        Args:
            name: Name of the facility to find

        Returns:
            The facility with the given name, or None if not found
        """
        for facility in self.facilities:
            if hasattr(facility, "name") and facility.name == name:
                return facility
        return None

    def get_facilities_by_type(self, facility_type: type) -> List[AnyDebtFacility]:
        """
        Get all facilities of a specific type.

        Args:
            facility_type: Type of facility to find (e.g., ConstructionFacility)

        Returns:
            List of facilities of the specified type
        """
        return [
            facility
            for facility in self.facilities
            if isinstance(facility, facility_type)
        ]

    def calculate_refinancing_transactions(
        self,
        timeline,
        property_value_series=None,
        noi_series=None,
        financing_cash_flows=None,
    ) -> List[Dict[str, Any]]:
        """
        Calculate refinancing transactions for the financing plan with institutional-grade sizing.

        This handles transitions between facilities, such as construction-to-permanent
        refinancing where the construction loan is paid off and replaced by permanent financing
        using our enhanced "Sizing Trifecta" (LTV + DSCR + Debt Yield).

        Args:
            timeline: Timeline object for the analysis period
            property_value_series: Time series of property values (required for LTV sizing)
            noi_series: Time series of Net Operating Income (required for DSCR/Debt Yield sizing)
            financing_cash_flows: DataFrame with financing cash flows (required for payoff calculation)

        Returns:
            List of refinancing transaction dictionaries with enhanced details:
            - transaction_date: When the refinancing occurs
            - transaction_type: Type of refinancing (e.g., "construction_to_permanent")
            - payoff_facility: Facility being paid off
            - new_facility: New facility being originated
            - payoff_amount: Amount needed to pay off old facility
            - new_loan_amount: Amount of new facility (using Sizing Trifecta)
            - net_proceeds: Net cash to borrower (new loan - payoff - closing costs)
            - sizing_analysis: Detailed breakdown of LTV/DSCR/Debt Yield constraints
            - covenant_monitoring: Setup for ongoing covenant monitoring
            - description: Human-readable transaction description
        """
        transactions = []

        # Handle construction-to-permanent refinancing
        if self.has_construction_financing and self.has_permanent_financing:
            construction_facilities = self.construction_facilities
            permanent_facilities = self.permanent_facilities

            for const_facility in construction_facilities:
                for perm_facility in permanent_facilities:
                    # Determine refinancing timing
                    if (
                        hasattr(perm_facility, "refinance_timing")
                        and perm_facility.refinance_timing
                    ):
                        # Use specified timing
                        refinance_period_index = min(
                            perm_facility.refinance_timing - 1,
                            len(timeline.period_index) - 1,
                        )
                        refinance_period = timeline.period_index[refinance_period_index]
                    else:
                        # Default: refinance at end of construction (middle of timeline)
                        refinance_period_index = len(timeline.period_index) // 2
                        refinance_period = timeline.period_index[refinance_period_index]

                    # Calculate payoff amount using actual construction loan balances
                    payoff_amount = 0.0
                    if financing_cash_flows is not None:
                        try:
                            refinance_date = refinance_period.to_timestamp().date()
                            payoff_amount = const_facility.get_outstanding_balance(
                                refinance_date, financing_cash_flows
                            )
                        except Exception:
                            # Fallback to estimated payoff
                            payoff_amount = (
                                0.0  # Will be calculated by deal orchestrator
                            )

                    # Calculate new loan amount using enhanced Sizing Trifecta
                    new_loan_amount = 0.0
                    sizing_analysis = {}

                    if (
                        hasattr(perm_facility, "loan_amount")
                        and perm_facility.loan_amount
                    ):
                        # Manual override
                        new_loan_amount = perm_facility.loan_amount
                        sizing_analysis = {
                            "sizing_method": "manual",
                            "manual_amount": new_loan_amount,
                            "ltv_constraint": None,
                            "dscr_constraint": None,
                            "debt_yield_constraint": None,
                            "most_restrictive": "manual_override",
                        }
                    elif property_value_series is not None and noi_series is not None:
                        # Automatic sizing using Sizing Trifecta
                        try:
                            property_value = property_value_series.loc[refinance_period]
                            noi = noi_series.loc[refinance_period]

                            # Calculate individual constraints
                            ltv_loan = property_value * perm_facility.ltv_ratio

                            annual_debt_constant = (
                                perm_facility._calculate_annual_debt_constant()
                            )
                            max_debt_service = noi / perm_facility.dscr_hurdle
                            dscr_loan = max_debt_service / annual_debt_constant

                            debt_yield_loan = float("inf")
                            if (
                                perm_facility.debt_yield_hurdle
                                and perm_facility.debt_yield_hurdle > 0
                            ):
                                debt_yield_loan = noi / perm_facility.debt_yield_hurdle

                            # Use most restrictive constraint
                            new_loan_amount = min(ltv_loan, dscr_loan, debt_yield_loan)

                            # Determine which constraint was most restrictive
                            if new_loan_amount == ltv_loan:
                                most_restrictive = "ltv"
                            elif new_loan_amount == dscr_loan:
                                most_restrictive = "dscr"
                            else:
                                most_restrictive = "debt_yield"

                            sizing_analysis = {
                                "sizing_method": "automatic",
                                "property_value": property_value,
                                "noi": noi,
                                "ltv_constraint": ltv_loan,
                                "dscr_constraint": dscr_loan,
                                "debt_yield_constraint": debt_yield_loan
                                if debt_yield_loan != float("inf")
                                else None,
                                "most_restrictive": most_restrictive,
                                "final_amount": new_loan_amount,
                            }

                        except Exception as e:
                            # Fallback to manual amount if available
                            new_loan_amount = 0.0
                            sizing_analysis = {
                                "sizing_method": "error",
                                "error": str(e),
                                "fallback_used": True,
                            }

                    # Calculate closing costs (simplified - typically 1-2% of loan amount)
                    closing_costs = new_loan_amount * 0.015  # 1.5% closing costs

                    # Calculate net proceeds to borrower
                    net_proceeds = new_loan_amount - payoff_amount - closing_costs

                    # Setup covenant monitoring parameters
                    covenant_monitoring = {}
                    if (
                        hasattr(perm_facility, "ongoing_ltv_max")
                        and perm_facility.ongoing_ltv_max
                    ):
                        covenant_monitoring.update({
                            "ongoing_ltv_max": perm_facility.ongoing_ltv_max,
                            "ongoing_dscr_min": perm_facility.ongoing_dscr_min,
                            "ongoing_debt_yield_min": perm_facility.ongoing_debt_yield_min,
                            "monitoring_enabled": True,
                        })
                    else:
                        covenant_monitoring = {"monitoring_enabled": False}

                    # Create transaction record
                    transaction = {
                        "transaction_date": refinance_period,
                        "transaction_type": "construction_to_permanent_refinancing",
                        "payoff_facility": const_facility.name,
                        "new_facility": perm_facility.name,
                        "payoff_amount": payoff_amount,
                        "new_loan_amount": new_loan_amount,
                        "closing_costs": closing_costs,
                        "net_proceeds": net_proceeds,
                        "sizing_analysis": sizing_analysis,
                        "covenant_monitoring": covenant_monitoring,
                        "description": f"Refinance {const_facility.name} with {perm_facility.name} using {sizing_analysis.get('sizing_method', 'unknown')} sizing",
                    }

                    transactions.append(transaction)

        return transactions
