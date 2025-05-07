"""Tests for absorption modeling functionality."""

from datetime import date
from typing import Optional  # Import necessary types

import pytest

# Import necessary models from performa.asset
from performa.asset._absorption import (
    CustomSchedulePace,
    CustomSchedulePaceStrategy,
    DirectLeaseTerms,
    EqualSpreadPace,
    EqualSpreadPaceStrategy,
    FixedQuantityPace,
    FixedQuantityPaceStrategy,
    PaceContext,  # Import BasePace for strategy type hints
)
from performa.asset._lease import LeaseSpec
from performa.asset._rent_roll import VacantSuite
from performa.asset._rollover import RolloverLeaseTerms, RolloverProfile
from performa.core._enums import (
    LeaseTypeEnum,
    ProgramUseEnum,
    StartDateAnchorEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from performa.core._settings import GlobalSettings
from performa.core.absorption_plan import AbsorptionPlan
from performa.core.space_filter import SpaceFilter

# Placeholder for test fixtures (e.g., common vacant suites, profiles)

# TODO: Add fixtures for VacantSuite lists
# TODO: Add fixtures for RolloverProfile / RolloverLeaseTerms
# TODO: Add fixtures for GlobalSettings

def create_mock_lookup_fn(profile_map: dict):
    """Creates a simple mock lookup function for testing."""
    def mock_lookup(identifier):
        if identifier in profile_map:
            return profile_map[identifier]
        raise LookupError(f"Identifier '{identifier}' not found in mock map.")
    return mock_lookup

# --- Mock Data & Fixtures --- #

@pytest.fixture
def vacant_suites_basic():
    """Provides a basic list of vacant suites."""
    return [
        VacantSuite(suite="101", floor="1", area=12000, use_type=ProgramUseEnum.OFFICE),
        VacantSuite(suite="102", floor="1", area=8000, use_type=ProgramUseEnum.OFFICE),
        VacantSuite(suite="201", floor="2", area=5000, use_type=ProgramUseEnum.OFFICE),
        VacantSuite(suite="202", floor="2", area=7000, use_type=ProgramUseEnum.OFFICE),
    ]

@pytest.fixture
def direct_terms_simple():
    """Provides simple DirectLeaseTerms."""
    return DirectLeaseTerms(
        term_months=60,
        base_rent_value=25.00,
        base_rent_unit_of_measure=UnitOfMeasureEnum.PSF,
        upon_expiration=UponExpirationEnum.MARKET,
    )

@pytest.fixture
def global_settings_default():
    """Provides default GlobalSettings."""
    return GlobalSettings()

# Simplified mock create_spec function for strategy testing
def mock_create_lease_spec(
    suite: VacantSuite,
    start_date: date,
    profile_market_terms: Optional[RolloverLeaseTerms],
    direct_terms: Optional[DirectLeaseTerms],
    deal_number: int,
    global_settings: Optional[GlobalSettings]
) -> Optional[LeaseSpec]:
    """Mocks the _create_lease_spec helper for strategy tests."""
    # Use terms primarily from direct_terms if available for simplicity in this mock
    terms_to_use = direct_terms or (profile_market_terms if profile_market_terms else DirectLeaseTerms(term_months=60, base_rent_value=10.0, upon_expiration=UponExpirationEnum.MARKET))

    try:
        return LeaseSpec(
             tenant_name=f"Absorption-Deal{deal_number}-{suite.suite}",
             suite=suite.suite,
             floor=suite.floor,
             area=suite.area,
             use_type=suite.use_type,
             lease_type=LeaseTypeEnum.OFFICE, # Assume office for mock
             start_date=start_date,
             term_months=terms_to_use.term_months,
             base_rent_value=terms_to_use.base_rent_value or 10.0,
             base_rent_unit_of_measure=terms_to_use.base_rent_unit_of_measure or UnitOfMeasureEnum.PSF,
             upon_expiration=terms_to_use.upon_expiration or UponExpirationEnum.MARKET,
             # Keep other components None for strategy testing simplicity
             rent_escalation=None,
             rent_abatement=None,
             recovery_method=None,
             ti_allowance=None,
             leasing_commission=None,
             rollover_profile_ref=None,
             source="AbsorptionPlan"
        )
    except Exception as e:
        print(f"Mock create spec error: {e}")
        return None

# --- Tests for Pace Strategies --- #

# Remove skip marker
def test_fixed_quantity_pace_strategy_sf(vacant_suites_basic, direct_terms_simple, global_settings_default):
    """Test FixedQuantityPaceStrategy with SF unit and monthly frequency."""
    # Arrange
    analysis_start = date(2025, 1, 1)
    analysis_end = date(2026, 12, 31)
    
    # Target: Absorb 15,000 SF per month
    pace_model = FixedQuantityPace(quantity=15000, unit="SF", frequency_months=1)
    strategy = FixedQuantityPaceStrategy()
    
    # Initial suites sorted by area desc: 101(12k), 102(8k), 202(7k), 201(5k)
    context = PaceContext(
        plan_name="TestPlan",
        remaining_suites=vacant_suites_basic.copy(), # Pass a copy
        initial_start_date=analysis_start,
        analysis_end_date=analysis_end,
        market_lease_terms=None, # Using direct terms for this test
        direct_terms=direct_terms_simple,
        global_settings=global_settings_default,
        create_spec_fn=mock_create_lease_spec, 
        total_target_area=sum(s.area for s in vacant_suites_basic)
    )

    # Act
    generated_specs = strategy.generate(pace_model, context)

    # Assert
    # Expected behavior:
    # Month 1 (Jan 25): Target 15k. Leases 101 (12k). Remaining target 3k. Cannot lease 102 (8k). Total: 1 spec (12k SF)
    # Month 2 (Feb 25): Target 15k. Leases 102 (8k). Remaining target 7k. Leases 202 (7k). Total: 2 specs (15k SF)
    # Month 3 (Mar 25): Target 15k. Leases 201 (5k). No more suites. Total: 1 spec (5k SF)
    # Total: 4 specs
    assert len(generated_specs) == 4

    total_absorbed_area = sum(spec.area for spec in generated_specs)
    assert total_absorbed_area == pytest.approx(12000 + 8000 + 7000 + 5000)

    # Check start dates
    assert generated_specs[0].start_date == date(2025, 1, 1)
    assert generated_specs[0].suite == "101"

    assert generated_specs[1].start_date == date(2025, 2, 1)
    assert generated_specs[1].suite == "102"
    assert generated_specs[2].start_date == date(2025, 2, 1)
    assert generated_specs[2].suite == "202"

    assert generated_specs[3].start_date == date(2025, 3, 1)
    assert generated_specs[3].suite == "201"

    # Check source
    for spec in generated_specs:
        assert spec.source == "AbsorptionPlan"

# Remove skip marker
def test_fixed_quantity_pace_strategy_units(vacant_suites_basic, direct_terms_simple, global_settings_default):
    """Test FixedQuantityPaceStrategy with Units unit and quarterly frequency."""
    # Arrange
    analysis_start = date(2025, 1, 1)
    analysis_end = date(2026, 12, 31)

    # Target: Absorb 2 Units per Quarter (3 months)
    pace_model = FixedQuantityPace(quantity=2, unit="Units", frequency_months=3)
    strategy = FixedQuantityPaceStrategy()

    # Initial suites sorted by area desc: 101(12k), 102(8k), 202(7k), 201(5k)
    context = PaceContext(
        plan_name="TestPlanUnits",
        remaining_suites=vacant_suites_basic.copy(),
        initial_start_date=analysis_start,
        analysis_end_date=analysis_end,
        market_lease_terms=None,
        direct_terms=direct_terms_simple,
        global_settings=global_settings_default,
        create_spec_fn=mock_create_lease_spec,
        total_target_area=sum(s.area for s in vacant_suites_basic)
    )

    # Act
    generated_specs = strategy.generate(pace_model, context)

    # Assert
    # Expected behavior:
    # Quarter 1 (Start Jan 1 2025): Target 2 units. Leases 101, 102.
    # Quarter 2 (Start Apr 1 2025): Target 2 units. Leases 202, 201.
    # Total: 4 specs (all suites leased)
    assert len(generated_specs) == 4

    total_absorbed_area = sum(spec.area for spec in generated_specs)
    assert total_absorbed_area == pytest.approx(sum(s.area for s in vacant_suites_basic))

    # Check start dates and suites
    # Q1
    assert generated_specs[0].start_date == date(2025, 1, 1)
    assert generated_specs[0].suite == "101"
    assert generated_specs[1].start_date == date(2025, 1, 1)
    assert generated_specs[1].suite == "102"

    # Q2 (starts 3 months after Q1 start)
    assert generated_specs[2].start_date == date(2025, 4, 1)
    assert generated_specs[2].suite == "202"
    assert generated_specs[3].start_date == date(2025, 4, 1)
    assert generated_specs[3].suite == "201"

    # Check source
    for spec in generated_specs:
        assert spec.source == "AbsorptionPlan"

# Remove skip marker
def test_equal_spread_pace_strategy(vacant_suites_basic, direct_terms_simple, global_settings_default):
    """Test EqualSpreadPaceStrategy spreading area over deals."""
    # Arrange
    analysis_start = date(2025, 1, 1)
    analysis_end = date(2026, 12, 31)
    total_area_input = sum(s.area for s in vacant_suites_basic) # 12k+8k+5k+7k = 32k

    # Target: Spread 32k SF over 3 deals, starting monthly
    # Target per deal = 32000 / 3 = 10666.67 SF
    pace_model = EqualSpreadPace(total_deals=3, frequency_months=1)
    strategy = EqualSpreadPaceStrategy()

    context = PaceContext(
        plan_name="TestSpreadPlan",
        remaining_suites=vacant_suites_basic.copy(),
        initial_start_date=analysis_start,
        analysis_end_date=analysis_end,
        market_lease_terms=None,
        direct_terms=direct_terms_simple,
        global_settings=global_settings_default,
        create_spec_fn=mock_create_lease_spec,
        total_target_area=total_area_input
    )

    # Act
    generated_specs = strategy.generate(pace_model, context)

    # Assert
    # Expected behavior (Suites: 12k, 8k, 7k, 5k)
    # Deal 1 (Jan 25): Target 10.67k. Leases 101 (12k). Exceeds target, stops. Specs: [101]
    # Deal 2 (Feb 25): Target 10.67k. Leases 102 (8k). Remaining target 2.67k. Leases 202 (7k). Exceeds. Specs: [102, 202]
    # Deal 3 (Mar 25): Target 10.67k. Leases 201 (5k). No more suites. Specs: [201]
    # Total: 4 specs
    assert len(generated_specs) == 4

    total_absorbed_area = sum(spec.area for spec in generated_specs)
    assert total_absorbed_area == pytest.approx(total_area_input)

    # Check start dates and suites
    # Deal 1
    assert generated_specs[0].start_date == date(2025, 1, 1)
    assert generated_specs[0].suite == "101"

    # Deal 2
    assert generated_specs[1].start_date == date(2025, 2, 1)
    assert generated_specs[1].suite == "102"
    assert generated_specs[2].start_date == date(2025, 2, 1)
    assert generated_specs[2].suite == "202"

    # Deal 3
    assert generated_specs[3].start_date == date(2025, 3, 1)
    assert generated_specs[3].suite == "201"

    # Check source
    for spec in generated_specs:
        assert spec.source == "AbsorptionPlan"

# Remove skip marker
def test_custom_schedule_pace_strategy(vacant_suites_basic, direct_terms_simple, global_settings_default):
    """Test CustomSchedulePaceStrategy."""
    # Arrange
    analysis_start = date(2025, 1, 1)
    analysis_end = date(2026, 12, 31)
    total_area_input = sum(s.area for s in vacant_suites_basic) # 32k

    # Target: Absorb 10k on 2025-03-01, 15k on 2025-06-01, 10k on 2025-09-01
    schedule = {
        date(2025, 3, 1): 10000,
        date(2025, 6, 1): 15000,
        date(2025, 9, 1): 10000, # Should absorb remaining 7k
    }
    pace_model = CustomSchedulePace(schedule=schedule)
    strategy = CustomSchedulePaceStrategy()

    context = PaceContext(
        plan_name="TestCustomSchedulePlan",
        remaining_suites=vacant_suites_basic.copy(),
        initial_start_date=analysis_start, # Not directly used by this strategy
        analysis_end_date=analysis_end,
        market_lease_terms=None,
        direct_terms=direct_terms_simple,
        global_settings=global_settings_default,
        create_spec_fn=mock_create_lease_spec,
        total_target_area=total_area_input
    )

    # Act
    generated_specs = strategy.generate(pace_model, context)

    # Assert
    # Expected behavior (Suites: 12k, 8k, 7k, 5k)
    # Date 2025-03-01: Target 10k. Leases 101 (12k). Exceeds target. Specs: [101]
    # Date 2025-06-01: Target 15k. Leases 102 (8k). Leases 202 (7k). Total 15k. Specs: [102, 202]
    # Date 2025-09-01: Target 10k. Leases 201 (5k). No more suites. Specs: [201]
    # Total: 4 specs
    assert len(generated_specs) == 4

    total_absorbed_area = sum(spec.area for spec in generated_specs)
    assert total_absorbed_area == pytest.approx(total_area_input)

    # Check start dates and suites
    # Date 1
    assert generated_specs[0].start_date == date(2025, 3, 1)
    assert generated_specs[0].suite == "101"

    # Date 2
    assert generated_specs[1].start_date == date(2025, 6, 1)
    assert generated_specs[1].suite == "102"
    assert generated_specs[2].start_date == date(2025, 6, 1)
    assert generated_specs[2].suite == "202"

    # Date 3
    assert generated_specs[3].start_date == date(2025, 9, 1)
    assert generated_specs[3].suite == "201"

    # Check source
    for spec in generated_specs:
        assert spec.source == "AbsorptionPlan"

# --- Tests for AbsorptionPlan.generate_lease_specs (Orchestration) --- #

# Remove skip marker
def test_generate_lease_specs_filtering(direct_terms_simple, global_settings_default):
    """Test that space_filter correctly selects suites."""
    # Arrange
    analysis_start = date(2025, 1, 1)
    analysis_end = date(2025, 12, 31)
    
    # Suites with different use types
    vacant_suites = [
        VacantSuite(suite='101', floor="1", area=1000, use_type=ProgramUseEnum.OFFICE),
        VacantSuite(suite='201', floor="2", area=2000, use_type=ProgramUseEnum.RETAIL),
        VacantSuite(suite='301', floor="3", area=1500, use_type=ProgramUseEnum.OFFICE),
    ]
    total_area_input = sum(s.area for s in vacant_suites)

    # Filter to only target OFFICE suites
    space_filter = SpaceFilter(use_types=[ProgramUseEnum.OFFICE])
    
    # Use a simple pace that should absorb all targeted space quickly
    pace_model = FixedQuantityPace(quantity=10000, unit="SF", frequency_months=1)
    
    # Create the plan
    absorption_plan = AbsorptionPlan(
        name="FilterTestPlan",
        space_filter=space_filter,
        start_date_anchor=analysis_start, # Use date directly
        pace=pace_model,
        leasing_assumptions=direct_terms_simple # Use simple direct terms
    )
    
    # Act
    # Note: generate_lease_specs handles sorting internally (largest first)
    # Filtered office suites: 301 (1.5k), 101 (1k)
    generated_specs = absorption_plan.generate_lease_specs(
        available_vacant_suites=vacant_suites, 
        analysis_start_date=analysis_start,
        analysis_end_date=analysis_end,
        lookup_fn=None, # Not needed for direct terms
        global_settings=global_settings_default
    )
    
    # Assert
    # Expected: Only the two OFFICE suites (101, 301) should be leased.
    # The strategy should lease both in the first month (target 10k SF >> 2.5k SF)
    assert len(generated_specs) == 2
    leased_suite_ids = {spec.suite for spec in generated_specs}
    assert leased_suite_ids == {'101', '301'}
    
    total_absorbed_area = sum(spec.area for spec in generated_specs)
    assert total_absorbed_area == pytest.approx(1000 + 1500)
    
    # Check start dates (should both be the first period)
    assert generated_specs[0].start_date == analysis_start
    assert generated_specs[1].start_date == analysis_start

# Remove skip marker
def test_generate_lease_specs_term_resolution_profile(vacant_suites_basic, global_settings_default):
    """Test resolving terms using a RolloverProfileIdentifier."""
    # Arrange
    analysis_start = date(2025, 1, 1)
    analysis_end = date(2025, 12, 31)

    # Create a mock RolloverProfile with distinct market terms
    # Assume RLA has a simple _calculate_rent for testing
    class MockRLT(RolloverLeaseTerms):
        def _calculate_rent(self, term_config, rollover_date, global_settings):
             return 35.50 # Mock calculated rent

    mock_market_terms = MockRLT(
        term_months=72,
        base_rent_value=None, # Rent is calculated
        unit_of_measure=UnitOfMeasureEnum.PSF,
        upon_expiration=UponExpirationEnum.RENEW # Example
    )
    mock_profile = RolloverProfile(
        name='TestMarketProf',
        term_months=72, # Matches market terms
        renewal_probability=0.0,
        downtime_months=0,
        market_terms=mock_market_terms,
        renewal_terms=mock_market_terms, # Dummy
        option_terms=mock_market_terms   # Dummy
    )
    profile_id = "TestMarketProfileID"
    lookup = create_mock_lookup_fn({profile_id: mock_profile})

    # Use a simple pace
    pace_model = FixedQuantityPace(quantity=1, unit="Units", frequency_months=1)

    # Plan referencing the profile ID
    absorption_plan = AbsorptionPlan(
        name="ProfileTermPlan",
        space_filter=SpaceFilter(), # No filter, target all
        start_date_anchor=analysis_start,
        pace=pace_model,
        leasing_assumptions=profile_id # Reference by ID
    )

    # Act
    # Target 1 unit per month
    generated_specs = absorption_plan.generate_lease_specs(
        available_vacant_suites=vacant_suites_basic.copy(), # Use basic set
        analysis_start_date=analysis_start,
        analysis_end_date=analysis_end,
        lookup_fn=lookup,
        global_settings=global_settings_default
    )

    # Assert
    assert len(generated_specs) > 0 # Should generate at least one spec
    first_spec = generated_specs[0]

    # Check that terms from the profile's market_terms were applied
    assert first_spec.term_months == mock_market_terms.term_months # 72
    assert first_spec.base_rent_value == pytest.approx(35.50) # From mock calc
    assert first_spec.base_rent_unit_of_measure == mock_market_terms.unit_of_measure
    # assert first_spec.upon_expiration == mock_market_terms.upon_expiration # upon_expiration taken from override or default
    assert first_spec.upon_expiration == UponExpirationEnum.MARKET # Check default applied correctly when profile doesn't override

# Remove skip marker
def test_generate_lease_specs_term_resolution_direct(vacant_suites_basic, global_settings_default):
    """Test resolving terms using DirectLeaseTerms."""
    # Arrange
    analysis_start = date(2025, 1, 1)
    analysis_end = date(2025, 12, 31)

    # Define direct terms with specific overrides
    direct_terms = DirectLeaseTerms(
        term_months=48,
        base_rent_value=30.0, # Directly specified
        base_rent_unit_of_measure=UnitOfMeasureEnum.PSF,
        upon_expiration=UponExpirationEnum.RENEW # Override default
    )

    # Use a simple pace
    pace_model = FixedQuantityPace(quantity=1, unit="Units", frequency_months=1)

    # Plan using direct terms
    absorption_plan = AbsorptionPlan(
        name="DirectTermPlan",
        space_filter=SpaceFilter(),
        start_date_anchor=analysis_start,
        pace=pace_model,
        leasing_assumptions=direct_terms # Pass direct terms object
    )

    # Act
    generated_specs = absorption_plan.generate_lease_specs(
        available_vacant_suites=vacant_suites_basic.copy(),
        analysis_start_date=analysis_start,
        analysis_end_date=analysis_end,
        lookup_fn=None, # Not needed for direct terms
        global_settings=global_settings_default
    )

    # Assert
    assert len(generated_specs) > 0
    first_spec = generated_specs[0]

    # Check that terms from DirectLeaseTerms were applied
    assert first_spec.term_months == 48
    assert first_spec.base_rent_value == pytest.approx(30.0)
    assert first_spec.base_rent_unit_of_measure == UnitOfMeasureEnum.PSF
    assert first_spec.upon_expiration == UponExpirationEnum.RENEW

# Remove skip marker
def test_generate_lease_specs_start_date_anchor(vacant_suites_basic, direct_terms_simple, global_settings_default):
    """Test different start date anchors."""
    analysis_start = date(2025, 1, 15)
    analysis_end = date(2025, 12, 31)
    fixed_anchor_date = date(2025, 7, 1)

    # Use a simple pace
    pace_model = FixedQuantityPace(quantity=1, unit="Units", frequency_months=1)

    # --- Test Case 1: ANALYSIS_START --- #
    plan_anchor_start = AbsorptionPlan(
        name="AnchorStartPlan",
        space_filter=SpaceFilter(),
        start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
        pace=pace_model,
        leasing_assumptions=direct_terms_simple
    )
    specs_anchor_start = plan_anchor_start.generate_lease_specs(
        available_vacant_suites=vacant_suites_basic.copy(),
        analysis_start_date=analysis_start,
        analysis_end_date=analysis_end,
        lookup_fn=None,
        global_settings=global_settings_default
    )
    assert len(specs_anchor_start) > 0
    # First lease should start on the analysis_start date
    assert specs_anchor_start[0].start_date == analysis_start

    # --- Test Case 2: Fixed Date --- #
    plan_fixed_date = AbsorptionPlan(
        name="FixedDatePlan",
        space_filter=SpaceFilter(),
        start_date_anchor=fixed_anchor_date,
        pace=pace_model,
        leasing_assumptions=direct_terms_simple
    )
    specs_fixed_date = plan_fixed_date.generate_lease_specs(
        available_vacant_suites=vacant_suites_basic.copy(),
        analysis_start_date=analysis_start,
        analysis_end_date=analysis_end,
        lookup_fn=None,
        global_settings=global_settings_default
    )
    assert len(specs_fixed_date) > 0
    # First lease should start on the specified fixed_anchor_date
    assert specs_fixed_date[0].start_date == fixed_anchor_date

# --- Tests for _create_lease_spec (Helper Method) --- #

# Remove skip marker
def test_create_lease_spec_prioritization(global_settings_default):
    """Test that DirectLeaseTerms override RolloverProfile market terms in _create_lease_spec."""
    # Arrange
    suite = VacantSuite(suite='101', floor="1", area=5000, use_type=ProgramUseEnum.OFFICE)
    start_date = date(2025, 1, 1)

    # Define profile terms (market terms)
    class MockRLTWithRent(RolloverLeaseTerms):
        # Mock method needed for fallback rent calculation
        def _calculate_rent(self, term_config, rollover_date, global_settings):
            return 30.0 # Profile rent
    profile_terms = MockRLTWithRent(
        term_months=60,
        base_rent_value=None,
        unit_of_measure=UnitOfMeasureEnum.PSF,
        upon_expiration=UponExpirationEnum.MARKET
    )

    # Define direct terms overriding only term_months and upon_expiration
    direct_terms = DirectLeaseTerms(
        term_months=48,
        upon_expiration=UponExpirationEnum.RENEW
        # base_rent_value is None, should fallback to profile calculation
    )

    # Need an instance of AbsorptionPlan to call the method (even if plan fields aren't used directly)
    # Pass dummy values for unused fields in this specific test context
    plan = AbsorptionPlan(
        name="HelperTestPlan",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2025,1,1),
        pace=FixedQuantityPace(quantity=1, unit="Units"), # Dummy pace
        leasing_assumptions=direct_terms # Doesn't matter for calling _create_lease_spec directly
    )

    # Act
    # Call the helper method directly
    spec = plan._create_lease_spec(
        suite=suite,
        start_date=start_date,
        profile_market_terms=profile_terms,
        direct_terms=direct_terms,
        deal_number=1,
        global_settings=global_settings_default
    )

    # Assert
    assert spec is not None
    # Check override fields
    assert spec.term_months == 48 # From direct_terms
    assert spec.upon_expiration == UponExpirationEnum.RENEW # From direct_terms
    # Check fallback fields
    assert spec.base_rent_value == pytest.approx(30.0) # Calculated from profile_terms
    assert spec.base_rent_unit_of_measure == UnitOfMeasureEnum.PSF # From profile_terms
    assert spec.source == "AbsorptionPlan"

# TODO: Add tests for edge cases (no suites, empty schedule, dates outside analysis, etc.) 