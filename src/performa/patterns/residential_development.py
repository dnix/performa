# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Residential development deal pattern implementation.

This pattern models ground-up residential development projects using unit-based
metrics and residential-specific leasing assumptions.
"""

from __future__ import annotations

from typing import List

from pydantic import Field, field_validator, model_validator

from ..asset.residential import (
    ResidentialAbsorptionPlan,
    ResidentialCreditLoss,
    ResidentialDevelopmentBlueprint,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialVacantUnit,
)
from ..asset.residential.absorption import (
    FixedQuantityPace,
    ResidentialDirectLeaseTerms,
)
from ..core.capital import CapitalItem, CapitalPlan
from ..core.primitives import (
    AssetTypeEnum,
    FloatBetween0And1,
    InterestCalculationMethod,
    PositiveFloat,
    PositiveInt,
    SCurveDrawSchedule,
    StartDateAnchorEnum,
    Timeline,
    UniformDrawSchedule,
    UponExpirationEnum,
)
from ..deal import (
    AcquisitionTerms,
    Deal,
    create_gp_lp_waterfall,
    create_simple_partnership,
)

# No direct debt facility imports needed - using construct
from ..debt.constructs import create_construction_to_permanent_plan
from ..development import DevelopmentProject
from ..valuation import DirectCapValuation
from .base import DevelopmentPatternBase


class ResidentialDevelopmentPattern(DevelopmentPatternBase):
    """
    Residential development deal pattern with unit-based metrics.

    This pattern models ground-up residential development projects from land acquisition
    through construction, lease-up, and stabilization using natural residential industry
    parameters based on unit counts and rent levels.

    Key Residential-Specific Features:
    - Unit count-based building specifications
    - Residential leasing metrics ($/month rent, unit mix)
    - Unit-by-unit vacant inventory modeling
    - Residential absorption strategies (units per month)
    - Residential construction costs ($/unit or $/SF)

    Example:
        ```python
        pattern = ResidentialDevelopmentPattern(
            project_name="Garden Apartments",
            acquisition_date=date(2024, 1, 1),
            land_cost=3_000_000,
            total_units=120,
            unit_mix=[
                {"unit_type": "1BR", "count": 60, "avg_sf": 650, "target_rent": 1800},
                {"unit_type": "2BR", "count": 60, "avg_sf": 950, "target_rent": 2400}
            ],
            construction_cost_per_unit=180_000
        )
        deal = pattern.create()
        results = pattern.analyze()
        ```
    """

    # === BUILDING SPECIFICATIONS ===
    total_units: PositiveInt = Field(
        ..., description="Total number of residential units"
    )
    unit_mix: List[dict] = Field(
        ...,
        description="List of unit types with counts, SF, and rents. Each dict should have: unit_type, count, avg_sf, target_rent",
    )
    avg_unit_sf: PositiveFloat = Field(
        default=None,
        description="Average unit size in square feet (calculated from unit_mix if not provided)",
    )
    building_efficiency: FloatBetween0And1 = Field(
        default=0.85,
        description="Ratio of net rentable area to gross building area",
    )

    # === LEASING ASSUMPTIONS ===
    lease_term_months: PositiveInt = Field(
        default=12,  # 1 year standard
        ge=6,
        le=24,
        description="Standard lease term in months",
    )
    renewal_probability: FloatBetween0And1 = Field(
        default=0.75,
        description="Expected renewal probability for stabilized property",
    )
    downtime_months: PositiveInt = Field(
        default=1,
        ge=0,
        le=6,
        description="Months of downtime during unit turnover",
    )

    # === ABSORPTION STRATEGY ===
    leasing_start_months: PositiveInt = Field(
        default=15,
        ge=3,
        le=36,
        description="Months after land acquisition to start leasing",
    )
    absorption_pace_units_per_month: PositiveInt = Field(
        default=8,  # Increased from 4 for reasonable lease-up timeline
        ge=1,
        le=20,
        description="Number of units to lease per month during lease-up",
    )
    absorption_frequency_months: PositiveInt = Field(
        default=1,
        ge=1,
        le=3,
        description="Frequency of lease executions (typically monthly for residential)",
    )

    # === CONSTRUCTION COST MODEL ===
    construction_cost_per_unit: PositiveFloat = Field(
        default=None,
        description="Construction cost per unit (alternative to per-SF pricing)",
    )
    construction_cost_psf: PositiveFloat = Field(
        default=200.0, description="Construction cost per square foot of gross area"
    )
    soft_costs_rate: FloatBetween0And1 = Field(
        default=0.15, description="Soft costs as percentage of hard construction costs"
    )
    developer_fee_rate: FloatBetween0And1 = Field(
        default=0.05,
        description="Developer fee as percentage of total construction cost",
    )

    # === OPERATING ASSUMPTIONS ===
    stabilized_vacancy_rate: FloatBetween0And1 = Field(
        default=0.05, description="Expected vacancy rate for stabilized property"
    )
    credit_loss_rate: FloatBetween0And1 = Field(
        default=0.01, description="Expected credit loss rate for collections"
    )

    # === CONSTRUCTION CAPITAL STRUCTURE ===
    construction_ltc_max: FloatBetween0And1 = Field(
        default=0.80,
        description="Maximum LTC threshold - lender's hard gate (typically 0.75-0.85)",
    )

    # Removed duplicate _derive_timeline() method - using the one below with proper development logic

    @field_validator("unit_mix")
    @classmethod
    def validate_unit_mix(cls, v):
        """Validate unit mix has required fields."""
        for unit_type in v:
            required_fields = ["unit_type", "count", "avg_sf", "target_rent"]
            for field in required_fields:
                if field not in unit_type:
                    raise ValueError(f"unit_mix items must include '{field}' field")
        return v

    @model_validator(mode="after")
    def validate_total_units_match(self) -> "ResidentialDevelopmentPattern":
        """Ensure total_units matches sum of unit_mix counts."""
        unit_mix_total = sum(unit["count"] for unit in self.unit_mix)
        if self.total_units != unit_mix_total:
            raise ValueError(
                f"total_units ({self.total_units}) must equal sum of unit_mix counts ({unit_mix_total})"
            )
        return self

    @property
    def avg_unit_sf_computed(self) -> float:
        """Calculate average unit SF from unit mix if not provided."""
        if self.avg_unit_sf is not None:
            return self.avg_unit_sf

        total_sf = sum(unit["count"] * unit["avg_sf"] for unit in self.unit_mix)
        return total_sf / self.total_units

    @property
    def total_rentable_area(self) -> float:
        """Calculate total rentable area from unit mix."""
        return sum(unit["count"] * unit["avg_sf"] for unit in self.unit_mix)

    @property
    def gross_building_area(self) -> float:
        """Calculate gross building area using efficiency factor."""
        return self.total_rentable_area / self.building_efficiency

    @property
    def total_construction_cost(self) -> float:
        """Calculate total construction cost using preferred method."""
        if self.construction_cost_per_unit is not None:
            hard_costs = self.construction_cost_per_unit * self.total_units
        else:
            hard_costs = self.construction_cost_psf * self.gross_building_area

        soft_costs = hard_costs * self.soft_costs_rate
        return hard_costs + soft_costs

    @property
    def developer_fee(self) -> float:
        """Calculate developer fee based on total construction cost."""
        return self.total_construction_cost * self.developer_fee_rate

    @property
    def total_project_cost(self) -> float:
        """Calculate total project cost including land and developer fee (excluding closing costs for development cost comparison)."""
        return self.land_cost + self.total_construction_cost + self.developer_fee

    def _derive_timeline(self) -> Timeline:
        """
        Derive timeline from hold_period_years (stabilized hold after construction + lease-up).
        
        Residential Development Timeline: Acquisition → Construction → Lease-up → Stabilized Hold Period
        - Total timeline = construction_start_months + construction_duration_months + 18 (lease-up) + hold_period_years * 12
        """
        # Calculate total development timeline
        construction_period_months = self.construction_start_months + self.construction_duration_months
        lease_up_months = 18  # Longer residential lease-up period vs 12 for office
        stabilized_hold_months = self.hold_period_years * 12
        
        total_timeline_months = construction_period_months + lease_up_months + stabilized_hold_months
        
        return Timeline(
            start_date=self.acquisition_date,
            duration_months=total_timeline_months
        )

    def create(self) -> Deal:
        """
        Create residential development Deal object.

        Returns:
            Complete Deal object ready for analysis
        """

        # === STEP 1: CONSTRUCTION CAPITAL PLAN ===
        construction_item = CapitalItem(
            name=f"{self.project_name} Construction",
            work_type="construction",
            value=self.total_construction_cost,
            timeline=Timeline(
                start_date=self.acquisition_date,
                duration_months=18,  # Typical residential construction timeline
            ),
            draw_schedule=SCurveDrawSchedule(
                sigma=1.0
            ),  # Realistic S-curve construction draws over 18 months
        )

        developer_fee_item = CapitalItem(
            name=f"{self.project_name} Developer Fee",
            work_type="developer",
            value=self.developer_fee,
            timeline=Timeline(
                start_date=self.acquisition_date,
                duration_months=18,  # Same timeline as construction
            ),
            draw_schedule=UniformDrawSchedule(),  # Flat monthly payments (industry standard)
        )

        capital_plan = CapitalPlan(
            name=f"{self.project_name} Construction Plan",
            capital_items=[construction_item, developer_fee_item],
        )

        # === STEP 2: VACANT INVENTORY ===
        vacant_units = []
        for unit_type in self.unit_mix:
            # Create rollover profile for this unit type
            rollover_profile = ResidentialRolloverProfile(
                name=f"New Development Leasing - {unit_type['unit_type']}",
                term_months=self.lease_term_months,
                renewal_probability=self.renewal_probability,
                downtime_months=self.downtime_months,
                upon_expiration=UponExpirationEnum.MARKET,
                market_terms=ResidentialRolloverLeaseTerms(
                    market_rent=unit_type["target_rent"],
                    term_months=self.lease_term_months,
                ),
                renewal_terms=ResidentialRolloverLeaseTerms(
                    market_rent=unit_type["target_rent"] * 0.98,  # 2% renewal discount
                    term_months=self.lease_term_months,
                ),
            )

            vacant_unit = ResidentialVacantUnit(
                unit_type_name=unit_type["unit_type"],
                unit_count=unit_type["count"],
                avg_area_sf=unit_type["avg_sf"],
                market_rent=unit_type["target_rent"],
                rollover_profile=rollover_profile,
            )
            vacant_units.append(vacant_unit)

        # === STEP 3: ABSORPTION PLAN ===
        # Calculate weighted average rent for absorption plan
        total_rent_weight = sum(
            unit["count"] * unit["target_rent"] for unit in self.unit_mix
        )
        avg_rent = total_rent_weight / self.total_units

        # For now, skip operating expenses until we fix the timeline issue
        # TODO: Add proper operating expenses with timeline
        stabilized_expenses = ResidentialExpenses(operating_expenses=[])
        stabilized_losses = ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(
                rate=self.stabilized_vacancy_rate,
            ),
            credit_loss=ResidentialCreditLoss(
                rate=self.credit_loss_rate,
            ),
        )

        absorption_plan = ResidentialAbsorptionPlan(
            name=f"{self.project_name} Residential Leasing",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            start_offset_months=self.leasing_start_months,  # Start leasing after construction
            pace=FixedQuantityPace(
                quantity=self.absorption_pace_units_per_month,
                unit="Units",
                frequency_months=self.absorption_frequency_months,
            ),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=avg_rent,
                lease_term_months=self.lease_term_months,
                stabilized_renewal_probability=self.renewal_probability,
                stabilized_downtime_months=self.downtime_months,
            ),
            stabilized_expenses=stabilized_expenses,
            stabilized_losses=stabilized_losses,
            stabilized_misc_income=[],
        )

        # === STEP 4: RESIDENTIAL DEVELOPMENT BLUEPRINT ===
        residential_blueprint = ResidentialDevelopmentBlueprint(
            name=f"{self.project_name} Residential Component",
            vacant_inventory=vacant_units,
            absorption_plan=absorption_plan,
        )

        # === STEP 5: DEVELOPMENT PROJECT ===
        project = DevelopmentProject(
            name=f"{self.project_name} Development",
            property_type=AssetTypeEnum.MULTIFAMILY,
            gross_area=self.gross_building_area,
            net_rentable_area=self.total_rentable_area,
            construction_plan=capital_plan,
            blueprints=[residential_blueprint],
        )

        # === STEP 6: ACQUISITION TERMS ===
        acquisition = AcquisitionTerms(
            name=f"{self.project_name} Land Acquisition",
            timeline=Timeline(
                start_date=self.acquisition_date,
                duration_months=2,  # 60 days to close land
            ),
            value=self.land_cost,
            acquisition_date=self.acquisition_date,
            closing_costs_rate=0.03,  # 3% default closing costs
        )

        # === STEP 7: CONSTRUCTION-TO-PERMANENT FINANCING ===
        total_project_cost = self.land_cost + self.total_construction_cost

        # === STEP 7: CONSTRUCTION-TO-PERMANENT FINANCING ===
        # Auto-sizing will handle all loan calculations based on LTC/LTV constraints
        # No manual calculations needed - the architecture handles this elegantly

        # === ARCHITECTURAL IMPROVEMENT ===
        # Feasibility checks now handled by auto-sizing logic and market-driven validation
        # The sophisticated architecture ensures deals are appropriately structured

        financing = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Construction Facility",
                "ltc_ratio": self.construction_ltc_ratio,  # Use base class LTC parameter for loan sizing
                "ltc_max": self.construction_ltc_max,  # Lender's hard gate
                "interest_rate": self.construction_interest_rate,
                "loan_term_months": self.construction_duration_months,  # Use actual construction duration
                "fund_interest_from_reserve": True,  # Match composition approach
                "interest_reserve_rate": 0.10
                if self.interest_reserve_rate is None
                else self.interest_reserve_rate,  # 10% reserve
                "interest_calculation_method": getattr(
                    InterestCalculationMethod, self.interest_calculation_method
                ),
                "simple_reserve_rate": 0.10,  # Required for SIMPLE method
            },
            permanent_terms={
                "name": "Permanent Facility",
                # ARCHITECTURAL IMPROVEMENT: Use auto-sizing instead of manual calculation
                "ltv_ratio": self.permanent_ltv_ratio,  # Auto-sizing based on completed property value
                "dscr_hurdle": 1.25,  # Constraint for auto-sizing
                "sizing_method": "auto",  # Enable sophisticated auto-sizing
                "interest_rate": self.permanent_interest_rate,
                "loan_term_years": self.permanent_loan_term_years,  # Use years form for construct
                "amortization_years": self.permanent_amortization_years,  # Use years form for construct
                "origination_fee_rate": 0.005,
                # Smart refinance timing: construct will calculate from construction_duration_months + lease_up
            },
            project_value=self.total_project_cost,
            lease_up_months=18,  # DEVELOPMENT FIX: Account for 18-month residential lease-up before refinancing
        )

        # === STEP 8: ARCHITECTURAL IMPROVEMENT ===
        # DSCR validation is now handled automatically by auto-sizing logic
        # The permanent facility will size based on LTV/DSCR/Debt Yield constraints

        # === STEP 9: PARTNERSHIP STRUCTURE ===
        if self.distribution_method == "waterfall":
            partnership = create_gp_lp_waterfall(
                gp_share=self.gp_share,
                lp_share=self.lp_share,
                pref_return=self.preferred_return,
                promote_tiers=[
                    (0.15, self.promote_tier_1)
                ],  # Single tier from base class
                final_promote_rate=self.promote_tier_1,
            )
        else:
            partnership = create_simple_partnership(
                gp_name=f"{self.project_name} GP",
                lp_name=f"{self.project_name} LP",
                gp_share=self.gp_share,
                lp_share=self.lp_share,
            )

        # === STEP 9: EXIT VALUATION ===
        # Exit should happen at end of timeline, not just hold period
        # Timeline includes construction + lease-up + stabilization + hold
        # So exit should be at the end of the full timeline
        timeline_for_exit = self._derive_timeline()
        reversion = DirectCapValuation(
            name=f"{self.project_name} Sale",
            cap_rate=self.exit_cap_rate,
            transaction_costs_rate=self.exit_costs_rate,
            hold_period_months=timeline_for_exit.duration_months,  # Exit at end of full timeline
            noi_basis_kind="LTM",  # Use trailing 12 months for realistic exit
        )

        # === STEP 10: ASSEMBLE DEAL ===
        return Deal(
            name=f"{self.project_name} Development",
            asset=project,
            acquisition=acquisition,
            financing=financing,
            equity_partners=partnership,
            exit_valuation=reversion,
        )
