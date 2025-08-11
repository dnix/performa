# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..core.primitives import (
    FloatBetween0And1,
    PositiveFloat,
    PositiveInt,
    Timeline,
)
from ..deal import Deal
from .base import PatternBase


class DevelopmentPattern(PatternBase):
    """
    Ground-up development deal pattern with integrated analysis.

    This pattern models ground-up real estate development projects from
    land acquisition through construction, lease-up, and stabilization.

    Key characteristics:
    - Land acquisition and entitlement
    - Construction financing and permanent takeout
    - Progressive lease-up during and after construction
    - Higher risk/return profile than acquisitions
    - Complex timeline with multiple phases

    Simplified Implementation Note:
    This initial version focuses on residential development with
    essential parameters. Future versions can add complexity like
    mixed-use, multiple phases, and sophisticated waterfall structures.
    """

    # === CORE PROJECT PARAMETERS ===
    project_name: str = Field(..., description="Development project name")
    acquisition_date: date = Field(..., description="Land acquisition closing date")
    land_cost: PositiveFloat = Field(..., description="Land acquisition cost")
    land_closing_costs_rate: FloatBetween0And1 = Field(
        default=0.03, description="Land closing costs as percentage of land cost"
    )

    # === CONSTRUCTION PARAMETERS ===
    construction_budget: PositiveFloat = Field(
        ..., description="Total construction budget"
    )
    construction_start_months: PositiveInt = Field(
        default=6,
        ge=1,
        le=24,
        description="Months after land acquisition to start construction",
    )
    construction_duration_months: PositiveInt = Field(
        default=24, ge=6, le=60, description="Construction duration in months"
    )

    # === RESIDENTIAL DEVELOPMENT SPECS ===
    total_units: PositiveInt = Field(
        ..., description="Total residential units to be built"
    )
    avg_unit_sf: PositiveFloat = Field(..., description="Average square feet per unit")
    target_rent: PositiveFloat = Field(
        ..., description="Target rent per unit at stabilization"
    )

    # === LEASE-UP ASSUMPTIONS ===
    leasing_start_months: PositiveInt = Field(
        default=18,
        ge=6,
        le=48,
        description="Months after land acquisition to start leasing",
    )
    absorption_pace_units_per_month: PositiveFloat = Field(
        default=4.0, ge=0.5, le=20.0, description="Lease-up pace in units per month"
    )
    stabilized_occupancy_rate: FloatBetween0And1 = Field(
        default=0.95, description="Target occupancy rate at stabilization"
    )

    # === CONSTRUCTION FINANCING ===
    construction_ltc_ratio: FloatBetween0And1 = Field(
        default=0.75,
        le=0.85,
        description="Loan-to-cost ratio for construction financing",
    )
    construction_interest_rate: FloatBetween0And1 = Field(
        default=0.08, description="Interest rate for construction loan"
    )
    construction_fee_rate: FloatBetween0And1 = Field(
        default=0.02, description="Origination fee rate for construction loan"
    )

    # === PERMANENT FINANCING ===
    permanent_ltv_ratio: FloatBetween0And1 = Field(
        default=0.70, le=0.80, description="Loan-to-value ratio for permanent financing"
    )
    permanent_interest_rate: FloatBetween0And1 = Field(
        default=0.065, description="Interest rate for permanent loan"
    )
    permanent_loan_term_years: PositiveInt = Field(
        default=10, ge=5, le=30, description="Permanent loan term in years"
    )
    permanent_amortization_years: PositiveInt = Field(
        default=30,
        ge=20,
        le=40,
        description="Permanent loan amortization period in years",
    )

    # === PARTNERSHIP STRUCTURE ===
    distribution_method: Literal["pari_passu", "waterfall"] = Field(
        default="waterfall", description="Partnership distribution methodology"
    )
    gp_share: FloatBetween0And1 = Field(
        default=0.20, description="General Partner ownership percentage"
    )
    lp_share: FloatBetween0And1 = Field(
        default=0.80, description="Limited Partner ownership percentage"
    )
    preferred_return: FloatBetween0And1 = Field(
        default=0.08, description="LP preferred return rate (for waterfall structures)"
    )

    # === EXIT ASSUMPTIONS ===
    hold_period_years: PositiveInt = Field(
        default=7,
        ge=3,
        le=15,
        description="Investment hold period in years (from land acquisition)",
    )
    exit_cap_rate: FloatBetween0And1 = Field(
        default=0.055, description="Exit capitalization rate for sale valuation"
    )
    exit_costs_rate: FloatBetween0And1 = Field(
        default=0.015, description="Exit transaction costs as percentage of sale price"
    )

    @field_validator("permanent_amortization_years")
    @classmethod
    def validate_amortization_vs_term(cls, v, info):
        """Ensure amortization period is longer than loan term."""
        if "permanent_loan_term_years" in info.data:
            loan_term = info.data["permanent_loan_term_years"]
            if v < loan_term:
                raise ValueError(
                    f"Amortization period ({v} years) must be >= loan term ({loan_term} years)"
                )
        return v

    @field_validator("leasing_start_months")
    @classmethod
    def validate_leasing_vs_construction(cls, v, info):
        """Ensure leasing doesn't start before construction."""
        if "construction_start_months" in info.data:
            construction_start = info.data["construction_start_months"]
            if v < construction_start:
                raise ValueError(
                    f"Leasing start ({v} months) should be >= construction start ({construction_start} months)"
                )
        return v

    @model_validator(mode="after")
    def validate_partnership_shares(self) -> "DevelopmentPattern":
        """Ensure GP and LP shares sum to 100%."""
        total_share = self.gp_share + self.lp_share
        if abs(total_share - 1.0) > 0.001:  # Allow for floating point precision
            raise ValueError(
                f"GP share ({self.gp_share:.1%}) + LP share ({self.lp_share:.1%}) must equal 100%"
            )
        return self

    def _derive_timeline(self) -> Timeline:
        """Derive timeline from hold period."""
        return Timeline(
            start_date=self.acquisition_date,
            duration_months=self.hold_period_years * 12,
        )

    def create(self) -> Deal:
        """
        Create the complete development deal.

        Note: This is a simplified implementation focusing on essential
        development deal components. Future versions can add complexity
        like mixed-use buildings, multiple phases, and sophisticated
        waterfall structures.
        """

        # For now, return a NotImplementedError with guidance
        # This maintains the interface contract while indicating
        # that full implementation is deferred

        raise NotImplementedError(
            "DevelopmentPattern.create() is not yet fully implemented. "
            "Development deals are highly complex and require careful modeling of:\n"
            "- Multi-phase construction timelines\n"
            "- Progressive absorption during lease-up\n"
            "- Construction-to-permanent loan conversion\n"
            "- Complex waterfall structures\n"
            "\n"
            "For now, use the existing create_development_deal() function "
            "or focus on acquisition patterns (StabilizedAcquisitionPattern, "
            "ValueAddAcquisitionPattern) which are fully implemented.\n"
            "\n"
            "The DevelopmentPattern interface is established and can be "
            "enhanced in future development cycles."
        )
