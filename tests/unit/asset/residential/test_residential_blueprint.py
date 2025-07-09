"""Unit tests for residential development blueprint functionality."""

from datetime import date

import pytest
from pydantic import ValidationError

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
from performa.core.base import DevelopmentBlueprintBase
from performa.core.primitives import Timeline


def test_residential_blueprint_inheritance():
    """Test that ResidentialDevelopmentBlueprint inherits from DevelopmentBlueprintBase."""
    assert issubclass(ResidentialDevelopmentBlueprint, DevelopmentBlueprintBase)
    assert hasattr(ResidentialDevelopmentBlueprint, 'to_stabilized_asset')


def test_residential_blueprint_instantiation():
    """Test creating a residential development blueprint with valid data."""
    rollover_profile = ResidentialRolloverProfile(
        name="Standard Residential Terms",
        renewal_probability=0.75,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2800.0),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2800.0,
            renewal_rent_increase_percent=0.03
        )
    )
    
    vacant_unit = ResidentialVacantUnit(
        unit_type_name="1BR/1BA",
        unit_count=50,
        avg_area_sf=850.0,
        market_rent=2500.0,
        rollover_profile=rollover_profile
    )
    
    # Create absorption plan with proper pace structure
    from performa.core.base import FixedQuantityPace  # Import from common base
    
    absorption_plan = ResidentialAbsorptionPlan(
        name="Residential Lease-Up Plan",
        space_filter=ResidentialUnitFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=10,
            unit="Units",
            frequency_months=1
        ),
        leasing_assumptions=ResidentialDirectLeaseTerms(
            monthly_rent=2800.0,
            lease_term_months=12,
            security_deposit_months=1.0
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = ResidentialDevelopmentBlueprint(
        name="Test Residential Development",
        vacant_inventory=[vacant_unit],
        absorption_plan=absorption_plan
    )
    
    assert blueprint.name == "Test Residential Development"
    assert blueprint.use_type == "RESIDENTIAL"
    assert len(blueprint.vacant_inventory) == 1
    assert blueprint.absorption_plan is not None


def test_residential_blueprint_unit_mix_aggregation():
    """Test that blueprint correctly handles multiple unit types."""
    rollover_profile = ResidentialRolloverProfile(
        name="Mixed Unit Terms",
        renewal_probability=0.80,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=3000.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=3000.0)
    )
    
    unit_types = [
        ResidentialVacantUnit(
            unit_type_name="Studio/1BA",
            unit_count=20,
            avg_area_sf=650.0,
            market_rent=2200.0,
            rollover_profile=rollover_profile
        ),
        ResidentialVacantUnit(
            unit_type_name="1BR/1BA", 
            unit_count=40,
            avg_area_sf=900.0,
            market_rent=2800.0,
            rollover_profile=rollover_profile
        ),
        ResidentialVacantUnit(
            unit_type_name="2BR/2BA",
            unit_count=30,
            avg_area_sf=1300.0,
            market_rent=3600.0,
            rollover_profile=rollover_profile
        )
    ]
    
    from performa.core.base import FixedQuantityPace
    
    absorption_plan = ResidentialAbsorptionPlan(
        name="Mixed Unit Plan",
        space_filter=ResidentialUnitFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=15,
            unit="Units",
            frequency_months=2
        ),
        leasing_assumptions=ResidentialDirectLeaseTerms(
            monthly_rent=3000.0,
            lease_term_months=12
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = ResidentialDevelopmentBlueprint(
        name="Mixed Unit Development",
        vacant_inventory=unit_types,
        absorption_plan=absorption_plan
    )
    
    # Verify unit mix structure (unit-centric)
    total_units = sum(unit_group.unit_count for unit_group in blueprint.vacant_inventory)
    assert total_units == 90  # 20 + 40 + 30 units
    assert len(blueprint.vacant_inventory) == 3
    
    # Verify different unit types
    unit_type_names = [unit.unit_type_name for unit in blueprint.vacant_inventory]
    assert "Studio/1BA" in unit_type_names
    assert "1BR/1BA" in unit_type_names
    assert "2BR/2BA" in unit_type_names


def test_residential_blueprint_to_stabilized_asset():
    """Test that blueprint creates a valid stabilized residential property."""
    timeline = Timeline.from_dates(
        start_date=date(2024, 1, 1),
        end_date=date(2029, 12, 31)
    )
    
    rollover_profile = ResidentialRolloverProfile(
        name="Luxury Terms",
        renewal_probability=0.85,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=3500.0),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=3500.0,
            renewal_rent_increase_percent=0.04
        )
    )
    
    vacant_unit = ResidentialVacantUnit(
        unit_type_name="Luxury 2BR/2BA",
        unit_count=100,
        avg_area_sf=1200.0,
        market_rent=3200.0,
        rollover_profile=rollover_profile
    )
    
    from performa.core.base import FixedQuantityPace
    
    absorption_plan = ResidentialAbsorptionPlan(
        name="Luxury Residential Absorption",
        space_filter=ResidentialUnitFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=100,  # Lease all units at once
            unit="Units",
            frequency_months=1
        ),
        leasing_assumptions=ResidentialDirectLeaseTerms(
            monthly_rent=3500.0,
            lease_term_months=12,
            security_deposit_months=2.0
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = ResidentialDevelopmentBlueprint(
        name="Luxury Residential Development",
        vacant_inventory=[vacant_unit],
        absorption_plan=absorption_plan
    )
    
    # Execute asset factory pattern
    stabilized_asset = blueprint.to_stabilized_asset(timeline)
    
    # Validate the result
    assert stabilized_asset is not None
    assert stabilized_asset.__class__.__name__ == "ResidentialProperty"
    assert stabilized_asset.name == "Luxury Residential Development"
    
    # Calculate expected total area
    expected_area = vacant_unit.unit_count * vacant_unit.avg_area_sf
    assert stabilized_asset.net_rentable_area == expected_area
    
    # Validate unit mix structure
    assert stabilized_asset.unit_mix is not None
    assert hasattr(stabilized_asset.unit_mix, 'unit_specs')
    assert hasattr(stabilized_asset.unit_mix, 'vacant_units')
    
    # Validate operating components were applied
    assert stabilized_asset.expenses is not None
    assert stabilized_asset.losses is not None


def test_residential_blueprint_relative_timeline_validation():
    """Test that blueprint rejects relative timelines properly."""
    rollover_profile = ResidentialRolloverProfile(
        name="Test Terms",
        renewal_probability=0.75,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2500.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2500.0)
    )
    
    vacant_unit = ResidentialVacantUnit(
        unit_type_name="Test Units",
        unit_count=10,
        avg_area_sf=800.0,
        market_rent=2400.0,
        rollover_profile=rollover_profile
    )
    
    from performa.core.base import FixedQuantityPace
    
    absorption_plan = ResidentialAbsorptionPlan(
        name="Test Plan",
        space_filter=ResidentialUnitFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=5,
            unit="Units",
            frequency_months=1
        ),
        leasing_assumptions=ResidentialDirectLeaseTerms(
            monthly_rent=2500.0
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = ResidentialDevelopmentBlueprint(
        name="Test Development",
        vacant_inventory=[vacant_unit],
        absorption_plan=absorption_plan
    )
    
    # Create relative timeline
    relative_timeline = Timeline.from_relative(
        months_until_start=6,
        duration_months=60
    )
    
    # Should raise ValueError for relative timeline
    with pytest.raises(ValueError, match="relative timeline"):
        blueprint.to_stabilized_asset(relative_timeline)


def test_residential_blueprint_absorption_plan_validation():
    """Test that blueprint requires valid absorption plan."""
    rollover_profile = ResidentialRolloverProfile(
        name="Valid Terms",
        renewal_probability=0.75,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2600.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2600.0)
    )
    
    vacant_unit = ResidentialVacantUnit(
        unit_type_name="Test Units",
        unit_count=25,
        avg_area_sf=1000.0,
        market_rent=2500.0,
        rollover_profile=rollover_profile
    )
    
    from performa.core.base import FixedQuantityPace
    
    # Valid absorption plan
    valid_plan = ResidentialAbsorptionPlan(
        name="Valid Residential Plan",
        space_filter=ResidentialUnitFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=8,
            unit="Units",
            frequency_months=2
        ),
        leasing_assumptions=ResidentialDirectLeaseTerms(
            monthly_rent=2600.0,
            lease_term_months=12,
            security_deposit_months=1.5
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = ResidentialDevelopmentBlueprint(
        name="Test Development",
        vacant_inventory=[vacant_unit],
        absorption_plan=valid_plan
    )
    
    assert blueprint.absorption_plan.name == "Valid Residential Plan"
    assert blueprint.absorption_plan.pace.quantity == 8
    assert blueprint.absorption_plan.pace.unit == "Units"


def test_residential_blueprint_empty_inventory():
    """Test blueprint behavior with empty vacant inventory."""
    from performa.core.base import FixedQuantityPace
    
    absorption_plan = ResidentialAbsorptionPlan(
        name="Empty Plan",
        space_filter=ResidentialUnitFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=5,
            unit="Units",
            frequency_months=1
        ),
        leasing_assumptions=ResidentialDirectLeaseTerms(
            monthly_rent=2500.0
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = ResidentialDevelopmentBlueprint(
        name="Empty Development",
        vacant_inventory=[],  # Empty list
        absorption_plan=absorption_plan
    )
    
    timeline = Timeline.from_dates(
        start_date=date(2024, 1, 1),
        end_date=date(2029, 12, 31)
    )
    
    # Should raise validation error for empty residential property 
    # (residential properties must have at least one unit)
    with pytest.raises(ValidationError, match="at least one unit specification"):
        blueprint.to_stabilized_asset(timeline)


def test_residential_blueprint_unit_count_calculation():
    """Test unit count calculations across different unit types."""
    rollover_profile = ResidentialRolloverProfile(
        name="Standard Terms",
        renewal_probability=0.75,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2800.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2800.0)
    )
    
    # Mix of different unit sizes and counts
    unit_inventory = [
        ResidentialVacantUnit(
            unit_type_name="Micro Studio",
            unit_count=15,
            avg_area_sf=400.0,
            market_rent=1800.0,
            rollover_profile=rollover_profile
        ),
        ResidentialVacantUnit(
            unit_type_name="Large 3BR",
            unit_count=5,
            avg_area_sf=1800.0,
            market_rent=4500.0,
            rollover_profile=rollover_profile
        )
    ]
    
    from performa.core.base import FixedQuantityPace
    
    absorption_plan = ResidentialAbsorptionPlan(
        name="Mixed Size Plan",
        space_filter=ResidentialUnitFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=10,
            unit="Units",
            frequency_months=1
        ),
        leasing_assumptions=ResidentialDirectLeaseTerms(
            monthly_rent=2800.0
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = ResidentialDevelopmentBlueprint(
        name="Mixed Size Development",
        vacant_inventory=unit_inventory,
        absorption_plan=absorption_plan
    )
    
    # Verify unit counts
    total_units = sum(unit.unit_count for unit in blueprint.vacant_inventory)
    assert total_units == 20  # 15 + 5 units
    
    # Verify area calculations
    total_area = sum(unit.unit_count * unit.avg_area_sf for unit in blueprint.vacant_inventory)
    expected_area = (15 * 400.0) + (5 * 1800.0)  # 6000 + 9000 = 15000
    assert total_area == expected_area


def test_residential_blueprint_name_inheritance():
    """Test that blueprint name is inherited by created assets."""
    timeline = Timeline.from_dates(
        start_date=date(2024, 1, 1),
        end_date=date(2029, 12, 31)
    )
    
    blueprint_name = "Luxury Waterfront Residences"
    
    rollover_profile = ResidentialRolloverProfile(
        name="Luxury Terms",
        renewal_probability=0.90,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=4000.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=4000.0)
    )
    
    vacant_unit = ResidentialVacantUnit(
        unit_type_name="Waterfront 2BR",
        unit_count=50,
        avg_area_sf=1400.0,
        market_rent=3800.0,
        rollover_profile=rollover_profile
    )
    
    from performa.core.base import FixedQuantityPace
    
    absorption_plan = ResidentialAbsorptionPlan(
        name="Waterfront Absorption",
        space_filter=ResidentialUnitFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=50,
            unit="Units",
            frequency_months=1
        ),
        leasing_assumptions=ResidentialDirectLeaseTerms(
            monthly_rent=4000.0,
            lease_term_months=12,
            security_deposit_months=2.0
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = ResidentialDevelopmentBlueprint(
        name=blueprint_name,
        vacant_inventory=[vacant_unit],
        absorption_plan=absorption_plan
    )
    
    stabilized_asset = blueprint.to_stabilized_asset(timeline)
    
    # Validate name inheritance
    assert stabilized_asset.name == blueprint_name
    assert stabilized_asset.name == blueprint.name 