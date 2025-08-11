# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Patterns for ground-up real estate development projects.

These functions assemble complete development Deals from land acquisition
through construction, lease-up, and stabilization.

Patterns implemented:
- create_development_deal(...) -> Deal (ground-up development projects)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List

from ..asset.residential import (
    ResidentialAbsorptionPlan,
    ResidentialCollectionLoss,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialVacantUnit,
)
from ..asset.residential.absorption import ResidentialDirectLeaseTerms
from ..asset.residential.blueprint import ResidentialDevelopmentBlueprint
from ..core.base.absorption import FixedQuantityPace
from ..core.capital import CapitalItem, CapitalPlan
from ..core.primitives import StartDateAnchorEnum, Timeline, UponExpirationEnum
from ..core.primitives.enums import AssetTypeEnum
from ..deal import AcquisitionTerms, Deal, create_gp_lp_waterfall
from ..debt import create_construction_to_permanent_plan
from ..development import DevelopmentProject
from ..valuation import ReversionValuation


def create_development_deal(
    project_name: str,
    acquisition_date: date,
    land_acquisition_terms: Dict[str, Any],
    construction_plan_spec: Dict[str, List[Dict]],
    blueprints_spec: List[Dict[str, Any]],
    financing_plan_spec: Dict[str, Dict],
    partnership_terms: Dict[str, Any],
    exit_valuation_spec: Dict[str, Any],
) -> Deal:
    """
    Models a complete ground-up development project from land acquisition to stabilization and exit.

    This is the "big project" pattern, modeling a ground-up development that tells a story
    of transformation, risk, and high potential reward.

    Args:
        project_name: The name of the development project
        acquisition_date: The date the land is acquired
        land_acquisition_terms: Parameters for land purchase:
            {"value": float, "closing_costs_rate": float}
        construction_plan_spec: Construction budget definition:
            {"capital_items": [{"name": str, "value": float, "timeline": {...}}, ...]}
        blueprints_spec: Asset Factory components - list of building components:
            [{"use_type": str, "vacant_inventory": [...], "absorption_plan": {...}}, ...]
        financing_plan_spec: Two-facility financing structure:
            {"construction_terms": {...}, "permanent_terms": {...}}
        partnership_terms: Equity waterfall structure:
            {"distribution_method": str, "gp_share": float, "lp_share": float,
             "pref_return": float, "promote_tiers": [(hurdle, rate), ...]}
        exit_valuation_spec: Sale parameters:
            {"cap_rate": float, "transaction_costs_rate": float, "hold_period_months": int}

    Returns:
        Complete Deal object ready for analysis

    Example:
        deal = create_development_deal(
            project_name="Urban Mixed-Use Development",
            acquisition_date=date(2024, 1, 1),
            land_acquisition_terms={
                "value": 5_000_000,
                "closing_costs_rate": 0.03
            },
            construction_plan_spec={
                "capital_items": [
                    {
                        "name": "Hard Costs",
                        "value": 20_000_000,
                        "timeline": {
                            "start_date": "2024-06-01",
                            "end_date": "2026-12-31"
                        }
                    },
                    {
                        "name": "Soft Costs",
                        "value": 3_000_000,
                        "timeline": {
                            "start_date": "2024-01-01",
                            "end_date": "2027-06-30"
                        }
                    }
                ]
            },
            blueprints_spec=[
                {
                    "use_type": "residential",
                    "vacant_inventory": [
                        {"unit_type": "1BR", "count": 50, "avg_sf": 650},
                        {"unit_type": "2BR", "count": 30, "avg_sf": 900}
                    ],
                    "absorption_plan": {
                        "pace": {"quantity": 4, "frequency_months": 1},
                        "rent": 2000,
                        "lease_terms": 12
                    }
                }
            ],
            financing_plan_spec={
                "construction_terms": {
                    "name": "Construction Loan",
                    "tranches": [{"name": "Construction", "ltc_threshold": 0.75,
                                 "interest_rate": 0.08, "fee_rate": 0.02}]
                },
                "permanent_terms": {
                    "name": "Permanent Loan",
                    "ltv_ratio": 0.70,
                    "interest_rate": 0.065,
                    "loan_term_years": 10
                }
            },
            partnership_terms={
                "distribution_method": "waterfall",
                "gp_share": 0.20,
                "lp_share": 0.80,
                "pref_return": 0.08,
                "promote_tiers": [(0.15, 0.25)]
            },
            exit_valuation_spec={
                "cap_rate": 0.055,
                "transaction_costs_rate": 0.015,
                "hold_period_months": 120
            }
        )

        results = analyze(deal, timeline)
        print(f"Development IRR: {results.deal_metrics.irr:.2%}")
    """
    # Step 1: Build the ConstructionPlan (CapitalPlan)
    capital_items = []
    for item_spec in construction_plan_spec["capital_items"]:
        # Create Timeline from timing parameters
        timeline = Timeline.from_dates(
            start_date=item_spec["timeline"]["start_date"],
            end_date=item_spec["timeline"]["end_date"],
        )

        # Create CapitalItem
        capital_item = CapitalItem(
            name=item_spec["name"],
            work_type="construction",  # Default work type for development
            value=item_spec["value"],
            timeline=timeline,
        )
        capital_items.append(capital_item)

    construction_plan = CapitalPlan(
        name=f"{project_name} Construction Plan", capital_items=capital_items
    )

    # Step 2: Build the blueprints List
    blueprints = []
    for blueprint_spec in blueprints_spec:
        use_type = blueprint_spec["use_type"]

        if use_type == "office":
            # Office blueprint implementation - placeholder for now
            raise NotImplementedError(
                "Office development blueprints will be implemented in future release"
            )

        elif use_type == "residential":
            # Get absorption plan specification first
            absorption_spec = blueprint_spec["absorption_plan"]

            # Create basic rollover profile for new development units
            default_rollover = ResidentialRolloverProfile(
                name="New Development Leasing",
                term_months=12,
                renewal_probability=0.75,  # 75% renewal rate
                downtime_months=1,  # 1 month turnover
                upon_expiration=UponExpirationEnum.MARKET,
                market_terms=ResidentialRolloverLeaseTerms(
                    market_rent=absorption_spec["rent"],  # Use absorption plan rent
                    term_months=12,
                ),
                renewal_terms=ResidentialRolloverLeaseTerms(
                    market_rent=absorption_spec["rent"] * 0.98,  # 2% renewal discount
                    term_months=12,
                ),
            )

            # Create vacant inventory
            vacant_units = []
            for inventory_item in blueprint_spec["vacant_inventory"]:
                vacant_unit = ResidentialVacantUnit(
                    unit_type_name=inventory_item["unit_type"],
                    unit_count=inventory_item["count"],
                    avg_area_sf=inventory_item["avg_sf"],
                    market_rent=absorption_spec[
                        "rent"
                    ],  # Use rent from absorption plan
                    rollover_profile=default_rollover,
                )
                vacant_units.append(vacant_unit)

            # Create absorption plan

            # Create default expenses and losses for new development
            stabilized_expenses = ResidentialExpenses(operating_expenses=[])
            stabilized_losses = ResidentialLosses(
                general_vacancy=ResidentialGeneralVacancyLoss(
                    name="General Vacancy",
                    rate=0.05,  # 5% vacancy for new development
                ),
                collection_loss=ResidentialCollectionLoss(
                    name="Collection Loss",
                    rate=0.01,  # 1% collection loss for new development
                ),
            )

            absorption_plan = ResidentialAbsorptionPlan(
                name=f"{project_name} Residential Leasing",
                start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
                pace=FixedQuantityPace(
                    quantity=absorption_spec["pace"]["quantity"],
                    unit="Units",
                    frequency_months=absorption_spec["pace"]["frequency_months"],
                ),
                leasing_assumptions=ResidentialDirectLeaseTerms(
                    monthly_rent=absorption_spec["rent"],
                    lease_term_months=absorption_spec["lease_terms"],
                    stabilized_renewal_probability=0.75,  # Default
                    stabilized_downtime_months=1,  # Default
                ),
                stabilized_expenses=stabilized_expenses,
                stabilized_losses=stabilized_losses,
                stabilized_misc_income=[],  # No misc income by default
            )

            blueprint = ResidentialDevelopmentBlueprint(
                name=f"{project_name} Residential Component",
                vacant_inventory=vacant_units,
                absorption_plan=absorption_plan,
            )
            blueprints.append(blueprint)

        else:
            raise ValueError(f"Unsupported use_type: {use_type}")

    # Step 3: Assemble the DevelopmentProject Asset
    # Calculate total area from blueprints
    total_area = 0.0
    for blueprint in blueprints:
        if hasattr(blueprint, "vacant_inventory"):
            for vacant_unit in blueprint.vacant_inventory:
                total_area += vacant_unit.total_area

    # Default to reasonable areas if no units are found
    if total_area == 0:
        total_area = 100000.0  # Default 100k SF

    # Determine property type based on blueprints
    property_type = (
        AssetTypeEnum.MULTIFAMILY
    )  # Default for residential-only development
    if len(blueprints) > 1:
        property_type = AssetTypeEnum.MIXED_USE  # Mixed-use if multiple blueprints

    development_asset = DevelopmentProject(
        name=project_name,
        property_type=property_type,
        gross_area=total_area,
        net_rentable_area=total_area * 0.95,  # Assume 95% rentable efficiency
        construction_plan=construction_plan,
        blueprints=blueprints,
    )

    # Step 4: Build the FinancingPlan
    financing_plan = create_construction_to_permanent_plan(
        construction_terms=financing_plan_spec["construction_terms"],
        permanent_terms=financing_plan_spec["permanent_terms"],
    )

    # Step 5: Build the PartnershipStructure
    partnership = create_gp_lp_waterfall(
        gp_share=partnership_terms.get("gp_share", 0.20),  # Default 20% GP
        lp_share=partnership_terms.get("lp_share", 0.80),  # Default 80% LP
        pref_return=partnership_terms["pref_return"],
        promote_tiers=partnership_terms.get(
            "promote_tiers", [(0.15, 0.30)]
        ),  # Default tier
        final_promote_rate=partnership_terms.get(
            "final_promote_rate", 0.30
        ),  # Default final promote
    )

    # Step 6: Build AcquisitionTerms and ReversionValuation
    land_value = land_acquisition_terms["value"]
    closing_costs_rate = land_acquisition_terms["closing_costs_rate"]

    # Land acquisition typically happens over 30-60 days
    acquisition_end_date = (
        datetime.combine(acquisition_date, datetime.min.time())
        .replace(
            month=acquisition_date.month + 2 if acquisition_date.month <= 10 else 1,
            year=acquisition_date.year
            if acquisition_date.month <= 10
            else acquisition_date.year + 1,
        )
        .date()
    )

    acquisition_timeline = Timeline.from_dates(
        start_date=acquisition_date.strftime("%Y-%m-%d"),
        end_date=acquisition_end_date.strftime("%Y-%m-%d"),
    )

    acquisition = AcquisitionTerms(
        name=f"{project_name} Land Acquisition",
        timeline=acquisition_timeline,
        value=land_value,
        acquisition_date=acquisition_date,
        closing_costs=land_value * closing_costs_rate,
    )

    reversion = ReversionValuation(
        name=f"{project_name} Sale",
        cap_rate=exit_valuation_spec["cap_rate"],
        transaction_costs_rate=exit_valuation_spec["transaction_costs_rate"],
        hold_period_months=exit_valuation_spec["hold_period_months"],
    )

    # Step 7: Assemble and Return the Final Deal
    deal = Deal(
        name=project_name,
        asset=development_asset,
        acquisition=acquisition,
        financing=financing_plan,
        equity_partners=partnership,
        exit_valuation=reversion,
    )

    return deal
