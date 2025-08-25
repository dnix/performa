# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Office development deal pattern implementation.

This pattern models ground-up office development projects using SF-based
metrics and office-specific leasing assumptions.
"""

from __future__ import annotations

from datetime import date
from typing import List

from pydantic import Field

from ..asset.office import (
    DirectLeaseTerms,
    EqualSpreadPace,
    OfficeAbsorptionPlan,
    OfficeDevelopmentBlueprint,
    OfficeVacantSuite,
    SpaceFilter,
)
from ..core.capital import CapitalItem, CapitalPlan
from ..core.primitives import (
    AssetTypeEnum,
    FirstOnlyDrawSchedule,
    FloatBetween0And1,
    InterestCalculationMethod,
    PositiveFloat,
    PositiveInt,
    ProgramUseEnum,
    PropertyAttributeKey,
    Timeline,
    UponExpirationEnum,
)
from ..deal import (
    AcquisitionTerms,
    CarryPromote,
    Deal,
    Partner,
    PartnershipStructure,
)
from ..debt import (
    ConstructionFacility,
    DebtTranche,
    FinancingPlan,
    FixedRate,
    InterestRate,
    PermanentFacility,
)
from ..development import DevelopmentProject
from ..valuation import ReversionValuation
from .base import DevelopmentPatternBase


class OfficeDevelopmentPattern(DevelopmentPatternBase):
    """
    Office development deal pattern with SF-based metrics.

    This pattern models ground-up office development projects from land acquisition
    through construction, lease-up, and stabilization using natural office industry
    parameters based on square footage.

    Key Office-Specific Features:
    - Square footage-based building specifications
    - Office leasing metrics ($/SF/year, average lease sizes)
    - Floor-by-floor vacant inventory modeling
    - Office absorption strategies (deals per month)
    - Office construction costs ($/SF)

    Example:
        ```python
        pattern = OfficeDevelopmentPattern(
            project_name="Downtown Office Tower",
            acquisition_date=date(2024, 1, 1),
            land_cost=5_000_000,
            net_rentable_area=45_000,
            floors=3,
            target_rent_psf=35.0,
            construction_cost_psf=350.0
        )
        deal = pattern.create()
        results = pattern.analyze()
        ```
    """

    # === BUILDING SPECIFICATIONS ===
    net_rentable_area: PositiveFloat = Field(
        ..., description="Total net rentable area in square feet"
    )
    gross_area: PositiveFloat = Field(
        default=None,
        description="Total gross area (defaults to net rentable area * 1.11)",
    )
    floors: PositiveInt = Field(
        default=3, ge=1, le=50, description="Number of floors in the building"
    )

    # === LEASING ASSUMPTIONS ===
    target_rent_psf: PositiveFloat = Field(
        ..., description="Target base rent in $/SF/year (e.g., $35.00)"
    )
    average_lease_size_sf: PositiveFloat = Field(
        default=5_000.0,
        ge=1_000.0,
        le=50_000.0,
        description="Average lease size in square feet",
    )
    minimum_lease_size_sf: PositiveFloat = Field(
        default=2_500.0,
        ge=500.0,
        le=25_000.0,
        description="Minimum viable lease size in square feet",
    )
    lease_term_months: PositiveInt = Field(
        default=84,  # 7 years
        ge=36,
        le=240,
        description="Standard lease term in months",
    )

    # === ABSORPTION STRATEGY ===
    leasing_start_months: PositiveInt = Field(
        default=18,
        ge=6,
        le=48,
        description="Months after land acquisition to start leasing",
    )
    total_leasing_deals: PositiveInt = Field(
        default=9,
        ge=3,
        le=50,
        description="Total number of leases to execute during lease-up",
    )
    leasing_frequency_months: PositiveInt = Field(
        default=2, ge=1, le=12, description="Months between new lease executions"
    )
    stabilized_occupancy_rate: FloatBetween0And1 = Field(
        default=0.95, description="Target occupancy rate at stabilization"
    )

    # === CONSTRUCTION COST MODEL ===
    construction_cost_psf: PositiveFloat = Field(
        default=350.0, description="Construction cost per square foot of gross area"
    )
    soft_costs_rate: FloatBetween0And1 = Field(
        default=0.15, description="Soft costs as percentage of hard construction costs"
    )
    developer_fee_rate: FloatBetween0And1 = Field(
        default=0.05,
        description="Developer fee as percentage of total construction costs",
    )

    # === COMPUTED FIELDS ===

    @property
    def gross_area_computed(self) -> float:
        """Calculate gross area if not provided (typically 11% larger than net)."""
        if self.gross_area is not None:
            return self.gross_area
        return self.net_rentable_area * 1.11

    @property
    def average_floor_size_sf(self) -> float:
        """Calculate average floor size."""
        return self.net_rentable_area / self.floors

    @property
    def hard_construction_costs(self) -> float:
        """Calculate hard construction costs."""
        return self.gross_area_computed * self.construction_cost_psf

    @property
    def soft_costs(self) -> float:
        """Calculate soft costs (professional fees, permits, etc.)."""
        return self.hard_construction_costs * self.soft_costs_rate

    @property
    def developer_fee(self) -> float:
        """Calculate developer fee."""
        return (
            self.hard_construction_costs + self.soft_costs
        ) * self.developer_fee_rate

    @property
    def total_construction_budget(self) -> float:
        """Calculate total construction budget."""
        return self.hard_construction_costs + self.soft_costs + self.developer_fee

    @property
    def total_project_cost(self) -> float:
        """Calculate total project cost including land (excluding closing costs for development cost comparison)."""
        return self.land_cost + self.total_construction_budget

    def create(self) -> Deal:
        """
        Create the complete office development deal.

        This method assembles all components needed for office development analysis:
        - Land acquisition with closing costs
        - Construction capital plan with proper timelines
        - Office development blueprint with vacant inventory
        - Office absorption plan with leasing strategy
        - Construction-to-permanent financing
        - Partnership structure with promote
        - Exit valuation strategy

        Returns:
            Complete Deal object ready for analysis
        """

        # === STEP 1: PROJECT TIMELINE ===
        construction_start_date = self.acquisition_date
        # Calculate construction timeline duration
        total_timeline_months = max(
            self.construction_start_months
            + self.construction_duration_months
            + 12,  # +12 for stabilization
            self.hold_period_years * 12,  # Or hold period, whichever is longer
        )

        timeline = Timeline(
            start_date=construction_start_date, duration_months=total_timeline_months
        )

        # === STEP 2: CAPITAL EXPENDITURE PLAN ===
        capital_items = [
            CapitalItem(
                name="Land Acquisition",
                work_type="land",
                value=self.land_cost,
                draw_schedule=FirstOnlyDrawSchedule(),
                timeline=timeline,
            ),
            CapitalItem(
                name="Construction - Core & Shell",
                work_type="construction",
                value=self.hard_construction_costs,
                draw_schedule=FirstOnlyDrawSchedule(),
                timeline=timeline,
            ),
            CapitalItem(
                name="Professional Fees",
                work_type="soft_costs",
                value=self.soft_costs,
                draw_schedule=FirstOnlyDrawSchedule(),
                timeline=timeline,
            ),
            CapitalItem(
                name="Developer Fee",
                work_type="developer",
                value=self.developer_fee,
                draw_schedule=FirstOnlyDrawSchedule(),
                timeline=timeline,
            ),
        ]

        capital_plan = CapitalPlan(
            name=f"{self.project_name} Construction Plan", capital_items=capital_items
        )

        # === STEP 3: VACANT OFFICE SPACE INVENTORY ===
        vacant_suites: List[OfficeVacantSuite] = []

        for floor_num in range(1, self.floors + 1):
            suite = OfficeVacantSuite(
                suite=f"Floor {floor_num}",
                floor=str(floor_num),
                area=self.average_floor_size_sf,
                use_type=ProgramUseEnum.OFFICE,
                is_divisible=True,
                subdivision_average_lease_area=self.average_lease_size_sf,
                subdivision_minimum_lease_area=self.minimum_lease_size_sf,
            )
            vacant_suites.append(suite)

        # === STEP 4: OFFICE ABSORPTION PLAN ===
        leasing_start_date = date(
            self.acquisition_date.year + (self.leasing_start_months // 12),
            self.acquisition_date.month + (self.leasing_start_months % 12),
            self.acquisition_date.day,
        )

        absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
            name=f"{self.project_name} Lease-Up Plan",
            space_filter=SpaceFilter(
                floors=[str(i) for i in range(1, self.floors + 1)],
                use_types=[ProgramUseEnum.OFFICE],
            ),
            start_date_anchor=leasing_start_date,
            pace=EqualSpreadPace(
                total_deals=self.total_leasing_deals,
                frequency_months=self.leasing_frequency_months,
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=self.target_rent_psf,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                term_months=self.lease_term_months,
                upon_expiration=UponExpirationEnum.MARKET,
            ),
        )

        # === STEP 5: OFFICE DEVELOPMENT BLUEPRINT ===
        office_blueprint = OfficeDevelopmentBlueprint(
            name=self.project_name,
            vacant_inventory=vacant_suites,
            absorption_plan=absorption_plan,
        )

        # === STEP 6: DEVELOPMENT PROJECT ===
        project = DevelopmentProject(
            name=f"{self.project_name} Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=self.gross_area_computed,
            net_rentable_area=self.net_rentable_area,
            construction_plan=capital_plan,
            blueprints=[office_blueprint],
        )

        # === STEP 7: ACQUISITION TERMS ===
        acquisition = AcquisitionTerms(
            name="Land Acquisition",
            timeline=Timeline(start_date=self.acquisition_date, duration_months=1),
            value=self.land_cost,
            acquisition_date=self.acquisition_date,
            closing_costs_rate=self.land_closing_costs_rate,
        )

        # === STEP 8: CONSTRUCTION FINANCING ===
        construction_loan = ConstructionFacility(
            name="Construction Facility",
            tranches=[
                DebtTranche(
                    name="Senior Construction",
                    interest_rate=InterestRate(
                        details=FixedRate(rate=self.construction_interest_rate)
                    ),
                    fee_rate=self.construction_fee_rate,
                    ltc_threshold=self.construction_ltc_ratio,
                )
            ],
            interest_calculation_method=getattr(
                InterestCalculationMethod, self.interest_calculation_method
            ),
            fund_interest_from_reserve=True,
            interest_reserve_rate=self.interest_reserve_rate,
        )

        # === STEP 9: PERMANENT FINANCING ===
        permanent_loan = PermanentFacility(
            name="Permanent Facility",
            loan_amount=18_000_000,  # Will be auto-sized based on stabilized value
            interest_rate=InterestRate(
                details=FixedRate(rate=self.permanent_interest_rate)
            ),
            loan_term_years=self.permanent_loan_term_years,
            amortization_years=self.permanent_amortization_years,
            ltv_ratio=self.permanent_ltv_ratio,
            dscr_hurdle=1.25,
            origination_fee_rate=0.005,
        )

        financing_plan = FinancingPlan(
            name="Construction-to-Permanent Financing",
            facilities=[construction_loan, permanent_loan],
        )

        # === STEP 10: PARTNERSHIP STRUCTURE ===
        gp_partner = Partner(
            name="Development GP",
            kind="GP",
            share=self.gp_share,
        )

        lp_partner = Partner(
            name="Institutional LP",
            kind="LP",
            share=self.lp_share,
        )

        partnership = PartnershipStructure(
            partners=[gp_partner, lp_partner],
            distribution_method=self.distribution_method,
            promote=CarryPromote(
                pref_hurdle_rate=self.preferred_return,
                promote_rate=self.promote_tier_1,
            )
            if self.distribution_method == "waterfall"
            else None,
        )

        # === STEP 11: EXIT STRATEGY ===
        exit_valuation = ReversionValuation(
            name="Stabilized Disposition",
            cap_rate=self.exit_cap_rate,
            transaction_costs_rate=self.exit_costs_rate,
            hold_period_months=self.hold_period_years * 12,
        )

        # === STEP 12: ASSEMBLE COMPLETE DEAL ===
        deal = Deal(
            name=f"{self.project_name} Development Deal",
            description=f"Office development - {self.net_rentable_area:,.0f} SF at ${self.target_rent_psf:.2f}/SF",
            asset=project,
            acquisition=acquisition,
            financing=financing_plan,
            exit_valuation=exit_valuation,
            equity_partners=partnership,
        )

        return deal
