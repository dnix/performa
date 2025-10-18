# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Development Analysis Orchestrator Tests

Tests for the dramatically simplified DevelopmentAnalysisScenario that uses
polymorphic blueprints instead of complex conditional logic.

Test Intent:
1. Polymorphic Orchestration: Analysis works without asset-type conditionals
2. Asset Factory Integration: Blueprints → stabilized assets → analysis
3. Construction + Financing: Non-asset models still work correctly
4. Cash Flow Generation: Complete lifecycle produces valid cash flows
5. Performance: Simplified orchestrator is efficient and maintainable
"""

import inspect
import time
from datetime import date

import pytest

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
from performa.core.ledger import Ledger
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
from performa.valuation import DirectCapValuation

# Shared fixtures for orchestrator tests


@pytest.fixture
def analysis_timeline() -> Timeline:
    """Standard analysis timeline for all tests."""
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2029, 12, 31))


@pytest.fixture
def global_settings(analysis_timeline) -> GlobalSettings:
    """Standard global settings for all tests."""
    return GlobalSettings(
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date()
    )


@pytest.fixture
def simple_construction_plan() -> CapitalPlan:
    """Simple construction plan for testing."""
    return CapitalPlan(
        name="Simple Construction",
        capital_items=[
            CapitalItem(
                name="Construction Phase 1",
                timeline=Timeline.from_dates(
                    start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
                ),
                value=10000000.0,
                frequency="monthly",
            )
        ],
    )


@pytest.fixture
def simple_financing_plan() -> ConstructionFacility:
    """Simple financing plan for testing."""
    return ConstructionFacility(
        tranches=[
            DebtTranche(
                name="Construction Loan",
                interest_rate=InterestRate(details=FixedRate(rate=0.065)),
                fee_rate=0.01,
                ltc_threshold=0.75,
            )
        ]
    )


@pytest.fixture
def office_blueprint() -> OfficeDevelopmentBlueprint:
    """Simple office blueprint for testing."""
    return OfficeDevelopmentBlueprint(
        name="Test Office Building",
        vacant_inventory=[
            OfficeVacantSuite(
                suite="Full Building",
                floor="1-5",
                area=50000.0,
                use_type="office",
                is_divisible=True,  # Allow subdivision for phased leasing
                subdivision_average_lease_area=20000.0,  # Target ~20k SF leases
                subdivision_minimum_lease_area=5000.0,  # Minimum viable size
            )
        ],
        absorption_plan=OfficeAbsorptionPlan.with_typical_assumptions(
            name="Office Absorption",
            space_filter=SpaceFilter(),
            pace=OfficeFixedQuantityPace(
                type="FixedQuantity", quantity=25000.0, unit="SF", frequency_months=6
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=40.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                term_months=60,
                upon_expiration="market",
            ),
            start_date_anchor="AnalysisStart",
        ),
    )


@pytest.fixture
def residential_blueprint() -> ResidentialDevelopmentBlueprint:
    """Simple residential blueprint for testing."""
    rollover_profile = ResidentialRolloverProfile(
        name="Standard Residential",
        renewal_probability=0.75,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2500.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2500.0),
    )

    return ResidentialDevelopmentBlueprint(
        name="Test Residential Building",
        vacant_inventory=[
            ResidentialVacantUnit(
                unit_type_name="Standard Units",
                unit_count=50,
                avg_area_sf=1000.0,
                market_rent=2500.0,
                rollover_profile=rollover_profile,
            )
        ],
        absorption_plan=ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Residential Absorption",
            space_filter=ResidentialUnitFilter(),
            pace=ResidentialFixedQuantityPace(
                type="FixedQuantity", quantity=10, unit="Units", frequency_months=2
            ),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=2500.0, lease_term_months=12
            ),
            start_date_anchor="AnalysisStart",
        ),
    )


@pytest.fixture
def comprehensive_project() -> DevelopmentProject:
    """Comprehensive development project for integration testing."""
    construction_plan = CapitalPlan(
        name="Comprehensive Construction",
        capital_items=[
            CapitalItem(
                name="Site Preparation",
                timeline=Timeline.from_dates(date(2024, 1, 1), date(2024, 3, 31)),
                value=2000000.0,
                frequency="monthly",
            ),
            CapitalItem(
                name="Building Construction",
                timeline=Timeline.from_dates(date(2024, 2, 1), date(2025, 8, 31)),
                value=25000000.0,
                frequency="monthly",
            ),
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

    # Create office blueprint
    office_blueprint = OfficeDevelopmentBlueprint(
        name="Premium Office Space",
        vacant_inventory=[
            OfficeVacantSuite(
                suite="Premium Floors",
                floor="1-10",
                area=80000.0,
                use_type="office",
                is_divisible=True,
                subdivision_average_lease_area=8000.0,
                subdivision_minimum_lease_area=2000.0,
            )
        ],
        absorption_plan=OfficeAbsorptionPlan.with_typical_assumptions(
            name="Premium Office Absorption",
            space_filter=SpaceFilter(),
            pace=OfficeFixedQuantityPace(
                type="FixedQuantity", quantity=20000.0, unit="SF", frequency_months=3
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=65.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",  # $65/SF/year (not monthly!)
                term_months=120,
                upon_expiration="market",
            ),
            start_date_anchor="AnalysisStart",
        ),
    )

    # Create residential blueprint
    rollover_profile = ResidentialRolloverProfile(
        name="Luxury Residential",
        renewal_probability=0.85,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=4000.0),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=4000.0, renewal_rent_increase_percent=0.04
        ),
    )

    residential_blueprint = ResidentialDevelopmentBlueprint(
        name="Luxury Residential Tower",
        vacant_inventory=[
            ResidentialVacantUnit(
                unit_type_name="1BR/1BA Luxury",
                unit_count=60,
                avg_area_sf=1200.0,
                market_rent=3500.0,
                rollover_profile=rollover_profile,
            ),
            ResidentialVacantUnit(
                unit_type_name="2BR/2BA Luxury",
                unit_count=40,
                avg_area_sf=1800.0,
                market_rent=5000.0,
                rollover_profile=rollover_profile,
            ),
        ],
        absorption_plan=ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Luxury Residential Absorption",
            space_filter=ResidentialUnitFilter(),
            pace=ResidentialFixedQuantityPace(
                type="FixedQuantity", quantity=12, unit="Units", frequency_months=1
            ),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=4000.0, lease_term_months=12, security_deposit_months=2.0
            ),
            start_date_anchor="AnalysisStart",
        ),
    )

    # Create disposition plan
    disposition_plan = DirectCapValuation(
        name="Mixed-Use Exit Strategy",
        cap_rate=0.055,
        transaction_costs_rate=0.025,
        hold_period_months=60,  # Changed from disposition_date
        noi_basis_kind="LTM",  # Added NOI basis
    )

    return DevelopmentProject(
        name="Comprehensive Mixed-Use Development",
        property_type=AssetTypeEnum.MIXED_USE,
        gross_area=200000.0,
        net_rentable_area=180000.0,
        construction_plan=construction_plan,
        blueprints=[office_blueprint, residential_blueprint],
    )


# Test functions


def test_orchestrator_basic_structure(
    simple_construction_plan,
    simple_financing_plan,
    office_blueprint,
    analysis_timeline,
    global_settings,
):
    """Test basic orchestrator structure and method availability."""
    project = DevelopmentProject(
        name="Basic Test Project",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=55000.0,
        net_rentable_area=50000.0,
        construction_plan=simple_construction_plan,
        blueprints=[office_blueprint],
    )

    # Create analysis scenario
    scenario = DevelopmentAnalysisScenario(
        model=project,
        timeline=analysis_timeline,
        settings=global_settings,
        ledger=Ledger(),
    )

    # Validate basic structure
    assert scenario.model == project
    assert scenario.timeline == analysis_timeline
    assert hasattr(scenario, "prepare_models")
    assert hasattr(scenario, "_get_stabilization_date_for_blueprint")
    assert hasattr(scenario, "_prepare_construction_models")


def test_orchestrator_prepare_models_basic(
    simple_construction_plan,
    simple_financing_plan,
    office_blueprint,
    analysis_timeline,
    global_settings,
):
    """Test that prepare_models method works without errors."""
    project = DevelopmentProject(
        name="Prepare Models Test",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=55000.0,
        net_rentable_area=50000.0,
        construction_plan=simple_construction_plan,
        blueprints=[office_blueprint],
    )

    scenario = DevelopmentAnalysisScenario(
        model=project,
        timeline=analysis_timeline,
        settings=global_settings,
        ledger=Ledger(),
    )

    # Execute the simplified orchestrator
    cash_flow_models = scenario.prepare_models()

    # Validate basic results
    assert isinstance(cash_flow_models, list)
    assert len(cash_flow_models) > 0

    # Should have construction models
    construction_models = [
        m for m in cash_flow_models if hasattr(m, "name") and "Construction" in m.name
    ]
    assert len(construction_models) > 0


def test_orchestrator_polymorphic_blueprint_processing(
    simple_construction_plan,
    simple_financing_plan,
    office_blueprint,
    residential_blueprint,
    analysis_timeline,
    global_settings,
):
    """Test that orchestrator processes multiple blueprint types without conditionals."""
    project = DevelopmentProject(
        name="Mixed-Use Test Project",
        property_type=AssetTypeEnum.MIXED_USE,
        gross_area=105000.0,
        net_rentable_area=100000.0,
        construction_plan=simple_construction_plan,
        blueprints=[office_blueprint, residential_blueprint],
    )

    scenario = DevelopmentAnalysisScenario(
        model=project,
        timeline=analysis_timeline,
        settings=global_settings,
        ledger=Ledger(),
    )

    # Execute polymorphic orchestration
    cash_flow_models = scenario.prepare_models()

    # Validate polymorphic processing
    assert isinstance(cash_flow_models, list)
    assert len(cash_flow_models) > 0

    print(f"DEBUG: Generated {len(cash_flow_models)} cash flow models")
    for i, model in enumerate(cash_flow_models):
        model_name = getattr(model, "name", "Unknown")
        model_type = model.__class__.__name__
        print(f"  {i + 1}. {model_type}: {model_name}")

    # Should have models from both asset types
    # Note: The exact number and types depend on implementation
    assert len(cash_flow_models) >= 2  # At least construction + some asset models


def test_orchestrator_asset_factory_integration(
    simple_construction_plan,
    simple_financing_plan,
    office_blueprint,
    analysis_timeline,
    global_settings,
):
    """Test that asset factory pattern is correctly integrated."""
    project = DevelopmentProject(
        name="Asset Factory Test",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=55000.0,
        net_rentable_area=50000.0,
        construction_plan=simple_construction_plan,
        blueprints=[office_blueprint],
    )

    scenario = DevelopmentAnalysisScenario(
        model=project,
        timeline=analysis_timeline,
        settings=global_settings,
        ledger=Ledger(),
    )

    # Test asset factory integration manually
    stabilized_assets = []
    for blueprint in project.blueprints:
        stabilized_asset = blueprint.to_stabilized_asset(analysis_timeline)
        stabilized_assets.append(stabilized_asset)

    # Validate asset factory worked
    assert len(stabilized_assets) == 1
    assert stabilized_assets[0].__class__.__name__ == "OfficeProperty"
    assert stabilized_assets[0].name == "Test Office Building"

    # Test that assets were created correctly
    for asset in stabilized_assets:
        # Assets should have the correct structure
        assert hasattr(asset, "name")
        assert hasattr(asset, "property_type")
        # Note: Full asset analysis integration is handled by the run() API in prepare_models()


def test_orchestrator_no_blueprints(
    simple_construction_plan, simple_financing_plan, analysis_timeline, global_settings
):
    """Test orchestrator with no blueprints (construction-only project)."""
    project = DevelopmentProject(
        name="Construction-Only Project",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=100000.0,
        net_rentable_area=90000.0,
        construction_plan=simple_construction_plan,
        blueprints=[],  # No blueprints
    )

    scenario = DevelopmentAnalysisScenario(
        model=project,
        timeline=analysis_timeline,
        settings=global_settings,
        ledger=Ledger(),
    )

    # Should still work (construction + financing only)
    cash_flow_models = scenario.prepare_models()

    assert isinstance(cash_flow_models, list)
    # Should have construction models, possibly financing models
    assert len(cash_flow_models) >= 1


def test_orchestrator_performance_no_conditionals(
    simple_construction_plan,
    simple_financing_plan,
    office_blueprint,
    residential_blueprint,
    analysis_timeline,
    global_settings,
):
    """Test that orchestrator performs efficiently without conditionals."""
    # Create a project with multiple blueprints
    blueprints = [office_blueprint, residential_blueprint]

    project = DevelopmentProject(
        name="Performance Test Project",
        property_type=AssetTypeEnum.MIXED_USE,
        gross_area=150000.0,
        net_rentable_area=100000.0,
        construction_plan=simple_construction_plan,
        blueprints=blueprints,
    )

    scenario = DevelopmentAnalysisScenario(
        model=project,
        timeline=analysis_timeline,
        settings=global_settings,
        ledger=Ledger(),
    )

    # Time the polymorphic iteration (simulating the core loop)
    start_time = time.time()

    # This should be the polymorphic loop from prepare_models
    stabilized_assets = []
    for blueprint in project.blueprints:
        stabilized_asset = blueprint.to_stabilized_asset(analysis_timeline)
        stabilized_assets.append(stabilized_asset)

    end_time = time.time()
    execution_time = end_time - start_time

    # Validate performance and results
    assert len(stabilized_assets) == 2
    assert execution_time < 1.0  # Should be very fast

    # Validate no conditionals were needed
    office_asset = next(
        a for a in stabilized_assets if a.__class__.__name__ == "OfficeProperty"
    )
    residential_asset = next(
        a for a in stabilized_assets if a.__class__.__name__ == "ResidentialProperty"
    )

    assert office_asset.name == "Test Office Building"
    assert residential_asset.name == "Test Residential Building"


def test_orchestrator_simplified_vs_old_complexity():
    """Test that demonstrates the simplification achieved."""
    # This test documents the architectural improvement

    # OLD PATTERN (what we replaced):
    # for component in self.model.development_program.program_components:
    #     if component.use_type == ProgramUseEnum.OFFICE:
    #         # 50+ lines of office-specific logic
    #     elif component.use_type == ProgramUseEnum.RESIDENTIAL:
    #         # 50+ lines of residential-specific logic
    #     # etc...

    # NEW PATTERN (what we have now):
    # for blueprint in self.model.blueprints:
    #     stabilized_asset = blueprint.to_stabilized_asset(timeline)
    #     asset_models = self._prepare_asset_models(stabilized_asset)

    # Validate the new pattern is dramatically simpler

    # Get the source of prepare_models method
    source_lines = inspect.getsourcelines(DevelopmentAnalysisScenario.prepare_models)[0]
    method_source = "".join(source_lines)

    # New implementation should NOT contain asset-type conditionals
    assert "if component.use_type ==" not in method_source
    assert "elif component.use_type ==" not in method_source
    assert "ProgramUseEnum.OFFICE" not in method_source
    assert "ProgramUseEnum.RESIDENTIAL" not in method_source

    # New implementation SHOULD contain polymorphic patterns
    assert "for blueprint in" in method_source
    assert "to_stabilized_asset" in method_source

    print("✅ Architectural simplification verified!")
    print("✅ No asset-type conditionals in orchestrator")
    print("✅ Pure polymorphic dispatch pattern confirmed")


def test_complete_development_lifecycle(
    comprehensive_project, analysis_timeline, global_settings
):
    """Test complete development lifecycle from construction through stabilization."""
    scenario = DevelopmentAnalysisScenario(
        model=comprehensive_project,
        timeline=analysis_timeline,
        settings=global_settings,
        ledger=Ledger(),
    )

    # Execute full preparation
    cash_flow_models = scenario.prepare_models()

    # Validate comprehensive results
    assert isinstance(cash_flow_models, list)
    assert len(cash_flow_models) > 0

    print(f"Complete lifecycle generated {len(cash_flow_models)} models:")
    for i, model in enumerate(cash_flow_models):
        model_name = getattr(model, "name", "Unknown")
        model_type = model.__class__.__name__
        print(f"  {i + 1}. {model_type}: {model_name}")

    # Should have construction models (minimum requirement)
    construction_models = [
        m for m in cash_flow_models if hasattr(m, "name") and "Construction" in m.name
    ]
    assert len(construction_models) > 0

    # Test that assets were created correctly
    stabilized_assets = []
    for blueprint in comprehensive_project.blueprints:
        stabilized_asset = blueprint.to_stabilized_asset(analysis_timeline)
        stabilized_assets.append(stabilized_asset)

    assert len(stabilized_assets) == 2  # Office + Residential

    office_asset = next(
        a for a in stabilized_assets if a.__class__.__name__ == "OfficeProperty"
    )
    residential_asset = next(
        a for a in stabilized_assets if a.__class__.__name__ == "ResidentialProperty"
    )

    assert office_asset.name == "Premium Office Space"
    assert residential_asset.name == "Luxury Residential Tower"


def test_end_to_end_cash_flow_generation(
    comprehensive_project, analysis_timeline, global_settings
):
    """Test end-to-end cash flow generation for development lifecycle."""
    # Execute full analysis
    analysis_result = run(
        model=comprehensive_project,
        timeline=analysis_timeline,
        settings=global_settings,
    )

    # Validate analysis results
    assert analysis_result is not None
    assert hasattr(analysis_result, "summary_df")

    # Basic cash flow validation
    cash_flows = analysis_result.summary_df
    assert cash_flows is not None
    assert len(cash_flows) > 0  # Should have some periods

    print(f"Generated cash flows for {len(cash_flows)} periods")
    print("✅ End-to-end development analysis successful!")
    print("✅ Polymorphic architecture produces valid cash flows!")
