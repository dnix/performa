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

from dateutil.relativedelta import relativedelta
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
    FixedRate,
    InterestRate,
)
from ..debt.constructs import create_construction_to_permanent_plan
from ..development import DevelopmentProject
from ..valuation import DirectCapValuation
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

    def _derive_timeline(self) -> Timeline:
        """Override to add buffer for exit transaction."""
        return Timeline(
            start_date=self.acquisition_date,
            duration_months=self.hold_period_years * 12
            + 6,  # Add 6 months buffer for exit and wind-down
        )

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

        # Calculate when space becomes available (after construction)
        space_available_date = self.acquisition_date + relativedelta(
            months=self.construction_start_months + self.construction_duration_months
        )

        for floor_num in range(1, self.floors + 1):
            suite = OfficeVacantSuite(
                suite=f"Floor {floor_num}",
                floor=str(floor_num),
                area=self.average_floor_size_sf,
                use_type=ProgramUseEnum.OFFICE,
                is_divisible=True,
                subdivision_average_lease_area=self.average_lease_size_sf,
                subdivision_minimum_lease_area=self.minimum_lease_size_sf,
                available_date=space_available_date,  # CRITICAL: Set when space is ready
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
                base_rent_value=self.target_rent_psf
                / 12,  # Convert annual $/SF to monthly
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
        # For multi-tranche mode, the facility will calculate loan amount
        # based on LTC and capital uses in the ledger during analysis
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
            # project_cost is passed via DealContext during analysis
            interest_calculation_method=getattr(
                InterestCalculationMethod, self.interest_calculation_method
            ),
            fund_interest_from_reserve=True,
            interest_reserve_rate=self.interest_reserve_rate,
        )

        # === STEP 9: PERMANENT FINANCING ===
        # Calculate expected stabilized value for loan sizing
        # target_rent_psf is already annual, so no * 12 needed
        annual_stabilized_rent = self.target_rent_psf * self.net_rentable_area * 0.95
        # Assume OpEx = 35% of EGI for office
        stabilized_noi = annual_stabilized_rent * 0.65
        stabilized_value = stabilized_noi / self.exit_cap_rate

        # Calculate permanent loan amount based on stabilized value
        perm_loan_amount = stabilized_value * self.permanent_ltv_ratio

        # === DEAL FEASIBILITY GUARD RAILS ===
        construction_loan_amount = self.total_project_cost * self.construction_ltc_ratio

        # Check 1: Value creation requirement
        value_to_cost_ratio = stabilized_value / self.total_project_cost
        if value_to_cost_ratio < 1.0:
            raise ValueError(
                f"❌ DEAL INFEASIBLE: Office project destroys value! "
                f"Stabilized value ${stabilized_value:,.0f} < Project cost ${self.total_project_cost:,.0f} "
                f"(ratio: {value_to_cost_ratio:.2f}). Increase rent PSF, reduce costs, or lower cap rate."
            )

        # Check 2: Cash-out feasibility
        cash_out_potential = perm_loan_amount - construction_loan_amount
        if cash_out_potential < 0:
            raise ValueError(
                f"❌ REFINANCING INFEASIBLE: Permanent loan ${perm_loan_amount:,.0f} < "
                f"Construction loan ${construction_loan_amount:,.0f}. "
                f"Cash shortfall: ${abs(cash_out_potential):,.0f}. "
                f"Increase permanent LTV, increase rent PSF, or reduce construction debt."
            )

        # Check 3: DSCR validation
        estimated_debt_service = (perm_loan_amount * self.permanent_interest_rate) / 12
        if estimated_debt_service > 0 and stabilized_noi > 0:
            estimated_annual_debt_service = estimated_debt_service * 12
            estimated_dscr = stabilized_noi / estimated_annual_debt_service
            required_dscr = 1.25

            if estimated_dscr < required_dscr:
                raise ValueError(
                    f"❌ DSCR VIOLATION: Estimated DSCR {estimated_dscr:.2f}x below "
                    f"required {required_dscr:.2f}x. Current capital structure cannot support "
                    f"permanent financing. Reduce permanent LTV or increase rent PSF."
                )

        # Calculate construction period for refinance timing
        construction_period_months = (
            self.construction_start_months + self.construction_duration_months
        )

        financing_plan = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Construction Facility",
                "debt_ratio": self.construction_ltc_ratio,  # Use debt_ratio like residential pattern
                "ltc_max": 0.80,  # Standard construction LTC cap
                "interest_rate": self.construction_interest_rate,
                "loan_term_months": 24,  # 2 years construction
                "interest_reserve_rate": self.interest_reserve_rate,
            },
            permanent_terms={
                "name": "Permanent Facility",
                "loan_amount": perm_loan_amount,
                "interest_rate": self.permanent_interest_rate,
                "loan_term_months": self.permanent_loan_term_years * 12,
                "amortization_months": self.permanent_amortization_years * 12,
                "ltv_ratio": self.permanent_ltv_ratio,
                "dscr_hurdle": 1.25,
                "origination_fee_rate": 0.005,
                "refinance_timing": construction_period_months,  # THIS IS THE KEY!
            },
            project_value=self.total_project_cost,
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
        exit_valuation = DirectCapValuation(
            name="Stabilized Disposition",
            cap_rate=self.exit_cap_rate,
            transaction_costs_rate=self.exit_costs_rate,
            hold_period_months=self.hold_period_years * 12,
            noi_basis_kind="LTM",  # Use trailing 12 months for realistic exit
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
