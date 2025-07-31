# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for office development blueprint functionality."""

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
from performa.core.base import DevelopmentBlueprintBase
from performa.core.primitives import Timeline, PropertyAttributeKey, UponExpirationEnum


def test_office_blueprint_inheritance():
    """Test that OfficeDevelopmentBlueprint inherits from DevelopmentBlueprintBase."""
    assert issubclass(OfficeDevelopmentBlueprint, DevelopmentBlueprintBase)
    assert hasattr(OfficeDevelopmentBlueprint, 'to_stabilized_asset')


def test_office_blueprint_instantiation():
    """Test creating an office development blueprint with valid data."""
    vacant_suite = OfficeVacantSuite(
        suite="Floor 1-5",
        floor="1-5",
        area=25000.0,
        use_type="office",  # ProgramUseEnum value
        is_divisible=False
    )
    
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Office Lease-Up Plan",
        space_filter=SpaceFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",  # discriminator field
            quantity=10000.0,
            unit="SF",
            frequency_months=3
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=45.0,
            base_rent_unit_of_measure="per_unit",
            term_months=60,
            upon_expiration="market"
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = OfficeDevelopmentBlueprint(
        name="Test Office Development",
        vacant_inventory=[vacant_suite],
        absorption_plan=absorption_plan
    )
    
    assert blueprint.name == "Test Office Development"
    assert blueprint.use_type == "OFFICE"
    assert len(blueprint.vacant_inventory) == 1
    assert blueprint.absorption_plan is not None


def test_office_blueprint_vacant_inventory_aggregation():
    """Test that blueprint correctly handles multiple vacant suites."""
    suites = [
        OfficeVacantSuite(
            suite="Floor 1-3",
            floor="1-3", 
            area=15000.0,
            use_type="office",
            is_divisible=False
        ),
        OfficeVacantSuite(
            suite="Floor 4-6",
            floor="4-6",
            area=20000.0,
            use_type="office",
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0
        )
    ]
    
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Multi-Floor Plan",
        space_filter=SpaceFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=10000.0,
            unit="SF",
            frequency_months=6
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=50.0,
            base_rent_unit_of_measure="per_unit",
            term_months=84,
            upon_expiration="market"
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = OfficeDevelopmentBlueprint(
        name="Multi-Floor Development",
        vacant_inventory=suites,
        absorption_plan=absorption_plan
    )
    
    # Verify inventory structure
    total_area = sum(suite.area for suite in blueprint.vacant_inventory)
    assert total_area == 35000.0
    assert len(blueprint.vacant_inventory) == 2
    
    # Verify mix of divisible and non-divisible
    divisible_suites = [s for s in blueprint.vacant_inventory if s.is_divisible]
    non_divisible_suites = [s for s in blueprint.vacant_inventory if not s.is_divisible]
    assert len(divisible_suites) == 1
    assert len(non_divisible_suites) == 1


def test_office_blueprint_to_stabilized_asset():
    """Test that blueprint creates a valid stabilized office property."""
    timeline = Timeline.from_dates(
        start_date=date(2024, 1, 1),
        end_date=date(2029, 12, 31)
    )
    
    vacant_suite = OfficeVacantSuite(
        suite="Premium Office Space",
        floor="10-15",
        area=50000.0,
        use_type="office",
        is_divisible=False
    )
    
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Premium Office Absorption",
        space_filter=SpaceFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=50000.0,  # Lease entire space at once
            unit="SF",
            frequency_months=1
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=55.0,
            base_rent_unit_of_measure="per_unit",
            term_months=60,
            upon_expiration="market"
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = OfficeDevelopmentBlueprint(
        name="Premium Office Development",
        vacant_inventory=[vacant_suite],
        absorption_plan=absorption_plan
    )
    
    # Execute asset factory pattern
    stabilized_asset = blueprint.to_stabilized_asset(timeline)
    
    # Validate the result
    assert stabilized_asset is not None
    assert stabilized_asset.__class__.__name__ == "OfficeProperty"
    assert stabilized_asset.name == "Premium Office Development"
    assert stabilized_asset.net_rentable_area == 50000.0
    
    # Validate structure
    assert stabilized_asset.rent_roll is not None
    assert hasattr(stabilized_asset.rent_roll, 'leases')
    assert hasattr(stabilized_asset.rent_roll, 'vacant_suites')
    
    # Validate operating components were applied
    assert stabilized_asset.expenses is not None
    assert stabilized_asset.losses is not None


def test_office_blueprint_relative_timeline_validation():
    """Test that blueprint rejects relative timelines properly."""
    vacant_suite = OfficeVacantSuite(
        suite="Test Suite",
        floor="1",
        area=10000.0,
        use_type="office"
    )
    
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Test Plan",
        space_filter=SpaceFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=10000.0,
            unit="SF",
            frequency_months=1
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=40.0,
            base_rent_unit_of_measure="per_unit",
            term_months=60,
            upon_expiration="market"
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = OfficeDevelopmentBlueprint(
        name="Test Development",
        vacant_inventory=[vacant_suite],
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


def test_office_blueprint_absorption_plan_validation():
    """Test that blueprint requires valid absorption plan."""
    vacant_suite = OfficeVacantSuite(
        suite="Test Suite",
        floor="1",
        area=10000.0,
        use_type="office"
    )
    
    # Valid absorption plan
    valid_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Valid Plan",
        space_filter=SpaceFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=5000.0,
            unit="SF",
            frequency_months=2
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=40.0,
            base_rent_unit_of_measure="per_unit",
            term_months=60,
            upon_expiration="market"
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = OfficeDevelopmentBlueprint(
        name="Test Development",
        vacant_inventory=[vacant_suite],
        absorption_plan=valid_plan
    )
    
    assert blueprint.absorption_plan.name == "Valid Plan"
    assert blueprint.absorption_plan.pace.quantity == 5000.0
    assert blueprint.absorption_plan.pace.unit == "SF"


def test_office_blueprint_empty_inventory():
    """Test blueprint behavior with empty vacant inventory."""
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Empty Plan",
        space_filter=SpaceFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=1000.0,
            unit="SF",
            frequency_months=1
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=40.0,
            base_rent_unit_of_measure="per_unit",
            term_months=60,
            upon_expiration="market"
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = OfficeDevelopmentBlueprint(
        name="Empty Development",
        vacant_inventory=[],  # Empty list
        absorption_plan=absorption_plan
    )
    
    timeline = Timeline.from_dates(
        start_date=date(2024, 1, 1),
        end_date=date(2029, 12, 31)
    )
    
    # Should create asset with no space
    stabilized_asset = blueprint.to_stabilized_asset(timeline)
    assert stabilized_asset.net_rentable_area == 0.0
    assert len(stabilized_asset.rent_roll.leases) == 0


def test_office_blueprint_pace_type_discriminator():
    """Test that different pace types work with discriminated union."""
    vacant_suite = OfficeVacantSuite(
        suite="Test Suite",
        floor="1",
        area=20000.0,
        use_type="office"
    )
    
    # Test FixedQuantityPace
    fixed_pace_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Fixed Pace Plan",
        space_filter=SpaceFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=10000.0,
            unit="SF",
            frequency_months=3
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=45.0,
            base_rent_unit_of_measure="per_unit",
            term_months=60,
            upon_expiration="market"
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = OfficeDevelopmentBlueprint(
        name="Fixed Pace Development",
        vacant_inventory=[vacant_suite],
        absorption_plan=fixed_pace_plan
    )
    
    assert blueprint.absorption_plan.pace.type == "FixedQuantity"
    assert blueprint.absorption_plan.pace.quantity == 10000.0
    assert blueprint.absorption_plan.pace.unit == "SF"


def test_office_blueprint_name_inheritance():
    """Test that blueprint name is inherited by created assets."""
    timeline = Timeline.from_dates(
        start_date=date(2024, 1, 1),
        end_date=date(2029, 12, 31)
    )
    
    blueprint_name = "Corporate Headquarters Development"
    
    vacant_suite = OfficeVacantSuite(
        suite="Corporate HQ",
        floor="1-20",
        area=100000.0,
        use_type="office"
    )
    
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="HQ Absorption",
        space_filter=SpaceFilter(),
        pace=FixedQuantityPace(
            type="FixedQuantity",
            quantity=100000.0,
            unit="SF",
            frequency_months=1
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=60.0,
            base_rent_unit_of_measure="per_unit",
            term_months=120,  # 10-year lease
            upon_expiration="market"
        ),
        start_date_anchor="AnalysisStart"
    )
    
    blueprint = OfficeDevelopmentBlueprint(
        name=blueprint_name,
        vacant_inventory=[vacant_suite],
        absorption_plan=absorption_plan
    )
    
    stabilized_asset = blueprint.to_stabilized_asset(timeline)
    
    # Validate name inheritance
    assert stabilized_asset.name == blueprint_name
    assert stabilized_asset.name == blueprint.name 