# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for development analysis scenario orchestrator."""

from datetime import date

from performa.analysis import run
from performa.asset.office import (
    OfficeAbsorptionPlan,
    OfficeDevelopmentBlueprint,
    OfficeVacantSuite,
)
from performa.asset.office.absorption import (
    DirectLeaseTerms,
    SpaceFilter,
)
from performa.asset.office.absorption import (
    FixedQuantityPace as OfficeFixedQuantityPace,
)
from performa.asset.residential import (
    ResidentialAbsorptionPlan,
    ResidentialDevelopmentBlueprint,
    ResidentialVacantUnit,
)
from performa.asset.residential.absorption import (
    ResidentialDirectLeaseTerms,
    ResidentialUnitFilter,
)
from performa.asset.residential.rollover import (
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
)
from performa.core.base import FixedQuantityPace as ResidentialFixedQuantityPace
from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.primitives import (
    AssetTypeEnum,
    GlobalSettings,
    PropertyAttributeKey,
    Timeline,
)
from performa.debt import (
    ConstructionFacility,
    DebtTranche,
)
from performa.debt.rates import FixedRate, InterestRate
from performa.development import DevelopmentAnalysisScenario, DevelopmentProject
from performa.valuation import ReversionValuation


def test_development_analysis_scenario_instantiation():
    """Test creating a development analysis scenario."""
    construction_plan = CapitalPlan(
        name="Test Construction",
        capital_items=[
            CapitalItem(
                name="Construction",
                timeline=Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31)),
                value=10000000.0,
                frequency="monthly",
            )
        ],
    )

    financing_plan = ConstructionFacility(
        tranches=[
            DebtTranche(
                name="Construction Loan",
                interest_rate=InterestRate(details=FixedRate(rate=0.065)),
                fee_rate=0.01,
                ltc_threshold=0.75,
            )
        ]
    )

    office_blueprint = OfficeDevelopmentBlueprint(
        name="Test Office",
        vacant_inventory=[
            OfficeVacantSuite(
                suite="Test Suite", floor="1", area=10000.0, use_type="office"
            )
        ],
        absorption_plan=OfficeAbsorptionPlan.with_typical_assumptions(
            name="Test Absorption",
            space_filter=SpaceFilter(),
            pace=OfficeFixedQuantityPace(
                type="FixedQuantity", quantity=10000.0, unit="SF", frequency_months=1
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=40.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",  # $40/SF/year (not monthly!)
                term_months=60,
                upon_expiration="market",
            ),
            start_date_anchor="AnalysisStart",
        ),
    )

    project = DevelopmentProject(
        name="Test Project",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=12000.0,
        net_rentable_area=10000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint],
    )

    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
    global_settings = GlobalSettings(
        analysis_start_date=timeline.start_date.to_timestamp().date()
    )

    scenario = DevelopmentAnalysisScenario(
        model=project, timeline=timeline, settings=global_settings
    )

    assert scenario.model == project
    assert scenario.timeline == timeline
    assert hasattr(scenario, "prepare_models")


def test_development_analysis_scenario_prepare_models():
    """Test that prepare_models method generates cash flow models."""
    construction_plan = CapitalPlan(
        name="Model Generation Test",
        capital_items=[
            CapitalItem(
                name="Site Preparation",
                timeline=Timeline.from_dates(date(2024, 1, 1), date(2024, 6, 30)),
                value=2000000.0,
                frequency="monthly",
            ),
            CapitalItem(
                name="Building Construction",
                timeline=Timeline.from_dates(date(2024, 3, 1), date(2025, 3, 31)),
                value=15000000.0,
                frequency="monthly",
            ),
        ],
    )

    financing_plan = ConstructionFacility(
        tranches=[
            DebtTranche(
                name="Construction Loan",
                interest_rate=InterestRate(details=FixedRate(rate=0.07)),
                fee_rate=0.015,
                ltc_threshold=0.75,
            )
        ]
    )

    office_blueprint = OfficeDevelopmentBlueprint(
        name="Office Building",
        vacant_inventory=[
            OfficeVacantSuite(
                suite="Full Building",
                floor="1-10",
                area=100000.0,
                use_type="office",
                is_divisible=False,
            )
        ],
        absorption_plan=OfficeAbsorptionPlan.with_typical_assumptions(
            name="Office Absorption Plan",
            space_filter=SpaceFilter(),
            pace=OfficeFixedQuantityPace(
                type="FixedQuantity", quantity=100000.0, unit="SF", frequency_months=1
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=40.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",  # $40/SF/year (not monthly!)
                term_months=60,
                upon_expiration="market",
            ),
            start_date_anchor="AnalysisStart",
        ),
    )

    project = DevelopmentProject(
        name="Model Generation Project",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=110000.0,
        net_rentable_area=100000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint],
    )

    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
    global_settings = GlobalSettings(
        analysis_start_date=timeline.start_date.to_timestamp().date()
    )

    scenario = DevelopmentAnalysisScenario(
        model=project, timeline=timeline, settings=global_settings
    )

    # Execute the orchestrator
    cash_flow_models = scenario.prepare_models()

    # Validate basic results
    assert isinstance(cash_flow_models, list)
    assert len(cash_flow_models) > 0

    # Should have construction models
    construction_models = [
        m
        for m in cash_flow_models
        if hasattr(m, "name") and "Construction" in getattr(m, "name", "")
    ]
    assert len(construction_models) > 0


def test_development_analysis_scenario_mixed_use():
    """Test analysis scenario with mixed-use project."""
    construction_plan = CapitalPlan(
        name="Mixed-Use Construction",
        capital_items=[
            CapitalItem(
                name="Foundation and Structure",
                timeline=Timeline.from_dates(date(2024, 1, 1), date(2025, 12, 31)),
                value=35000000.0,
                frequency="monthly",
            )
        ],
    )

    financing_plan = ConstructionFacility(
        tranches=[
            DebtTranche(
                name="Construction Loan",
                interest_rate=InterestRate(details=FixedRate(rate=0.065)),
                fee_rate=0.015,
                ltc_threshold=0.70,
            )
        ]
    )

    office_blueprint = OfficeDevelopmentBlueprint(
        name="Office Component",
        vacant_inventory=[
            OfficeVacantSuite(
                suite="Office Floors", floor="1-15", area=150000.0, use_type="office"
            )
        ],
        absorption_plan=OfficeAbsorptionPlan.with_typical_assumptions(
            name="Office Absorption",
            space_filter=SpaceFilter(),
            pace=OfficeFixedQuantityPace(
                type="FixedQuantity", quantity=30000.0, unit="SF", frequency_months=3
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=40.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",  # $40/SF/year (not monthly!)
                term_months=84,
                upon_expiration="market",
            ),
            start_date_anchor="AnalysisStart",
        ),
    )

    rollover_profile = ResidentialRolloverProfile(
        name="Luxury Residential",
        renewal_probability=0.85,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=3500.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=3500.0),
    )

    residential_blueprint = ResidentialDevelopmentBlueprint(
        name="Residential Component",
        vacant_inventory=[
            ResidentialVacantUnit(
                unit_type_name="Luxury Units",
                unit_count=200,
                avg_area_sf=1200.0,
                market_rent=3200.0,
                rollover_profile=rollover_profile,
            )
        ],
        absorption_plan=ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Residential Absorption",
            space_filter=ResidentialUnitFilter(),
            pace=ResidentialFixedQuantityPace(
                type="FixedQuantity", quantity=25, unit="Units", frequency_months=2
            ),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=3500.0, lease_term_months=12
            ),
            start_date_anchor="AnalysisStart",
        ),
    )

    project = DevelopmentProject(
        name="Mixed-Use Development",
        property_type=AssetTypeEnum.MIXED_USE,
        gross_area=400000.0,
        net_rentable_area=390000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint, residential_blueprint],
    )

    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
    global_settings = GlobalSettings(
        analysis_start_date=timeline.start_date.to_timestamp().date()
    )

    scenario = DevelopmentAnalysisScenario(
        model=project, timeline=timeline, settings=global_settings
    )

    # Execute polymorphic orchestration
    cash_flow_models = scenario.prepare_models()

    # Validate polymorphic processing worked
    assert isinstance(cash_flow_models, list)
    assert len(cash_flow_models) > 0

    # Should have models from both asset types
    assert len(cash_flow_models) >= 1  # At least construction models


def test_development_analysis_scenario_empty_blueprints():
    """Test analysis scenario with no blueprints (construction-only)."""
    construction_plan = CapitalPlan(
        name="Site Development Only",
        capital_items=[
            CapitalItem(
                name="Site Preparation",
                timeline=Timeline.from_dates(date(2024, 1, 1), date(2024, 8, 31)),
                value=5000000.0,
                frequency="monthly",
            )
        ],
    )

    financing_plan = ConstructionFacility(
        tranches=[
            DebtTranche(
                name="Land Development Loan",
                interest_rate=InterestRate(details=FixedRate(rate=0.08)),
                fee_rate=0.02,
                ltc_threshold=0.70,
            )
        ]
    )

    project = DevelopmentProject(
        name="Site Development Project",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=100000.0,
        net_rentable_area=90000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[],  # No blueprints
    )

    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
    global_settings = GlobalSettings(
        analysis_start_date=timeline.start_date.to_timestamp().date()
    )

    scenario = DevelopmentAnalysisScenario(
        model=project, timeline=timeline, settings=global_settings
    )

    # Should still work (construction + financing only)
    cash_flow_models = scenario.prepare_models()

    assert isinstance(cash_flow_models, list)
    # Should have at least construction models
    assert len(cash_flow_models) >= 1


def test_development_analysis_scenario_with_disposition():
    """Test analysis scenario with disposition strategy."""
    construction_plan = CapitalPlan(
        name="Build-to-Sell Construction",
        capital_items=[
            CapitalItem(
                name="Investment Grade Construction",
                timeline=Timeline.from_dates(date(2024, 1, 1), date(2025, 6, 30)),
                value=25000000.0,
                frequency="monthly",
            )
        ],
    )

    financing_plan = ConstructionFacility(
        tranches=[
            DebtTranche(
                name="Construction-to-Perm Loan",
                interest_rate=InterestRate(details=FixedRate(rate=0.065)),
                fee_rate=0.015,
                ltc_threshold=0.75,
            )
        ]
    )

    office_blueprint = OfficeDevelopmentBlueprint(
        name="Investment Grade Office",
        vacant_inventory=[
            OfficeVacantSuite(
                suite="Class A Office", floor="1-12", area=120000.0, use_type="office"
            )
        ],
        absorption_plan=OfficeAbsorptionPlan.with_typical_assumptions(
            name="Pre-Sale Absorption",
            space_filter=SpaceFilter(),
            pace=OfficeFixedQuantityPace(
                type="FixedQuantity", quantity=120000.0, unit="SF", frequency_months=1
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=40.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",  # $40/SF/year (not monthly!)
                term_months=120,  # Long-term lease for investment sale
                upon_expiration="market",
            ),
            start_date_anchor="AnalysisStart",
        ),
    )

    disposition_plan = ReversionValuation(
        name="Investment Sale",
        cap_rate=0.055,
        transaction_costs_rate=0.025,
        disposition_date=date(2028, 12, 31),
    )

    project = DevelopmentProject(
        name="Build-to-Sell Project",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=130000.0,
        net_rentable_area=120000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint],
        disposition_valuation=disposition_plan,
    )

    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
    global_settings = GlobalSettings(
        analysis_start_date=timeline.start_date.to_timestamp().date()
    )

    scenario = DevelopmentAnalysisScenario(
        model=project, timeline=timeline, settings=global_settings
    )

    # Execute with disposition
    cash_flow_models = scenario.prepare_models()

    assert isinstance(cash_flow_models, list)
    assert len(cash_flow_models) > 0

    # Should handle disposition component
    # Note: Actual disposition model creation depends on NOI calculation
    # which may not be available in this simplified test


def test_development_analysis_scenario_polymorphic_iteration():
    """Test that scenario correctly iterates over blueprints polymorphically."""
    construction_plan = CapitalPlan(
        name="Polymorphic Test Construction",
        capital_items=[
            CapitalItem(
                name="Construction",
                timeline=Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31)),
                value=20000000.0,
                frequency="monthly",
            )
        ],
    )

    financing_plan = ConstructionFacility(
        tranches=[
            DebtTranche(
                name="Construction Loan",
                interest_rate=InterestRate(details=FixedRate(rate=0.065)),
                fee_rate=0.01,
                ltc_threshold=0.75,
            )
        ]
    )

    office_blueprint = OfficeDevelopmentBlueprint(
        name="Polymorphic Office",
        vacant_inventory=[
            OfficeVacantSuite(
                suite="Office Space", floor="1-5", area=50000.0, use_type="office"
            )
        ],
        absorption_plan=OfficeAbsorptionPlan.with_typical_assumptions(
            name="Office Absorption",
            space_filter=SpaceFilter(),
            pace=OfficeFixedQuantityPace(
                type="FixedQuantity", quantity=50000.0, unit="SF", frequency_months=1
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=40.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",  # $40/SF/year (not monthly!)
                term_months=60,
                upon_expiration="market",
            ),
            start_date_anchor="AnalysisStart",
        ),
    )

    rollover_profile = ResidentialRolloverProfile(
        name="Standard Terms",
        renewal_probability=0.75,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2800.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2800.0),
    )

    residential_blueprint = ResidentialDevelopmentBlueprint(
        name="Polymorphic Residential",
        vacant_inventory=[
            ResidentialVacantUnit(
                unit_type_name="Standard Units",
                unit_count=80,
                avg_area_sf=1000.0,
                market_rent=2600.0,
                rollover_profile=rollover_profile,
            )
        ],
        absorption_plan=ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Residential Absorption",
            space_filter=ResidentialUnitFilter(),
            pace=ResidentialFixedQuantityPace(
                type="FixedQuantity", quantity=20, unit="Units", frequency_months=1
            ),
            leasing_assumptions=ResidentialDirectLeaseTerms(monthly_rent=2800.0),
            start_date_anchor="AnalysisStart",
        ),
    )

    project = DevelopmentProject(
        name="Polymorphic Test Project",
        property_type=AssetTypeEnum.MIXED_USE,
        gross_area=130000.0,
        net_rentable_area=130000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint, residential_blueprint],
    )

    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))

    # Test the core polymorphic pattern used by the scenario
    # This simulates what the orchestrator does internally
    stabilized_assets = []
    for blueprint in project.blueprints:
        # This should work without any conditionals!
        stabilized_asset = blueprint.to_stabilized_asset(timeline)
        stabilized_assets.append(stabilized_asset)

    # Validate polymorphic results
    assert len(stabilized_assets) == 2

    asset_types = [asset.__class__.__name__ for asset in stabilized_assets]
    assert "OfficeProperty" in asset_types
    assert "ResidentialProperty" in asset_types


def test_development_analysis_end_to_end():
    """Test complete end-to-end development analysis."""
    construction_plan = CapitalPlan(
        name="End-to-End Construction",
        capital_items=[
            CapitalItem(
                name="Complete Building",
                timeline=Timeline.from_dates(date(2024, 1, 1), date(2025, 6, 30)),
                value=30000000.0,
                frequency="monthly",
            )
        ],
    )

    financing_plan = ConstructionFacility(
        tranches=[
            DebtTranche(
                name="Senior Construction Loan",
                interest_rate=InterestRate(details=FixedRate(rate=0.07)),
                fee_rate=0.015,
                ltc_threshold=0.75,
            )
        ]
    )

    office_blueprint = OfficeDevelopmentBlueprint(
        name="End-to-End Office",
        vacant_inventory=[
            OfficeVacantSuite(
                suite="Complete Building",
                floor="1-15",
                area=150000.0,
                use_type="office",
            )
        ],
        absorption_plan=OfficeAbsorptionPlan.with_typical_assumptions(
            name="Complete Absorption",
            space_filter=SpaceFilter(),
            pace=OfficeFixedQuantityPace(
                type="FixedQuantity", quantity=150000.0, unit="SF", frequency_months=1
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=40.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",  # $40/SF/year (not monthly!)
                term_months=84,
                upon_expiration="market",
            ),
            start_date_anchor="AnalysisStart",
        ),
    )

    disposition_plan = ReversionValuation(
        name="Complete Sale", cap_rate=0.055, transaction_costs_rate=0.025
    )

    project = DevelopmentProject(
        name="End-to-End Development",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=165000.0,
        net_rentable_area=150000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint],
        disposition_valuation=disposition_plan,
    )

    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
    global_settings = GlobalSettings(
        analysis_start_date=timeline.start_date.to_timestamp().date()
    )

    # Execute complete analysis using the run function
    scenario = run(model=project, timeline=timeline, settings=global_settings)

    # Validate complete lifecycle execution
    assert scenario is not None

    # Get cash flow summary
    cash_flows = scenario.get_cash_flow_summary()
    assert not cash_flows.empty
    assert len(cash_flows) > 0
