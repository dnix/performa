# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Residential value-add acquisition deal pattern implementation.

This pattern models the common investment strategy of acquiring an underperforming
property, executing renovations to increase NOI, and exiting via sale.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from uuid import uuid4

from pydantic import Field, field_validator

from ..asset.residential import (
    ResidentialAbsorptionPlan,
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
)
from ..asset.residential.absorption import ResidentialDirectLeaseTerms
from ..core.base.absorption import FixedQuantityPace
from ..core.capital import CapitalItem, CapitalPlan
from ..core.primitives import (
    FrequencyEnum,
    PercentageGrowthRate,
    PropertyAttributeKey,
    StartDateAnchorEnum,
    Timeline,
    UnleveredAggregateLineKey,
    UponExpirationEnum,
)
from ..core.primitives.types import FloatBetween0And1, PositiveFloat, PositiveInt
from ..deal import (
    AcquisitionTerms,
    Deal,
    create_gp_lp_waterfall,
    create_simple_partnership,
)
from ..debt import create_construction_to_permanent_plan
from ..valuation import DirectCapValuation
from .base import PatternBase


class ValueAddAcquisitionPattern(PatternBase):
    """
    Value-add acquisition deal pattern with integrated analysis.

    This pattern models a common investment strategy:
    - Acquire an underperforming property at below-market pricing
    - Execute renovations to increase rents and NOI
    - Hold for cash flow and appreciation
    - Exit via sale at a lower cap rate

    The pattern uses sensible defaults for many parameters while allowing
    full customization when needed.
    """

    # === Property Identification ===
    property_name: str = Field(description="Name of the property")
    property_type: Literal["multifamily"] = Field(
        default="multifamily",
        description="Type of property (multifamily supported)",
    )

    # === Acquisition Parameters ===
    acquisition_date: date = Field(description="Date of acquisition")
    acquisition_price: PositiveFloat = Field(gt=0, description="Purchase price")
    closing_costs_rate: FloatBetween0And1 = Field(
        default=0.025,
        ge=0,
        le=0.1,
        description="Closing costs as percentage of purchase price",
    )

    # === Value-Add Strategy ===
    renovation_budget: PositiveFloat = Field(
        gt=0,
        description="Total renovation investment (e.g., $15,000/unit for light value-add)",
    )
    renovation_start_year: PositiveInt = Field(
        default=1,
        ge=1,
        le=10,
        description="Year to begin renovations (1 = first year after acquisition)",
    )
    renovation_duration_years: PositiveInt = Field(
        default=2, ge=1, le=5, description="Years to complete renovations"
    )

    # === Property Specifications ===
    total_units: PositiveInt = Field(
        default=100, ge=1, le=1000, description="Total number of units in the property"
    )
    avg_unit_sf: PositiveFloat = Field(
        default=800, gt=0, description="Average square footage per unit"
    )
    current_avg_rent: PositiveFloat = Field(
        gt=0, description="Current average monthly rent per unit"
    )
    target_avg_rent: PositiveFloat = Field(
        gt=0, description="Target average monthly rent after renovation"
    )

    # === Operating Assumptions ===
    initial_vacancy_rate: FloatBetween0And1 = Field(
        default=0.08, ge=0, le=0.5, description="Initial vacancy rate"
    )
    stabilized_vacancy_rate: FloatBetween0And1 = Field(
        default=0.05, ge=0, le=0.3, description="Vacancy rate after stabilization"
    )
    credit_loss_rate: FloatBetween0And1 = Field(
        default=0.015, ge=0, le=0.1, description="Collection loss rate"
    )
    operating_expense_ratio: FloatBetween0And1 = Field(
        default=0.45,
        ge=0.2,
        le=0.7,
        description="Operating expenses as percentage of effective gross income",
    )

    # === Hold Strategy ===
    hold_period_years: PositiveInt = Field(
        default=5, ge=1, le=30, description="Investment hold period in years"
    )

    # === Financing Parameters ===
    ltv_ratio: FloatBetween0And1 = Field(
        default=0.65,
        ge=0,
        le=0.70,  # Realistic for value-add deals
        description="Loan-to-value ratio (realistic for value-add)",
    )
    renovation_loan_rate: PositiveFloat = Field(
        default=0.08, gt=0, le=0.15, description="Renovation loan interest rate"
    )
    permanent_rate: PositiveFloat = Field(
        default=0.06, gt=0, le=0.15, description="Permanent loan interest rate"
    )
    loan_term_years: PositiveInt = Field(
        default=10, ge=1, le=30, description="Permanent loan term"
    )
    amortization_years: PositiveInt = Field(
        default=30, ge=1, le=40, description="Amortization period in years"
    )

    # === Partnership Structure ===
    distribution_method: Literal["pari_passu", "waterfall"] = Field(
        default="waterfall", description="Distribution methodology"
    )
    gp_share: FloatBetween0And1 = Field(
        default=0.20, ge=0, le=1, description="General partner ownership share"
    )
    lp_share: FloatBetween0And1 = Field(
        default=0.80, ge=0, le=1, description="Limited partner ownership share"
    )
    pref_return: Optional[PositiveFloat] = Field(
        default=0.08,
        gt=0,
        le=0.20,
        description="Preferred return (required for waterfall)",
    )
    promote_tiers: Optional[list[tuple[float, float]]] = Field(
        default=[(0.15, 0.30)],
        description="Promote tiers: [(irr_hurdle, promote_rate), ...]",
    )

    # === Exit Strategy ===
    exit_cap_rate: PositiveFloat = Field(
        default=0.055, gt=0, le=0.15, description="Exit capitalization rate"
    )
    exit_costs_rate: FloatBetween0And1 = Field(
        default=0.015, ge=0, le=0.1, description="Exit transaction costs as percentage"
    )

    @field_validator("lp_share")
    def validate_partnership_shares(cls, v, info):
        """Ensure GP and LP shares sum to 1.0"""
        if "gp_share" in info.data:
            total = v + info.data["gp_share"]
            if abs(total - 1.0) > 0.001:
                raise ValueError(
                    f"GP share ({info.data['gp_share']}) and LP share ({v}) must sum to 1.0, got {total}"
                )
        return v

    @field_validator("pref_return")
    def validate_waterfall_requirements(cls, v, info):
        """Ensure pref_return is provided when using waterfall distribution"""
        if info.data.get("distribution_method") == "waterfall" and v is None:
            raise ValueError(
                "pref_return is required when distribution_method is 'waterfall'"
            )
        return v

    def _derive_timeline(self) -> Timeline:
        """
        Derive timeline from hold_period_years (stabilized hold after renovation).

        Value-Add Timeline: Acquisition → Renovation → Stabilized Hold Period
        - Total timeline = renovation_duration_months + hold_period_years * 12
        """
        start_date = self.acquisition_date

        # Value-add timeline = renovation period + stabilized hold period
        # Adding 12 months for typical renovation/lease-up period
        total_duration_months = self.hold_period_years * 12 + 12

        return Timeline(start_date=start_date, duration_months=total_duration_months)

    def create(self) -> Deal:
        """
        Create a complete Deal object from the pattern parameters.

        This method assembles all components needed for a value-add acquisition:
        - ResidentialProperty with current and post-renovation specifications
        - CapitalPlan for renovation investments
        - Construction-to-permanent financing structure
        - GP/LP partnership with waterfall distribution
        - AcquisitionTerms and exit valuation

        Returns:
            Complete Deal object ready for analysis via analyze()
        """

        # === Step 1: Create Acquisition Terms ===
        acquisition_end_date = (
            datetime.combine(self.acquisition_date, datetime.min.time())
            .replace(
                month=self.acquisition_date.month + 2
                if self.acquisition_date.month <= 10
                else 1,
                year=self.acquisition_date.year
                if self.acquisition_date.month <= 10
                else self.acquisition_date.year + 1,
            )
            .date()
        )

        acquisition_timeline = Timeline.from_dates(
            start_date=self.acquisition_date.strftime("%Y-%m-%d"),
            end_date=acquisition_end_date.strftime("%Y-%m-%d"),
        )

        acquisition = AcquisitionTerms(
            name=f"{self.property_name} Acquisition",
            timeline=acquisition_timeline,
            value=self.acquisition_price,
            acquisition_date=self.acquisition_date,
            closing_costs_rate=self.closing_costs_rate,
        )

        # === Step 2: Create Renovation Capital Plan ===
        renovation_start = self.acquisition_date.replace(
            year=self.acquisition_date.year + self.renovation_start_year
        )
        renovation_end = renovation_start.replace(
            year=renovation_start.year + self.renovation_duration_years
        )

        renovation_plan = CapitalPlan(
            name="Unit Renovation Program",
            capital_items=[
                CapitalItem(
                    name="Unit Renovations",
                    work_type="renovation",
                    value=self.renovation_budget,
                    timeline=Timeline.from_dates(
                        start_date=renovation_start.strftime("%Y-%m-%d"),
                        end_date=renovation_end.strftime("%Y-%m-%d"),
                    ),
                )
            ],
        )

        # === Step 3: Create Expenses (realistic operating expenses) ===
        timeline = self.get_timeline()

        expenses = ResidentialExpenses(
            operating_expenses=[
                ResidentialOpExItem(
                    name="Property Management",
                    timeline=timeline,
                    value=0.05,  # 5% of effective gross income
                    frequency=FrequencyEnum.MONTHLY,
                    reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
                ),
                ResidentialOpExItem(
                    name="Maintenance & Repairs",
                    timeline=timeline,
                    value=600.0,  # $600 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Maintenance Inflation", value=0.03
                    ),
                ),
                ResidentialOpExItem(
                    name="Insurance",
                    timeline=timeline,
                    value=400.0,  # $400 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Insurance Inflation", value=0.04
                    ),
                ),
                ResidentialOpExItem(
                    name="Property Taxes",
                    timeline=timeline,
                    value=self.acquisition_price * 0.012,  # 1.2% of acquisition price
                    frequency=FrequencyEnum.ANNUAL,
                    growth_rate=PercentageGrowthRate(name="Tax Growth", value=0.025),
                ),
                ResidentialOpExItem(
                    name="Utilities (Common Area)",
                    timeline=timeline,
                    value=200.0,  # $200 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Utility Inflation", value=0.04
                    ),
                ),
                ResidentialOpExItem(
                    name="Marketing & Leasing",
                    timeline=timeline,
                    value=150.0,  # $150 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                ),
                ResidentialOpExItem(
                    name="Admin & Professional",
                    timeline=timeline,
                    value=100.0,  # $100 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                ),
            ]
        )

        # === Step 4: Create Post-Renovation Absorption Plan ===
        post_renovation_plan_id = uuid4()
        post_renovation_absorption = ResidentialAbsorptionPlan(
            uid=post_renovation_plan_id,
            name="Post-Renovation Premium Leasing",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=2, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=self.target_avg_rent,
                lease_term_months=12,
                stabilized_renewal_probability=0.8,
                stabilized_downtime_months=1,
            ),
            stabilized_expenses=expenses,  # Use same expense structure
            stabilized_losses=ResidentialLosses(
                general_vacancy=ResidentialGeneralVacancyLoss(
                    rate=self.stabilized_vacancy_rate,
                ),
                credit_loss=ResidentialCreditLoss(
                    rate=self.credit_loss_rate,
                ),
            ),
            stabilized_misc_income=[],
        )

        # === Step 5: Create Value-Add Rollover Profile ===
        rollover_profile = ResidentialRolloverProfile(
            name="Value-Add Lease Expiration",
            term_months=12,
            renewal_probability=0.30,  # Low renewal to encourage turnover
            downtime_months=2,  # Time for renovation
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=post_renovation_plan_id,
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=self.current_avg_rent,
                term_months=12,
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=self.current_avg_rent * 0.95,
                term_months=12,
            ),
        )

        # === Step 6: Create Unit Mix ===
        # Split units into 1BR and 2BR for variety
        br1_count = self.total_units // 2
        br2_count = self.total_units - br1_count

        unit_spec_1br = ResidentialUnitSpec(
            unit_type_name="1BR - Current",
            unit_count=br1_count,
            avg_area_sf=self.avg_unit_sf * 0.8,  # 1BR is 80% of average
            current_avg_monthly_rent=self.current_avg_rent
            * 0.9,  # 1BR is 90% of average rent
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 4, 1),  # Default lease start
        )

        unit_spec_2br = ResidentialUnitSpec(
            unit_type_name="2BR - Current",
            unit_count=br2_count,
            avg_area_sf=self.avg_unit_sf * 1.2,  # 2BR is 120% of average
            current_avg_monthly_rent=self.current_avg_rent
            * 1.1,  # 2BR is 110% of average rent
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 4, 1),
        )

        rent_roll = ResidentialRentRoll(unit_specs=[unit_spec_1br, unit_spec_2br])

        # === Step 7: Create Losses ===
        losses = ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(
                rate=self.initial_vacancy_rate,
            ),
            credit_loss=ResidentialCreditLoss(
                rate=self.credit_loss_rate,
            ),
        )

        # === Step 8: Create Property Asset ===
        property_asset = ResidentialProperty(
            name=self.property_name,
            property_type=self.property_type,
            gross_area=self.total_units * self.avg_unit_sf,
            net_rentable_area=self.total_units * self.avg_unit_sf,
            unit_mix=rent_roll,
            capital_plans=[renovation_plan],
            absorption_plans=[post_renovation_absorption],
            expenses=expenses,
            losses=losses,
            miscellaneous_income=[],
        )

        # === Step 9: Create Financing Plan ===
        # Calculate loan amount based on total project cost (acquisition + renovations)
        # For value-add deals, LTV applies to total project cost since construction loan
        # must fund both the acquisition and the renovations
        total_project_cost = self.acquisition_price + self.renovation_budget
        loan_amount = total_project_cost * self.ltv_ratio

        # Calculate when renovation loan should mature (at refinancing)
        renovation_loan_term_months = (
            self.renovation_start_year + self.renovation_duration_years
        ) * 12

        financing_plan = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Renovation Loan",
                "loan_amount": loan_amount,  # Explicit loan amount for renovation facility
                # CRITICAL FIX: Set loan term to match refinancing timing
                # This ensures renovation loan stops charging interest when permanent loan takes over
                "loan_term_months": renovation_loan_term_months,
                "tranches": [
                    {
                        "name": "Renovation Financing",
                        "interest_rate": {
                            "details": {
                                "rate_type": "fixed",
                                "rate": self.renovation_loan_rate,
                            }
                        },
                        "fee_rate": 0.015,
                        "ltc_threshold": self.ltv_ratio,
                    }
                ],
                "fund_interest_from_reserve": True,
                "interest_reserve_rate": 0.10,
            },
            permanent_terms={
                "name": "Permanent Financing",
                "interest_rate": {
                    "details": {"rate_type": "fixed", "rate": self.permanent_rate}
                },
                "loan_term_years": self.loan_term_years,
                "amortization_years": self.amortization_years,
                "loan_amount": loan_amount,  # Explicit loan amount to fix debt service calculation
                "ltv_ratio": self.ltv_ratio,
                "dscr_hurdle": 1.25,
                # CRITICAL FIX: Set refinance timing to after renovation completion
                # This prevents double-funding by ensuring permanent loan refinances renovation loan
                # rather than both funding on day 1
                "refinance_timing": (
                    self.renovation_start_year + self.renovation_duration_years
                )
                * 12,
            },
        )

        # === Step 10: Create Partnership Structure ===
        if self.distribution_method == "waterfall":
            partnership = create_gp_lp_waterfall(
                gp_share=self.gp_share,
                lp_share=self.lp_share,
                pref_return=self.pref_return,
                promote_tiers=self.promote_tiers or [(0.15, 0.30)],
                final_promote_rate=self.promote_tiers[-1][1]
                if self.promote_tiers
                else 0.30,
            )
        else:
            partnership = create_simple_partnership(
                gp_name=f"{self.property_name} GP",
                lp_name=f"{self.property_name} LP",
                gp_share=self.gp_share,
                lp_share=self.lp_share,
            )

        # === Step 11: Create Exit Valuation ===
        reversion = DirectCapValuation(
            name=f"{self.property_name} Sale",
            cap_rate=self.exit_cap_rate,
            transaction_costs_rate=self.exit_costs_rate,
            hold_period_months=self.hold_period_years * 12,
            noi_basis_kind="LTM",  # Use trailing 12 months for realistic exit
        )

        # === Step 12: Assemble and Return Deal ===
        return Deal(
            name=f"{self.property_name} Value-Add Acquisition",
            asset=property_asset,
            acquisition=acquisition,
            financing=financing_plan,
            equity_partners=partnership,
            exit_valuation=reversion,
        )
