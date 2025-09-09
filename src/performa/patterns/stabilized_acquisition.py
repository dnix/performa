# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Stabilized acquisition deal pattern implementation.

This pattern models the acquisition of existing, cash-flowing properties
with stable operations and tenants - the most common institutional real
estate investment strategy.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..asset.residential import (
    ResidentialCreditLoss,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialOpExItem,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
    ResidentialVacantUnit,
)
from ..core.primitives import (
    FloatBetween0And1,
    FrequencyEnum,
    PercentageGrowthRate,
    PositiveFloat,
    PositiveInt,
    PropertyAttributeKey,
    Timeline,
    UnleveredAggregateLineKey,
)
from ..deal import (
    AcquisitionTerms,
    Deal,
    create_simple_partnership,
)
from ..debt import FinancingPlan, PermanentFacility
from ..valuation import DirectCapValuation
from .base import PatternBase


class StabilizedAcquisitionPattern(PatternBase):
    """
    Stabilized acquisition deal pattern with integrated analysis.

    This pattern models the most common real estate investment strategy:
    acquiring an existing, cash-flowing property with stable tenants and
    operating income for long-term hold and eventual sale.

    Key characteristics:
    - Property is already stabilized (occupied, market rents)
    - No major renovations or lease-up required
    - Standard permanent financing
    - Simple buy-hold-sell strategy

    This is the foundational pattern for most institutional real estate investments.
    """

    # === CORE DEAL PARAMETERS ===
    property_name: str = Field(..., description="Property name for identification")
    acquisition_date: date = Field(..., description="Property acquisition closing date")
    acquisition_price: PositiveFloat = Field(
        ..., description="Total property purchase price"
    )
    closing_costs_rate: FloatBetween0And1 = Field(
        default=0.025, description="Closing costs as percentage of purchase price"
    )

    # === PROPERTY SPECIFICATIONS ===
    # Simplified residential property model - can be expanded for office later
    total_units: PositiveInt = Field(
        ..., description="Total number of residential units"
    )
    avg_unit_sf: PositiveFloat = Field(..., description="Average square feet per unit")
    current_avg_rent: PositiveFloat = Field(
        ..., description="Current average rent per unit"
    )
    occupancy_rate: FloatBetween0And1 = Field(
        default=0.95, description="Current occupancy rate (decimal)"
    )

    # === FINANCING TERMS ===
    ltv_ratio: FloatBetween0And1 = Field(
        default=0.75, le=0.80, description="Loan-to-value ratio for permanent financing"
    )
    interest_rate: FloatBetween0And1 = Field(
        default=0.055, description="Fixed interest rate for permanent loan"
    )
    loan_term_years: PositiveInt = Field(
        default=10, ge=5, le=30, description="Loan term in years"
    )
    amortization_years: PositiveInt = Field(
        default=30, ge=20, le=40, description="Loan amortization period in years"
    )
    dscr_hurdle: PositiveFloat = Field(
        default=1.25, description="Minimum debt service coverage ratio required"
    )

    # === PARTNERSHIP STRUCTURE ===
    distribution_method: Literal["pari_passu", "waterfall"] = Field(
        default="pari_passu", description="Partnership distribution methodology"
    )
    gp_share: FloatBetween0And1 = Field(
        default=0.20, description="General Partner ownership percentage"
    )
    lp_share: FloatBetween0And1 = Field(
        default=0.80, description="Limited Partner ownership percentage"
    )

    # === EXIT ASSUMPTIONS ===
    hold_period_years: PositiveInt = Field(
        default=5, ge=1, le=10, description="Investment hold period in years"
    )
    exit_cap_rate: FloatBetween0And1 = Field(
        default=0.055, description="Exit capitalization rate for sale valuation"
    )
    exit_costs_rate: FloatBetween0And1 = Field(
        default=0.015, description="Exit transaction costs as percentage of sale price"
    )

    @field_validator("amortization_years")
    @classmethod
    def validate_amortization_vs_term(cls, v, info):
        """Ensure amortization period is longer than loan term."""
        if "loan_term_years" in info.data:
            loan_term = info.data["loan_term_years"]
            if v < loan_term:
                raise ValueError(
                    f"Amortization period ({v} years) must be >= loan term ({loan_term} years)"
                )
        return v

    @model_validator(mode="after")
    def validate_partnership_shares(self) -> "StabilizedAcquisitionPattern":
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
        Create a complete Deal object from the pattern parameters.

        This method assembles all components needed for a stabilized acquisition:
        - ResidentialProperty with existing tenant base and market operations
        - Permanent financing with standard loan terms
        - GP/LP partnership structure
        - AcquisitionTerms and exit valuation strategy

        Returns:
            Complete Deal object ready for analysis via analyze()
        """

        # === Step 1: Create Property Asset ===

        # Create rollover profile for standard residential leasing

        # Market terms for new leases
        market_terms = ResidentialRolloverLeaseTerms(
            market_rent=self.current_avg_rent,
            market_rent_growth=PercentageGrowthRate(
                name="Market Rent Growth",
                value=0.03,  # 3% annual growth
            ),
            renewal_rent_increase_percent=0.04,  # 4% renewal increase
            concessions_months=0,  # No concessions for stabilized property
        )

        # Renewal terms (typically same as market for stabilized properties)
        renewal_terms = ResidentialRolloverLeaseTerms(
            market_rent=self.current_avg_rent,
            market_rent_growth=PercentageGrowthRate(
                name="Renewal Rent Growth", value=0.03
            ),
            renewal_rent_increase_percent=0.04,
            concessions_months=0,
        )

        # Create rollover profile
        rollover_profile = ResidentialRolloverProfile(
            name="Standard Residential Rollover",
            renewal_probability=0.65,  # 65% renewal rate for stabilized property
            downtime_months=1,  # 1 month turnover time
            term_months=12,  # 12-month leases
            market_terms=market_terms,
            renewal_terms=renewal_terms,
        )

        # Create unit specifications (simplified to single unit type for now)
        unit_specs = [
            ResidentialUnitSpec(
                unit_type_name="Standard Unit",
                unit_count=int(
                    self.total_units * self.occupancy_rate
                ),  # Occupied units
                current_avg_monthly_rent=self.current_avg_rent,
                avg_area_sf=self.avg_unit_sf,
                rollover_profile=rollover_profile,
                lease_start_date=self.acquisition_date,
            )
        ]

        # Create vacant units for remaining occupancy
        vacant_units = []
        vacant_count = self.total_units - int(self.total_units * self.occupancy_rate)
        if vacant_count > 0:
            vacant_units = [
                ResidentialVacantUnit(
                    unit_type_name="Standard Unit",
                    unit_count=vacant_count,
                    avg_area_sf=self.avg_unit_sf,
                    market_rent=self.current_avg_rent,
                    rollover_profile=rollover_profile,  # Use same rollover profile
                )
            ]

        rent_roll = ResidentialRentRoll(
            unit_specs=unit_specs,
            vacant_units=vacant_units,
        )

        # Create basic expenses (stabilized property has standard OpEx)
        timeline = self.get_timeline()

        expenses = ResidentialExpenses(
            operating_expenses=[
                ResidentialOpExItem(
                    name="Property Management",
                    timeline=timeline,
                    value=0.04,  # 4% of effective gross income
                    frequency=FrequencyEnum.MONTHLY,
                    reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
                ),
                ResidentialOpExItem(
                    name="Maintenance & Repairs",
                    timeline=timeline,
                    value=500.0,  # $500 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Maintenance Inflation", value=0.03
                    ),
                ),
                ResidentialOpExItem(
                    name="Insurance",
                    timeline=timeline,
                    value=350.0,  # $350 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Insurance Inflation", value=0.04
                    ),
                ),
                ResidentialOpExItem(
                    name="Property Taxes",
                    timeline=timeline,
                    value=self.acquisition_price * 0.011,  # 1.1% of acquisition price
                    frequency=FrequencyEnum.ANNUAL,
                    growth_rate=PercentageGrowthRate(name="Tax Growth", value=0.025),
                ),
                ResidentialOpExItem(
                    name="Utilities (Common Area)",
                    timeline=timeline,
                    value=180.0,  # $180 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Utility Inflation", value=0.04
                    ),
                ),
                ResidentialOpExItem(
                    name="Administrative",
                    timeline=timeline,
                    value=120.0,  # $120 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                ),
            ]
        )

        # Create basic losses (vacancy and collection)
        losses = ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(
                rate=1.0 - self.occupancy_rate,
            ),
            credit_loss=ResidentialCreditLoss(
                rate=0.02,  # 2% collection loss
            ),
        )

        # Create the property
        total_area = self.total_units * self.avg_unit_sf
        property_asset = ResidentialProperty(
            name=self.property_name,
            address=None,  # Optional for patterns
            gross_area=total_area * 1.15,  # 15% efficiency factor for common areas
            net_rentable_area=total_area,
            unit_mix=rent_roll,
            expenses=expenses,
            losses=losses,
            miscellaneous_income=[],
            capital_plans=[],  # No major CapEx for stabilized acquisition
            absorption_plans=[],  # No absorption needed
        )

        # === Step 2: Create Acquisition Terms ===
        acquisition = AcquisitionTerms(
            name=f"{self.property_name} Acquisition",
            timeline=Timeline.from_dates(
                start_date=self.acquisition_date,
                end_date=self.acquisition_date,  # Single day acquisition
            ),
            value=self.acquisition_price,
            acquisition_date=self.acquisition_date,
            closing_costs_rate=self.closing_costs_rate,
        )

        # === Step 3: Create Financing Plan ===
        # Calculate loan amount based on LTV of acquisition price
        loan_amount = self.acquisition_price * self.ltv_ratio
        
        permanent_facility = PermanentFacility(
            name=f"{self.property_name} Permanent Loan",
            loan_amount=loan_amount,  # Explicit sizing based on acquisition price
            ltv_ratio=self.ltv_ratio,
            interest_rate={
                "details": {"rate_type": "fixed", "rate": self.interest_rate}
            },
            loan_term_years=self.loan_term_years,
            amortization_years=self.amortization_years,
            dscr_hurdle=self.dscr_hurdle,
        )

        financing_plan = FinancingPlan(
            name=f"{self.property_name} Financing", facilities=[permanent_facility]
        )

        # === Step 4: Create Partnership Structure ===
        partnership = create_simple_partnership(
            gp_name="Sponsor",
            lp_name="Investor",
            gp_share=self.gp_share,
            lp_share=self.lp_share,
            distribution_method=self.distribution_method,
        )

        # === Step 5: Create Exit Valuation ===
        reversion = DirectCapValuation(
            name=f"{self.property_name} Sale",
            cap_rate=self.exit_cap_rate,
            transaction_costs_rate=self.exit_costs_rate,
            hold_period_months=self.hold_period_years * 12,
            noi_basis_kind="LTM",  # Use trailing 12 months for realistic exit
        )

        # === Step 6: Assemble and Return Deal ===
        return Deal(
            name=f"{self.property_name} Stabilized Acquisition",
            asset=property_asset,
            acquisition=acquisition,
            financing=financing_plan,
            equity_partners=partnership,
            exit_valuation=reversion,
        )
