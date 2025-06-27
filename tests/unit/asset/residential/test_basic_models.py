"""
Unit tests for basic residential asset models.

Tests the core components built in Steps 1.1-1.3:
- ResidentialProperty and related models
- Unit mix architecture (ResidentialUnitSpec, ResidentialRentRoll)
- Rollover profiles and lease terms
"""

from datetime import date
from uuid import UUID

import pytest

from performa.asset.residential import (
    ResidentialCollectionLoss,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialMiscIncome,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
    ResidentialVacantUnit,
)
from performa.common.primitives import (
    AssetTypeEnum,
    GrowthRate,
    Timeline,
    UnitOfMeasureEnum,
)

# Test Step 1.1: Basic model creation and inheritance

def test_residential_expenses_creation():
    """Test that ResidentialExpenses can be created and inherits properly"""
    expenses = ResidentialExpenses()
    assert expenses.operating_expenses == []
    assert expenses.capital_expenses == []


def test_residential_losses_creation():
    """Test that ResidentialLosses can be created with proper subcomponents"""
    losses = ResidentialLosses(
        general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),
        collection_loss=ResidentialCollectionLoss(rate=0.01)
    )
    assert losses.general_vacancy.rate == 0.05
    assert losses.collection_loss.rate == 0.01


def test_residential_misc_income_creation():
    """Test that ResidentialMiscIncome inherits from base properly"""
    misc_income = ResidentialMiscIncome(
        name="Parking Fees",
        value=50.0,  # $50/month per space
        timeline=Timeline.from_dates(date(2024, 1, 1), end_date=date(2024, 12, 31)),
        unit_of_measure=UnitOfMeasureEnum.CURRENCY  # Required by CashFlowModel base
    )
    assert misc_income.name == "Parking Fees"
    assert misc_income.value == 50.0


# Test Step 1.2: Unit mix architecture - the paradigm shift

@pytest.fixture
def sample_rollover_profile():
    """Provides a basic rollover profile for testing"""
    return ResidentialRolloverProfile(
        name="Standard Rollover",
        term_months=12,
        renewal_probability=0.65,
        downtime_months=1,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2400.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2300.0)
    )


def test_residential_unit_spec_creation(sample_rollover_profile):
    """Test that ResidentialUnitSpec captures unit type data correctly"""
    unit_spec = ResidentialUnitSpec(
        unit_type_name="1BR/1BA - Garden",
        unit_count=40,
        avg_area_sf=850.0,
        current_avg_monthly_rent=2200.0,
        rollover_profile=sample_rollover_profile
    )
    
    assert unit_spec.unit_type_name == "1BR/1BA - Garden"
    assert unit_spec.unit_count == 40
    assert unit_spec.avg_area_sf == 850.0
    assert unit_spec.current_avg_monthly_rent == 2200.0
    assert unit_spec.rollover_profile == sample_rollover_profile


def test_residential_rent_roll_aggregation():
    """Test that ResidentialRentRoll properly aggregates unit specifications"""
    # Create rollover profiles
    profile_1br = ResidentialRolloverProfile(
        name="1BR Rollover",
        term_months=12,
        renewal_probability=0.65,
        downtime_months=1,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2400.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2300.0)
    )
    
    profile_2br = ResidentialRolloverProfile(
        name="2BR Rollover", 
        term_months=12,
        renewal_probability=0.70,
        downtime_months=1,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=3200.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=3100.0)
    )
    
    # Create unit specifications
    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Garden",
            unit_count=40,
            avg_area_sf=850.0,
            current_avg_monthly_rent=2200.0,
            rollover_profile=profile_1br
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA - Premium",
            unit_count=30,
            avg_area_sf=1200.0,
            current_avg_monthly_rent=2900.0,
            rollover_profile=profile_2br
        )
    ]
    
    rent_roll = ResidentialRentRoll(unit_specs=unit_specs)
    
    # Test aggregation properties
    assert rent_roll.total_unit_count == 70
    assert rent_roll.total_rentable_area == (40 * 850.0) + (30 * 1200.0)
    assert rent_roll.weighted_avg_rent == pytest.approx(2500.0, rel=1e-2)  # Weighted average


def test_rent_roll_computed_properties():
    """Test computed properties work correctly for various scenarios"""
    profile = ResidentialRolloverProfile(
        name="Test Profile",
        term_months=12,
        renewal_probability=0.65,
        downtime_months=1,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2000.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=1950.0)
    )
    
    # Single unit type
    single_spec = ResidentialRentRoll(unit_specs=[
        ResidentialUnitSpec(
            unit_type_name="Studio",
            unit_count=50,
            avg_area_sf=600.0,
            current_avg_monthly_rent=1800.0,
            rollover_profile=profile
        )
    ])
    
    assert single_spec.total_unit_count == 50
    assert single_spec.total_rentable_area == 30000.0  # 50 * 600
    assert single_spec.weighted_avg_rent == 1800.0


# Test Step 1.3: Rollover assumptions and lease terms

def test_residential_rollover_lease_terms():
    """Test that ResidentialRolloverLeaseTerms captures simplified residential logic"""
    market_growth = GrowthRate(name="Market Growth", value=0.04)

    # Test new CapitalPlan-based approach
    terms = ResidentialRolloverLeaseTerms.with_simple_turnover(
        market_rent=2500.0,
        make_ready_cost=1200.0,
        leasing_fee=400.0,
        market_rent_growth=market_growth,
        renewal_rent_increase_percent=0.035,  # 3.5% renewal increase
        concessions_months=1,  # 1 month free
    )

    assert terms.market_rent == 2500.0
    assert terms.market_rent_growth == market_growth
    assert terms.renewal_rent_increase_percent == 0.035
    assert terms.concessions_months == 1
    
    # Test UUID-based CapitalPlan reference (new architecture)
    assert terms.capital_plan_id is not None
    assert isinstance(terms.capital_plan_id, UUID)
    
    # The factory method creates the plan and stores its UUID
    # We can't directly test the plan content since it's not stored on the terms
    # Instead, we validate that the UUID reference is properly set
    assert terms.effective_market_rent == 2500.0  # No renovation premium


def test_residential_rollover_profile_blending():
    """Test that ResidentialRolloverProfile properly blends market vs renewal terms"""
    market_growth = GrowthRate(name="Market Growth", value=0.04)
    
    # Use factory method for market terms with CapitalPlan
    market_terms = ResidentialRolloverLeaseTerms.with_simple_turnover(
        market_rent=2600.0,  # Higher market rent
        make_ready_cost=1500.0,
        leasing_fee=500.0,
        market_rent_growth=market_growth,
    )
    
    # Renewal terms with no turnover costs (UUID-based architecture)
    renewal_terms = ResidentialRolloverLeaseTerms(
        market_rent=2400.0,  # Lower renewal rent (current + increase)
        renewal_rent_increase_percent=0.04,
        capital_plan_id=None  # No costs for renewals
    )
    
    profile = ResidentialRolloverProfile(
        name="Blended Profile",
        term_months=12,
        renewal_probability=0.65,  # 65% renew, 35% turn over
        downtime_months=1,
        market_terms=market_terms,
        renewal_terms=renewal_terms
    )
    
    # Test blending calculation
    blended_terms = profile.blend_lease_terms()
    
    # Expected: (2400 * 0.65) + (2600 * 0.35) = 1560 + 910 = 2470
    expected_blended_rent = (2400.0 * 0.65) + (2600.0 * 0.35)
    assert blended_terms.market_rent == pytest.approx(expected_blended_rent, rel=1e-2)
    
    # With new UUID-based approach, market terms capital_plan_id should be used when both exist
    # Since we have market_terms.capital_plan_id and renewal_terms.capital_plan_id is None,
    # the blended result should use the market terms capital plan ID
    assert blended_terms.capital_plan_id is not None
    assert blended_terms.capital_plan_id == market_terms.capital_plan_id


# Integration test: All components working together

def test_complete_residential_property_creation():
    """Test creating a complete ResidentialProperty with all components"""
    # Create all required components
    market_growth = GrowthRate(name="Market Growth", value=0.04)
    
    market_terms = ResidentialRolloverLeaseTerms.with_simple_turnover(
        market_rent=2500.0,
        make_ready_cost=1500.0,
        leasing_fee=500.0,
        market_rent_growth=market_growth,
    )
    
    renewal_terms = ResidentialRolloverLeaseTerms(
        market_rent=2400.0,
        renewal_rent_increase_percent=0.04,
        capital_plan_id=None  # No costs for renewals (UUID-based architecture)
    )
    
    rollover_profile = ResidentialRolloverProfile(
        name="Standard Rollover",
        term_months=12,
        renewal_probability=0.65,
        downtime_months=1,
        market_terms=market_terms,
        renewal_terms=renewal_terms
    )
    
    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA",
            unit_count=50,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2200.0,
            rollover_profile=rollover_profile
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA", 
            unit_count=30,
            avg_area_sf=1100.0,
            current_avg_monthly_rent=2800.0,
            rollover_profile=rollover_profile
        )
    ]
    
    rent_roll = ResidentialRentRoll(unit_specs=unit_specs)
    
    expenses = ResidentialExpenses()
    
    losses = ResidentialLosses(
        general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),
        collection_loss=ResidentialCollectionLoss(rate=0.01)
    )
    
    # Create the complete property
    # Note: Calculate areas from unit mix data for realistic values
    total_unit_area = rent_roll.total_rentable_area  # 80 * 950 average = 76,000 SF
    efficiency_factor = 0.85  # Typical residential efficiency
    
    property_model = ResidentialProperty(
        name="Sunset Gardens Apartments",
        gross_area=total_unit_area / efficiency_factor,  # ~89,400 SF
        net_rentable_area=total_unit_area,  # 76,000 SF
        unit_mix=rent_roll,
        expenses=expenses,
        losses=losses,
        miscellaneous_income=[]
    )
    
    # Validate the complete property
    assert property_model.name == "Sunset Gardens Apartments"
    assert property_model.property_type == AssetTypeEnum.MULTIFAMILY
    assert property_model.unit_mix.total_unit_count == 80
    assert property_model.expenses == expenses
    assert property_model.losses == losses
    assert len(property_model.miscellaneous_income) == 0
    
    # Test computed properties specific to residential
    assert property_model.unit_count == 80
    assert property_model.weighted_avg_rent == property_model.unit_mix.weighted_avg_rent
    assert property_model.occupancy_rate == 1.0  # Stabilized property
    
    # Test area validation (should pass since we calculated correctly)
    assert property_model.net_rentable_area == property_model.unit_mix.total_rentable_area


# Test Step 1.1+: New vacant units functionality

def test_residential_vacant_unit_creation():
    """Test that ResidentialVacantUnit can be created and computed properties work"""
    rollover_profile = ResidentialRolloverProfile(
        name="Vacant Unit Profile",
        term_months=12,
        renewal_probability=0.0,  # New leases, not renewals
        downtime_months=1,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2200.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2200.0)
    )
    
    vacant_unit = ResidentialVacantUnit(
        unit_type_name="1BR/1BA - Vacant",
        unit_count=5,
        avg_area_sf=750.0,
        market_rent=2100.0,
        rollover_profile=rollover_profile
    )
    
    assert vacant_unit.unit_type_name == "1BR/1BA - Vacant"
    assert vacant_unit.unit_count == 5
    assert vacant_unit.avg_area_sf == 750.0
    assert vacant_unit.market_rent == 2100.0
    assert vacant_unit.total_area == 3750.0  # 5 * 750
    assert vacant_unit.monthly_income_potential == 10500.0  # 5 * 2100


def test_rent_roll_with_vacant_units():
    """Test ResidentialRentRoll with mixed occupied and vacant units"""
    # Create rollover profiles
    rollover_profile = ResidentialRolloverProfile(
        name="Mixed Profile",
        term_months=12,
        renewal_probability=0.65,
        downtime_months=1,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2400.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2300.0)
    )
    
    # Occupied units
    occupied_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Occupied",
            unit_count=20,
            avg_area_sf=700.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA - Occupied",
            unit_count=15,
            avg_area_sf=1000.0,
            current_avg_monthly_rent=2800.0,
            rollover_profile=rollover_profile
        )
    ]
    
    # Vacant units
    vacant_units = [
        ResidentialVacantUnit(
            unit_type_name="1BR/1BA - Vacant",
            unit_count=3,
            avg_area_sf=700.0,
            market_rent=2100.0,
            rollover_profile=rollover_profile
        ),
        ResidentialVacantUnit(
            unit_type_name="2BR/2BA - Vacant",
            unit_count=2,
            avg_area_sf=1000.0,
            market_rent=2900.0,
            rollover_profile=rollover_profile
        )
    ]
    
    rent_roll = ResidentialRentRoll(
        unit_specs=occupied_specs,
        vacant_units=vacant_units
    )
    
    # Test unit counts
    assert rent_roll.occupied_units == 35  # 20 + 15
    assert rent_roll.vacant_unit_count == 5  # 3 + 2
    assert rent_roll.total_unit_count == 40  # 35 + 5
    
    # Test area calculations
    assert rent_roll.occupied_area == 29000.0  # (20*700) + (15*1000)
    assert rent_roll.vacant_area == 4100.0     # (3*700) + (2*1000)
    assert rent_roll.total_rentable_area == 33100.0  # 29000 + 4100
    
    # Test income calculations
    current_income = (20 * 2000) + (15 * 2800)  # 40,000 + 42,000 = 82,000
    vacant_potential = (3 * 2100) + (2 * 2900)  # 6,300 + 5,800 = 12,100
    total_potential = current_income + vacant_potential  # 82,000 + 12,100 = 94,100
    
    assert rent_roll.current_monthly_income == current_income
    assert rent_roll.total_monthly_income_potential == total_potential
    
    # Test occupancy calculation
    assert rent_roll.occupancy_rate == pytest.approx(35/40, rel=1e-6)  # 87.5%
    
    # Test rent calculations
    assert rent_roll.current_average_rent_per_occupied_unit == pytest.approx(current_income/35, rel=1e-6)
    assert rent_roll.average_rent_per_unit == pytest.approx(total_potential/40, rel=1e-6)


def test_property_with_vacant_units():
    """Test ResidentialProperty with vacant units and occupancy calculations"""
    rollover_profile = ResidentialRolloverProfile(
        name="Property Test Profile",
        term_months=12,
        renewal_probability=0.70,
        downtime_months=1,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2200.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2150.0)
    )
    
    # 80% occupied property
    occupied_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Occupied",
            unit_count=40,  # 40 occupied
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile
        )
    ]
    
    vacant_units = [
        ResidentialVacantUnit(
            unit_type_name="1BR/1BA - Vacant",
            unit_count=10,  # 10 vacant
            avg_area_sf=800.0,
            market_rent=2100.0,
            rollover_profile=rollover_profile
        )
    ]
    
    rent_roll = ResidentialRentRoll(
        unit_specs=occupied_specs,
        vacant_units=vacant_units
    )
    
    property_model = ResidentialProperty(
        name="Mixed Occupancy Property",
        gross_area=44000.0,  # 50 * 800 / 0.91 efficiency
        net_rentable_area=40000.0,  # 50 * 800
        unit_mix=rent_roll,
        expenses=ResidentialExpenses(),
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),
            collection_loss=ResidentialCollectionLoss(rate=0.01)
        )
    )
    
    # Test property-level calculations
    assert property_model.unit_count == 50  # 40 + 10
    assert property_model.occupancy_rate == 0.8  # 40/50 = 80%
    assert property_model.weighted_avg_rent == pytest.approx((40*2000 + 10*2100)/50, rel=1e-6)


def test_vacant_units_analysis_integration():
    """Test that vacant units work correctly in analysis scenarios"""
    from performa.analysis import run
    from performa.common.primitives import GlobalSettings, Timeline
    
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
    settings = GlobalSettings()
    
    rollover_profile = ResidentialRolloverProfile(
        name="Analysis Test Profile",
        renewal_probability=0.65,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=2200.0,
            term_months=12
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2200.0,
            term_months=12
        )
    )
    
    # Property with 20 occupied + 5 vacant = 25 total units
    occupied_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Occupied",
            unit_count=20,
            avg_area_sf=750.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile
        )
    ]
    
    vacant_units = [
        ResidentialVacantUnit(
            unit_type_name="1BR/1BA - Vacant",
            unit_count=5,
            avg_area_sf=750.0,
            market_rent=2100.0,
            rollover_profile=rollover_profile
        )
    ]
    
    rent_roll = ResidentialRentRoll(
        unit_specs=occupied_specs,
        vacant_units=vacant_units
    )
    
    property_model = ResidentialProperty(
        name="Analysis Test Property",
        gross_area=20625.0,  # 25 * 750 / 0.91
        net_rentable_area=18750.0,  # 25 * 750
        unit_mix=rent_roll,
        expenses=ResidentialExpenses(),
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.03),
            collection_loss=ResidentialCollectionLoss(rate=0.01)
        )
    )
    
    # Run analysis
    scenario = run(
        model=property_model,
        timeline=timeline,
        settings=settings
    )
    
    # Verify analysis completed successfully
    assert scenario is not None
    assert property_model.occupancy_rate == 0.8  # 20/25 = 80%
    
    # Verify unit mix unrolling works correctly
    orchestrator = scenario._orchestrator
    lease_models = [m for m in orchestrator.models if m.__class__.__name__ == 'ResidentialLease']
    
    # Should have 20 lease models (one per occupied unit)
    # Vacant units are not modeled as leases until they're absorbed
    assert len(lease_models) == 20


def test_edge_cases_with_vacant_units():
    """Test edge cases: 100% vacant, 0% vacant, empty lists"""
    rollover_profile = ResidentialRolloverProfile(
        name="Edge Case Profile",
        term_months=12,
        renewal_probability=0.65,
        downtime_months=1,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2000.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2000.0)
    )
    
    # Test 100% vacant property
    all_vacant_roll = ResidentialRentRoll(
        unit_specs=[],  # No occupied units
        vacant_units=[
            ResidentialVacantUnit(
                unit_type_name="1BR/1BA - All Vacant",
                unit_count=10,
                avg_area_sf=800.0,
                market_rent=2000.0,
                rollover_profile=rollover_profile
            )
        ]
    )
    
    assert all_vacant_roll.occupied_units == 0
    assert all_vacant_roll.vacant_unit_count == 10
    assert all_vacant_roll.total_unit_count == 10
    assert all_vacant_roll.occupancy_rate == 0.0
    assert all_vacant_roll.current_monthly_income == 0.0
    assert all_vacant_roll.total_monthly_income_potential == 20000.0
    
    # Test 100% occupied property (no vacant units) - existing behavior
    all_occupied_roll = ResidentialRentRoll(
        unit_specs=[
            ResidentialUnitSpec(
                unit_type_name="1BR/1BA - All Occupied",
                unit_count=10,
                avg_area_sf=800.0,
                current_avg_monthly_rent=2000.0,
                rollover_profile=rollover_profile
            )
        ],
        vacant_units=[]  # Explicitly empty
    )
    
    assert all_occupied_roll.occupied_units == 10
    assert all_occupied_roll.vacant_unit_count == 0
    assert all_occupied_roll.total_unit_count == 10
    assert all_occupied_roll.occupancy_rate == 1.0
    assert all_occupied_roll.current_monthly_income == 20000.0
    assert all_occupied_roll.total_monthly_income_potential == 20000.0
    
    # Test that attempting to create a completely empty property fails with good error message
    # This is correct business behavior - properties must have at least some units defined
    with pytest.raises(ValueError, match="must have at least one unit specification or vacant unit"):
        empty_roll = ResidentialRentRoll(
            unit_specs=[],
            vacant_units=[]
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 