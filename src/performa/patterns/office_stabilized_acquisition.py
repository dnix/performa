# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Office stabilized acquisition deal pattern implementation.

This pattern models the acquisition of existing, cash-flowing office properties
with stable operations and tenants.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..asset.office import (
    DirectLeaseTerms,
    OfficeExpenses,
    OfficeLeaseSpec,
    OfficeLosses,
    OfficeProperty,
    OfficeRentRoll,
    OfficeRolloverLeaseTerms,
    OfficeRolloverProfile,
    OfficeVacantSuite,
)
from ..core.primitives import (
    FloatBetween0And1,
    FrequencyEnum,
    LeaseTypeEnum,
    PercentageGrowthRate,
    PositiveFloat,
    PositiveInt,
    PropertyAttributeKey,
    Timeline,
    UponExpirationEnum,
)
from ..deal import (
    AcquisitionTerms,
    Deal,
    create_simple_partnership,
)
from ..debt import FinancingPlan, PermanentFacility
from ..valuation import DirectCapValuation
from .base import PatternBase


class OfficeStabilizedAcquisitionPattern(PatternBase):
    """
    Office stabilized acquisition deal pattern with integrated analysis.

    This pattern models the acquisition of existing, cash-flowing office properties
    with stable tenants and operating income for long-term hold and eventual sale.

    Key office characteristics:
    - Property measured in net rentable square feet
    - Rent calculated as $/SF/year
    - Current occupancy rate as percentage of NRA
    - Standard permanent financing
    - Simple buy-hold-sell strategy

    Example:
        ```python
        pattern = OfficeStabilizedAcquisitionPattern(
            property_name="Downtown Office Building",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=15_000_000,
            net_rentable_area=45_000,
            current_rent_psf=32.0,
            occupancy_rate=0.92,
            ltv_ratio=0.75,
            hold_period_years=7
        )
        deal = pattern.create()
        results = pattern.analyze()
        ```
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

    # === OFFICE PROPERTY SPECIFICATIONS ===
    net_rentable_area: PositiveFloat = Field(
        ..., description="Total net rentable area in square feet"
    )
    current_rent_psf: PositiveFloat = Field(
        default=20.0, description="Current average rent per square foot per year"
    )
    occupancy_rate: FloatBetween0And1 = Field(
        default=0.95, description="Current occupancy rate (decimal)"
    )
    avg_lease_size_sf: PositiveFloat = Field(
        default=5_000.0, description="Average lease size in square feet"
    )
    avg_lease_term_months: PositiveInt = Field(
        default=60, ge=12, le=120, description="Average lease term in months"
    )

    # === OPERATING ASSUMPTIONS ===
    operating_expense_psf: PositiveFloat = Field(
        default=12.0, description="Operating expenses per square foot per year"
    )
    management_fee_rate: FloatBetween0And1 = Field(
        default=0.03, description="Property management fee as percentage of EGI"
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
        default=7, ge=1, le=15, description="Investment hold period in years"
    )
    exit_cap_rate: FloatBetween0And1 = Field(
        default=0.060, description="Exit capitalization rate for sale valuation"
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
    def validate_partnership_shares(self) -> "OfficeStabilizedAcquisitionPattern":
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
        Create stabilized office acquisition Deal object.

        Returns:
            Complete Deal object ready for analysis
        """

        # === STEP 1: OFFICE PROPERTY ===

        # Create market lease terms for rollover
        market_terms = OfficeRolloverLeaseTerms(
            market_rent=self.current_rent_psf,  # Already annual rent PSF
            term_months=self.avg_lease_term_months,
            growth_rate=PercentageGrowthRate(
                name="Market Rent Growth",
                value=0.025,  # 2.5% annual growth
            ),
        )

        # Create renewal terms (typically with modest discount)
        renewal_terms = OfficeRolloverLeaseTerms(
            market_rent=self.current_rent_psf * 0.98,  # 2% renewal discount on annual rent PSF
            term_months=self.avg_lease_term_months,
            growth_rate=PercentageGrowthRate(name="Renewal Rent Growth", value=0.03),
        )

        # Create rollover profile
        rollover_profile = OfficeRolloverProfile(
            name="Standard Office Rollover",
            renewal_probability=0.70,  # 70% renewal rate for stabilized office
            downtime_months=3,  # 3 months turnover time for office
            term_months=self.avg_lease_term_months,
            market_terms=market_terms,
            renewal_terms=renewal_terms,
            upon_expiration=UponExpirationEnum.MARKET,
        )

        # Calculate occupied and vacant areas
        occupied_area = int(self.net_rentable_area * self.occupancy_rate)
        vacant_area = int(self.net_rentable_area - occupied_area)

        # Create occupied lease specs (simplified to single lease for now)
        occupied_lease_specs = []
        if occupied_area > 0:
            occupied_lease_spec = OfficeLeaseSpec(
                tenant_name="Stabilized Tenant Mix",
                suite="Occupied Space",
                floor="Multiple",
                area=occupied_area,
                base_rent_value=self.current_rent_psf,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency=FrequencyEnum.ANNUAL,  # Fix: current_rent_psf is annual
                term_months=self.avg_lease_term_months,
                start_date=self.acquisition_date,
                upon_expiration=UponExpirationEnum.MARKET,
                lease_type=LeaseTypeEnum.GROSS,
                rollover_profile=rollover_profile,
            )
            occupied_lease_specs.append(occupied_lease_spec)

        # Create vacant suites
        vacant_suites = []
        if vacant_area > 0:
            vacant_suite = OfficeVacantSuite(
                suite="Vacant Space",
                floor="Multiple",
                area=vacant_area,
                use_type="office",
                market_terms=DirectLeaseTerms(
                    base_rent_value=self.current_rent_psf,
                    base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                    base_rent_frequency=FrequencyEnum.ANNUAL,  # Fix: current_rent_psf is annual
                    term_months=self.avg_lease_term_months,
                    upon_expiration=UponExpirationEnum.MARKET,
                ),
                rollover_profile=rollover_profile,
            )
            vacant_suites.append(vacant_suite)

        # Create operating expenses (simplified for pattern)
        expenses = OfficeExpenses(operating_expenses=[])

        # Create basic losses
        losses = OfficeLosses()  # Use defaults

        # Create rent roll
        rent_roll = OfficeRentRoll(
            leases=occupied_lease_specs,
            vacant_suites=vacant_suites,
        )

        # Create office property
        property_obj = OfficeProperty(
            name=self.property_name,
            address=None,
            net_rentable_area=self.net_rentable_area,
            gross_area=self.net_rentable_area
            * 1.11,  # Typical office efficiency factor
            rent_roll=rent_roll,
            expenses=expenses,
            losses=losses,
        )

        # === STEP 2: ACQUISITION TERMS ===
        acquisition = AcquisitionTerms(
            name=f"{self.property_name} Acquisition",
            timeline=Timeline(
                start_date=self.acquisition_date,
                duration_months=2,  # 60 days to close
            ),
            value=self.acquisition_price,
            acquisition_date=self.acquisition_date,
            closing_costs_rate=self.closing_costs_rate,
        )

        # === STEP 3: FINANCING ===
        loan_amount = self.acquisition_price * self.ltv_ratio

        permanent_facility = PermanentFacility(
            name=f"{self.property_name} Permanent Loan",
            loan_amount=loan_amount,
            interest_rate=self.interest_rate,
            loan_term_months=self.loan_term_years * 12,
            amortization_months=self.amortization_years * 12,
            ongoing_dscr_min=self.dscr_hurdle,
        )

        financing = FinancingPlan(
            name=f"{self.property_name} Financing",
            facilities=[permanent_facility],
        )

        # === STEP 4: PARTNERSHIP ===
        partnership = create_simple_partnership(
            gp_name=f"{self.property_name} GP",
            lp_name=f"{self.property_name} LP",
            gp_share=self.gp_share,
            lp_share=self.lp_share,
        )

        # === STEP 5: EXIT VALUATION ===
        reversion = DirectCapValuation(
            name=f"{self.property_name} Sale",
            cap_rate=self.exit_cap_rate,
            transaction_costs_rate=self.exit_costs_rate,
            hold_period_months=self.hold_period_years * 12,
            noi_basis_kind="LTM",  # Use trailing 12 months for realistic exit
        )

        # === STEP 6: ASSEMBLE DEAL ===
        return Deal(
            name=f"{self.property_name} Acquisition",
            asset=property_obj,
            acquisition=acquisition,
            financing=financing,
            partnership=partnership,
            exit_valuation=reversion,
        )
