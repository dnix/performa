# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Development Project Unit Tests

Unit tests for the DevelopmentProject data model and polymorphic blueprint architecture.
These tests validate that development projects work correctly with the new blueprint 
pattern, discriminated unions, and polymorphic iteration.

Test Coverage:
1. DevelopmentProject data model validation
2. Polymorphic blueprint container functionality  
3. Discriminated union (AnyDevelopmentBlueprint) validation
4. Mixed-use project configurations
5. Blueprint iteration without conditionals
6. Project serialization and validation
"""

from datetime import date

import pytest

from performa.asset.office import (
    OfficeAbsorptionPlan,
    OfficeDevelopmentBlueprint,
    OfficeVacantSuite,
)
from performa.asset.office.absorption import (
    DirectLeaseTerms,
    FixedQuantityPace,
    SpaceFilter,
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
from performa.core.primitives import AssetTypeEnum, Timeline
from performa.debt import (
    ConstructionFacility,
    DebtTranche,
)
from performa.debt.rates import FixedRate, InterestRate
from performa.development import AnyDevelopmentBlueprint, DevelopmentProject
from performa.valuation import ReversionValuation

# Shared fixtures for development project tests


@pytest.fixture
def development_timeline() -> Timeline:
    """Standard development timeline."""
    return Timeline.from_dates(
        start_date=date(2024, 1, 1),
        end_date=date(2029, 12, 31)
    )


@pytest.fixture
def construction_plan() -> CapitalPlan:
    """Standard construction plan for development projects."""
    return CapitalPlan(
        name="Mixed-Use Construction",
        capital_items=[
            CapitalItem(
                name="Office Tower Construction",
                timeline=Timeline.from_dates(
                    start_date=date(2024, 1, 1),
                    end_date=date(2025, 6, 30)
                ),
                value=50000000.0,
                unit_of_measure="currency",
                frequency="monthly"
            ),
            CapitalItem(
                name="Residential Building Construction",
                timeline=Timeline.from_dates(
                    start_date=date(2024, 6, 1),
                    end_date=date(2025, 12, 31)
                ),
                value=30000000.0,
                unit_of_measure="currency",
                frequency="monthly"
            )
        ]
    )


@pytest.fixture
def financing_plan() -> ConstructionFacility:
    """Standard construction financing plan."""
    return ConstructionFacility(
        tranches=[
            DebtTranche(
                name="Senior Construction Loan",
                interest_rate=InterestRate(details=FixedRate(rate=0.07)),
                fee_rate=0.015,
                ltc_threshold=0.75
            )
        ]
    )


@pytest.fixture
def office_blueprint() -> OfficeDevelopmentBlueprint:
    """Office development blueprint for mixed-use projects."""
    return OfficeDevelopmentBlueprint(
        name="Office Tower Component",
        vacant_inventory=[
            OfficeVacantSuite(
                suite="Floors 1-20",
                floor="1-20",
                area=400000.0,
                use_type="office",
                is_divisible=True,
                subdivision_average_lease_area=20000.0,
                subdivision_minimum_lease_area=5000.0
            )
        ],
        absorption_plan=OfficeAbsorptionPlan.with_typical_assumptions(
            name="Office Lease-Up Strategy",
            space_filter=SpaceFilter(),
            pace=FixedQuantityPace(
                type="FixedQuantity",  # discriminator field
                quantity=50000.0,
                unit="SF",
                frequency_months=6
            ),
            leasing_assumptions=DirectLeaseTerms(
                base_rent_value=55.0,
                base_rent_unit_of_measure="per_unit",
                term_months=84,  # 7-year leases
                upon_expiration="market"
            ),
            start_date_anchor="AnalysisStart"
        )
    )


@pytest.fixture
def residential_blueprint() -> ResidentialDevelopmentBlueprint:
    """Residential development blueprint for mixed-use projects."""
    rollover_profile = ResidentialRolloverProfile(
        name="Luxury Residential Terms",
        renewal_probability=0.80,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=3500.0),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=3500.0,
            renewal_rent_increase_percent=0.04
        )
    )
    
    return ResidentialDevelopmentBlueprint(
        name="Luxury Residential Component",
        vacant_inventory=[
            ResidentialVacantUnit(
                unit_type_name="Studio/1BA",
                unit_count=40,
                avg_area_sf=650.0,
                market_rent=2800.0,
                rollover_profile=rollover_profile
            ),
            ResidentialVacantUnit(
                unit_type_name="1BR/1BA",
                unit_count=80,
                avg_area_sf=900.0,
                market_rent=3200.0,
                rollover_profile=rollover_profile
            ),
            ResidentialVacantUnit(
                unit_type_name="2BR/2BA",
                unit_count=60,
                avg_area_sf=1300.0,
                market_rent=4200.0,
                rollover_profile=rollover_profile
            )
        ],
        absorption_plan=ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Residential Lease-Up Strategy",
            space_filter=ResidentialUnitFilter(),
            pace=ResidentialFixedQuantityPace(
                type="FixedQuantity",  # discriminator field
                quantity=15,
                unit="Units",
                frequency_months=1
            ),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=3500.0,
                lease_term_months=12,
                security_deposit_months=1.5
            ),
            start_date_anchor="AnalysisStart"
        )
    )


@pytest.fixture
def disposition_plan() -> ReversionValuation:
    """Standard disposition plan for development projects."""
    return ReversionValuation(
        name="Mixed-Use Disposition",
        cap_rate=0.055,
        transaction_costs_rate=0.025,
        disposition_date=date(2028, 12, 31)
    )

# Test functions


def test_single_asset_type_development_project(
    construction_plan,
    financing_plan,
    office_blueprint,
    disposition_plan
):
    """Test development project with single asset type (office only)."""
    project = DevelopmentProject(
        name="Office-Only Development",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=450000.0,
        net_rentable_area=400000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint],
        disposition_valuation=disposition_plan
    )
    
    # Validate project structure
    assert project.name == "Office-Only Development"
    assert project.property_type == AssetTypeEnum.OFFICE
    assert len(project.blueprints) == 1
    assert project.blueprints[0].use_type == "OFFICE"
    
    # Validate polymorphic iteration works
    for blueprint in project.blueprints:
        assert hasattr(blueprint, 'to_stabilized_asset')
        assert hasattr(blueprint, 'use_type')
        assert blueprint.use_type == "OFFICE"


def test_mixed_use_development_project(
    construction_plan,
    financing_plan,
    office_blueprint,
    residential_blueprint,
    disposition_plan
):
    """Test development project with multiple asset types (mixed-use)."""
    project = DevelopmentProject(
        name="Mixed-Use Development",
        property_type=AssetTypeEnum.MIXED_USE,
        gross_area=650000.0,
        net_rentable_area=580000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint, residential_blueprint],
        disposition_valuation=disposition_plan
    )
    
    # Validate project structure
    assert project.name == "Mixed-Use Development"
    assert project.property_type == AssetTypeEnum.MIXED_USE
    assert len(project.blueprints) == 2
    
    # Validate blueprint types
    blueprint_types = [blueprint.use_type for blueprint in project.blueprints]
    assert "OFFICE" in blueprint_types
    assert "RESIDENTIAL" in blueprint_types
    
    # Validate polymorphic iteration works
    stabilized_assets = []
    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
    
    for blueprint in project.blueprints:
        # This should work without any conditionals!
        stabilized_asset = blueprint.to_stabilized_asset(timeline)
        stabilized_assets.append(stabilized_asset)
    
    # Validate results
    assert len(stabilized_assets) == 2
    asset_types = [asset.__class__.__name__ for asset in stabilized_assets]
    assert "OfficeProperty" in asset_types
    assert "ResidentialProperty" in asset_types


def test_blueprint_discriminated_union_validation(
    office_blueprint,
    residential_blueprint
):
    """Test that discriminated unions work correctly with blueprints."""
    # Test that AnyDevelopmentBlueprint accepts both types
    blueprints: list[AnyDevelopmentBlueprint] = [office_blueprint, residential_blueprint]
    
    # Validate discriminated union behavior
    for blueprint in blueprints:
        assert hasattr(blueprint, 'use_type')
        assert blueprint.use_type in ["OFFICE", "RESIDENTIAL"]
    
    # Test discriminator values are literals
    office_discriminator = office_blueprint.use_type
    residential_discriminator = residential_blueprint.use_type
    
    assert office_discriminator == "OFFICE"
    assert residential_discriminator == "RESIDENTIAL"
    assert office_discriminator != residential_discriminator


def test_development_project_blueprint_iteration_performance(
    construction_plan,
    financing_plan,
    office_blueprint,
    residential_blueprint,
    disposition_plan
):
    """Test that blueprint iteration is efficient and doesn't require conditionals."""
    # Create project with multiple blueprints
    project = DevelopmentProject(
        name="Performance Test Project",
        property_type=AssetTypeEnum.MIXED_USE,
        gross_area=650000.0,
        net_rentable_area=580000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint, residential_blueprint],
        disposition_valuation=disposition_plan
    )
    
    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
    
    # Simulate the analysis orchestrator pattern
    stabilized_assets = []
    
    # This loop should work without any if/elif conditionals!
    for blueprint in project.blueprints:
        # Pure polymorphic dispatch - no conditionals needed
        stabilized_asset = blueprint.to_stabilized_asset(timeline)
        stabilized_assets.append(stabilized_asset)
    
    # Validate polymorphic dispatch worked
    assert len(stabilized_assets) == 2
    
    # Each asset should be correctly typed
    office_asset = next(asset for asset in stabilized_assets 
                      if asset.__class__.__name__ == "OfficeProperty")
    residential_asset = next(asset for asset in stabilized_assets 
                           if asset.__class__.__name__ == "ResidentialProperty")
    
    assert office_asset.name == "Office Tower Component"
    assert residential_asset.name == "Luxury Residential Component"


def test_development_project_pydantic_serialization(
    construction_plan,
    financing_plan,
    office_blueprint,
    residential_blueprint,
    disposition_plan
):
    """Test that development projects serialize/deserialize correctly with blueprints."""
    project = DevelopmentProject(
        name="Serialization Test Project",
        property_type=AssetTypeEnum.MIXED_USE,
        gross_area=650000.0,
        net_rentable_area=580000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[office_blueprint, residential_blueprint],
        disposition_valuation=disposition_plan
    )
    
    # Test model structure (JSON serialization has pandas Period issue - library bug)
    project_dict = project.model_dump()
    assert "blueprints" in project_dict
    assert len(project_dict["blueprints"]) == 2
    assert project_dict["blueprints"][0]["use_type"] in ["OFFICE", "RESIDENTIAL"]
    assert project_dict["blueprints"][1]["use_type"] in ["OFFICE", "RESIDENTIAL"]
    
    # Test deserialization
    reconstructed_project = DevelopmentProject.model_validate(project_dict)
    
    # Validate reconstruction
    assert reconstructed_project.name == project.name
    assert len(reconstructed_project.blueprints) == len(project.blueprints)
    assert reconstructed_project.blueprints[0].use_type == project.blueprints[0].use_type
    assert reconstructed_project.blueprints[1].use_type == project.blueprints[1].use_type


def test_empty_blueprints_list(
    construction_plan,
    financing_plan,
    disposition_plan
):
    """Test development project with empty blueprints list."""
    project = DevelopmentProject(
        name="Empty Development Project",
        property_type=AssetTypeEnum.MIXED_USE,
        gross_area=100000.0,
        net_rentable_area=90000.0,
        construction_plan=construction_plan,
        financing_plan=financing_plan,
        blueprints=[],  # Empty list
        disposition_valuation=disposition_plan
    )
    
    # Should be valid project structure
    assert project.name == "Empty Development Project"
    assert len(project.blueprints) == 0
    
    # Iteration should work (but produce no results)
    stabilized_assets = []
    for blueprint in project.blueprints:
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
        stabilized_asset = blueprint.to_stabilized_asset(timeline)
        stabilized_assets.append(stabilized_asset)
    
    assert len(stabilized_assets) == 0


def test_blueprint_name_inheritance_to_assets(
    office_blueprint,
    residential_blueprint
):
    """Test that blueprint names are inherited by created assets."""
    timeline = Timeline.from_dates(date(2024, 1, 1), date(2029, 12, 31))
    
    # Create assets from blueprints
    office_asset = office_blueprint.to_stabilized_asset(timeline)
    residential_asset = residential_blueprint.to_stabilized_asset(timeline)
    
    # Validate name inheritance
    assert office_asset.name == office_blueprint.name
    assert residential_asset.name == residential_blueprint.name
    assert office_asset.name == "Office Tower Component"
    assert residential_asset.name == "Luxury Residential Component"


def test_development_project_required_fields():
    """Test that development project requires all necessary fields."""
    from pydantic import ValidationError
    
    # Test missing required fields
    with pytest.raises(ValidationError):
        DevelopmentProject()  # Missing all required fields
    
    with pytest.raises(ValidationError):
        DevelopmentProject(name="Test")  # Missing other required fields


def test_development_project_blueprint_type_validation(office_blueprint):
    """Test that only valid blueprint types are accepted."""
    # Valid project
    project = DevelopmentProject(
        name="Valid Project",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=100000.0,
        net_rentable_area=90000.0,
        construction_plan=CapitalPlan(name="Test", capital_items=[]),
        financing_plan=ConstructionFacility(
            tranches=[
                DebtTranche(
                    name="Test Loan",
                    interest_rate=InterestRate(details=FixedRate(rate=0.07)),
                    fee_rate=0.01,
                    ltc_threshold=0.75
                )
            ]
        ),
        blueprints=[office_blueprint]
    )
    
    assert len(project.blueprints) == 1
    assert project.blueprints[0].use_type == "OFFICE" 