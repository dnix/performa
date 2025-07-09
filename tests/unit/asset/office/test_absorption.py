"""
This test module provides comprehensive coverage for the office absorption logic
defined in `performa.asset.office.absorption`. The tests are designed to
validate the behavior of the different `PaceStrategy` implementations under
various scenarios, including:

- **Non-Divisible Suites**: Standard scenarios where the absorption plan leases
  entire, pre-defined vacant suites.
- **Divisible Suites**: Scenarios testing the dynamic subdivision of a large,
  divisible suite into smaller leases to meet absorption targets.
- **Mixed Suites**: Scenarios that involve a combination of divisible and
  non-divisible suites to ensure the logic correctly prioritizes and combines
  them.

Fixtures are used to provide common setups for vacant suites (standard, large
divisible, and mixed), analysis timelines, and base leasing terms, ensuring
tests are clean and easy to understand. Each test function is named to clearly
indicate the strategy and scenario it covers.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from performa.asset.office.absorption import (
    CustomSchedulePace,
    DirectLeaseTerms,
    EqualSpreadPace,
    FixedQuantityPace,
    OfficeAbsorptionPlan,
    SpaceFilter,
)
from performa.asset.office.rent_roll import OfficeVacantSuite
from performa.core.primitives import (
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)


@pytest.fixture
def vacant_suites():
    """Provides a list of standard, non-divisible vacant suites."""
    return [
        OfficeVacantSuite(suite="500", floor="5", area=5000, use_type="office"),
        OfficeVacantSuite(suite="400", floor="4", area=4000, use_type="office"),
        OfficeVacantSuite(suite="300", floor="3", area=3000, use_type="office"),
        OfficeVacantSuite(suite="200", floor="2", area=2000, use_type="office"),
        OfficeVacantSuite(suite="100", floor="1", area=1000, use_type="office"),
    ]

@pytest.fixture
def large_divisible_suite():
    """Provides a single large, divisible vacant suite for subdivision tests."""
    return [
        OfficeVacantSuite(
            suite="1000", floor="10", area=100000, use_type="office",
            is_divisible=True,
            subdivision_average_lease_area=10000,
            subdivision_minimum_lease_area=5000,
        )
    ]

@pytest.fixture
def mixed_suites():
    """
    Provides a mix of divisible and non-divisible suites to test hybrid
    scenarios.
    """
    return [
        OfficeVacantSuite(suite="500", floor="5", area=5000, use_type="office"),
        OfficeVacantSuite(suite="400", floor="4", area=4000, use_type="office"),
        OfficeVacantSuite(
            suite="1000", floor="10", area=50000, use_type="office",
            is_divisible=True,
            subdivision_average_lease_area=8000,
            subdivision_minimum_lease_area=4000,
        )
    ]

@pytest.fixture
def base_direct_lease_terms():
    """
    Provides a DirectLeaseTerms object with default non-null values required
    for creating valid `OfficeLeaseSpec` instances during tests.
    """
    return DirectLeaseTerms(
        base_rent_value=50.0,
        base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
        term_months=60,
        upon_expiration=UponExpirationEnum.MARKET,
    )

@pytest.fixture
def analysis_timeline():
    """Provides a standard analysis timeline for all tests."""
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2028, 12, 31))

@pytest.fixture
def mock_lookup_fn():
    # In a real scenario, this would look up a RolloverProfile
    return MagicMock(return_value=None)


# --- FixedQuantityPaceStrategy Tests ---

def test_fixed_quantity_sf_non_divisible(vacant_suites, analysis_timeline, base_direct_lease_terms):
    """
    Tests the Fixed Quantity strategy with a defined SF target.

    Scenario:
        - A list of various-sized, non-divisible suites.
        - A target to absorb 8,000 SF every 3 months.
    Expectation:
        - The strategy should run for multiple periods until all space is absorbed.
        - In the first period, it should perform a greedy pack, leasing the
          5,000 SF and 3,000 SF suites to exactly meet the 8,000 SF target.
        - In the second period, it should lease the remaining 7,000 SF.
    """
    plan = OfficeAbsorptionPlan(
        name="Test Fixed Pace SF",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2024, 1, 1),
        pace=FixedQuantityPace(quantity=8000, unit="SF", frequency_months=3),
        leasing_assumptions=base_direct_lease_terms
    )
    generated_specs = plan.generate_lease_specs(
        available_vacant_suites=vacant_suites,
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date(),
        analysis_end_date=analysis_timeline.end_date.to_timestamp().date(),
    )
    # The logic will now absorb all suites over multiple periods.
    # Total area is 15000. It will absorb 8k, then 7k.
    assert len(generated_specs) == 5
    assert sum(s.area for s in generated_specs) == 15000

    # Check the first period
    period1_specs = [s for s in generated_specs if s.start_date == date(2024, 1, 1)]
    assert len(period1_specs) == 2
    assert sum(s.area for s in period1_specs) == 8000 # 5000 + 3000

    # Check the second period
    period2_specs = [s for s in generated_specs if s.start_date == date(2024, 4, 1)]
    assert len(period2_specs) == 3
    assert sum(s.area for s in period2_specs) == 7000 # 4000 + 2000 + 1000


def test_fixed_quantity_sf_with_subdivision(large_divisible_suite, analysis_timeline, base_direct_lease_terms):
    """
    Tests the Fixed Quantity strategy's ability to subdivide a large suite
    to meet a specific SF target.

    Scenario:
        - A single, large (100k SF) divisible suite.
        - A target to absorb 25,000 SF per period.
    Expectation:
        - In the first period, the strategy should generate three new leases by
          carving out chunks from the divisible suite: two of the average size
          (10k SF) and one of the remaining size (5k SF) to meet the target.
    """
    plan = OfficeAbsorptionPlan(
        name="Test Fixed Pace Subdivision",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2024, 1, 1),
        pace=FixedQuantityPace(quantity=25000, unit="SF", frequency_months=6),
        leasing_assumptions=base_direct_lease_terms
    )
    generated_specs = plan.generate_lease_specs(
        available_vacant_suites=large_divisible_suite,
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date(),
        analysis_end_date=analysis_timeline.end_date.to_timestamp().date(),
    )
    # Should generate 3 leases in the first period: 10k, 10k, 5k to meet 25k target
    period1_specs = [s for s in generated_specs if s.start_date == date(2024, 1, 1)]
    assert len(period1_specs) == 3
    assert sum(s.area for s in period1_specs) == 25000.0
    assert sorted([s.area for s in period1_specs]) == [5000, 10000, 10000]


def test_fixed_quantity_units_with_subdivision(large_divisible_suite, analysis_timeline, base_direct_lease_terms):
    """
    Tests the Fixed Quantity strategy with a "Units" target, forcing it to
    create a specific number of new leases from a divisible suite.

    Scenario:
        - A single, large (100k SF) divisible suite with an average lease
          size of 10,000 SF.
        - A target to absorb 3 "Units" (i.e., create 3 new leases).
    Expectation:
        - The strategy should generate exactly 3 new leases in the first period,
          each with the defined average lease area of 10,000 SF.
    """
    plan = OfficeAbsorptionPlan(
        name="Test Fixed Pace Units Subdivision",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2024, 1, 1),
        pace=FixedQuantityPace(quantity=3, unit="Units", frequency_months=1),
        leasing_assumptions=base_direct_lease_terms
    )
    generated_specs = plan.generate_lease_specs(
        available_vacant_suites=large_divisible_suite,
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date(),
        analysis_end_date=analysis_timeline.end_date.to_timestamp().date(),
    )
    # Should create 3 leases of the average size (10,000 SF) in the first period
    period1_specs = [s for s in generated_specs if s.start_date == date(2024, 1, 1)]
    assert len(period1_specs) == 3
    assert sum(s.area for s in period1_specs) == 30000.0
    assert all(s.area == 10000 for s in period1_specs)


# --- EqualSpreadPaceStrategy Tests ---

def test_equal_spread_non_divisible(vacant_suites, analysis_timeline, base_direct_lease_terms):
    """
    Tests the Equal Spread strategy with only non-divisible suites.

    Scenario:
        - Total vacant area is 15,000 SF, to be leased over 3 deals.
        - Target per deal is therefore 5,000 SF.
    Expectation:
        - The strategy performs a greedy pack for each deal.
        - Deal 1: Leases the 5,000 SF suite.
        - Deal 2: Leases the 4,000 SF and 1,000 SF suites.
        - Deal 3: Leases the 3,000 SF and 2,000 SF suites.
    """
    plan = OfficeAbsorptionPlan(
        name="Test Equal Spread",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2024, 1, 1),
        pace=EqualSpreadPace(total_deals=3, frequency_months=4),
        leasing_assumptions=base_direct_lease_terms
    )
    # Total area = 15,000 SF. Target per deal = 5,000 SF.
    generated_specs = plan.generate_lease_specs(
        available_vacant_suites=vacant_suites,
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date(),
        analysis_end_date=analysis_timeline.end_date.to_timestamp().date(),
    )
    # Total leased area should be the full 15,000 SF
    assert sum(s.area for s in generated_specs) == 15000

    # Deal 1: Leases 5000 SF suite
    deal1_specs = [s for s in generated_specs if s.start_date == date(2024, 1, 1)]
    assert len(deal1_specs) == 1
    assert sum(s.area for s in deal1_specs) == 5000

    # Deal 2: Leases 4000 SF suite, then tops off with 1000 SF from another suite
    deal2_specs = [s for s in generated_specs if s.start_date == date(2024, 5, 1)]
    assert len(deal2_specs) == 2
    assert sum(s.area for s in deal2_specs) == 5000
    
    # Deal 3: Leases 3000 SF suite, then 2000 SF suite
    deal3_specs = [s for s in generated_specs if s.start_date == date(2024, 9, 1)]
    assert len(deal3_specs) == 2
    assert sum(s.area for s in deal3_specs) == 5000


def test_equal_spread_with_subdivision_top_off(mixed_suites, analysis_timeline, base_direct_lease_terms):
    """
    Tests the Equal Spread strategy's ability to use a divisible suite to
    "top off" a deal to meet its target area.

    Scenario:
        - A mix of non-divisible suites and one large divisible suite.
        - Total area of 59,000 SF to be leased over 3 deals.
        - Target per deal is ~19,667 SF.
    Expectation:
        - All 59,000 SF should be leased in total.
        - The first deal should lease the two non-divisible suites (5k + 4k = 9k SF)
          and then create a new subdivided lease of ~10,667 SF to meet the
          deal's target.
    """
    plan = OfficeAbsorptionPlan(
        name="Test Equal Spread Top Off",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2024, 1, 1),
        pace=EqualSpreadPace(total_deals=3, frequency_months=2),
        leasing_assumptions=base_direct_lease_terms
    )
    # Total area = 59,000 SF. Target per deal = 19,666.67 SF
    generated_specs = plan.generate_lease_specs(
        available_vacant_suites=mixed_suites,
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date(),
        analysis_end_date=analysis_timeline.end_date.to_timestamp().date(),
    )
    total_leased_area = sum(s.area for s in generated_specs)
    
    # We expect all 59,000 SF to be leased.
    assert round(total_leased_area) == 59000

    # Check first deal specifically
    deal1_specs = [s for s in generated_specs if s.start_date == date(2024, 1, 1)]
    assert len(deal1_specs) == 3 # 5k suite, 4k suite, and one subdivided
    assert round(sum(s.area for s in deal1_specs)) == round(59000 / 3)


# --- CustomSchedulePaceStrategy Tests ---

def test_custom_schedule_pace_with_subdivision(mixed_suites, analysis_timeline, base_direct_lease_terms):
    """
    Tests the Custom Schedule strategy with a mix of suite types, forcing
    both whole-suite leasing and subdivision.

    Scenario:
        - A schedule with two absorption dates:
          1. June 1, 2024: Absorb 15,000 SF.
          2. Jan 1, 2025: Absorb 44,000 SF.
    Expectation:
        - All 59,000 SF of vacant space is eventually leased.
        - On the first date, the two non-divisible suites (5k + 4k) are
          leased, and a third lease is created by subdividing 6k SF from the
          divisible suite to meet the 15k target.
        - On the second date, the remaining 44k SF of the divisible suite is
          leased.
    """
    plan = OfficeAbsorptionPlan(
        name="Test Custom Schedule",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2024, 1, 1),
        pace=CustomSchedulePace(schedule={date(2024, 6, 1): 15000, date(2025, 1, 1): 44000}),
        leasing_assumptions=base_direct_lease_terms
    )
    generated_specs = plan.generate_lease_specs(
        available_vacant_suites=mixed_suites,
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date(),
        analysis_end_date=analysis_timeline.end_date.to_timestamp().date(),
    )
    # Period 1 (15k target): Leases 5k, 4k, and subdivides 6k from divisible suite.
    # Period 2 (44k target): Leases the remaining 44k from the divisible suite.
    assert round(sum(s.area for s in generated_specs)) == 59000

    period1_specs = [s for s in generated_specs if s.start_date == date(2024, 6, 1)]
    assert len(period1_specs) == 3
    assert sum(s.area for s in period1_specs) == 15000

    period2_specs = [s for s in generated_specs if s.start_date == date(2025, 1, 1)]
    assert len(period2_specs) > 0
    assert round(sum(s.area for s in period2_specs)) == 44000


# --- Edge Case Tests ---

def test_absorption_target_exceeds_vacant(vacant_suites, analysis_timeline, base_direct_lease_terms):
    """
    Tests that if the absorption target (`quantity`) is larger than the total
    available vacant space, the plan leases everything available and stops
    gracefully without error.

    Scenario:
        - Total vacant area is 15,000 SF.
        - The absorption plan targets 20,000 SF in a single period.
    Expectation:
        - The plan should generate specs for all 5 vacant suites, totaling
          15,000 SF of leased area.
        - It should not error or create more leases than there is space.
    """
    plan = OfficeAbsorptionPlan(
        name="Test Exceeds Vacant",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2024, 1, 1),
        pace=FixedQuantityPace(quantity=20000, unit="SF", frequency_months=3),
        leasing_assumptions=base_direct_lease_terms
    )
    generated_specs = plan.generate_lease_specs(
        available_vacant_suites=vacant_suites,
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date(),
        analysis_end_date=analysis_timeline.end_date.to_timestamp().date(),
    )
    
    total_vacant_area = sum(s.area for s in vacant_suites)
    total_leased_area = sum(s.area for s in generated_specs)

    # Should lease all available space, but no more
    assert total_leased_area == total_vacant_area
    assert len(generated_specs) == len(vacant_suites)


def test_absorption_schedule_exceeds_analysis(vacant_suites, analysis_timeline, base_direct_lease_terms):
    """
    Tests that a CustomSchedulePace only generates leases for dates that
    fall within the analysis timeline.

    Scenario:
        - Analysis timeline ends on Dec 31, 2028.
        - The absorption schedule includes a date after the end (Jan 1, 2029).
    Expectation:
        - Leases should be generated for the date within the timeline.
        - The lease scheduled for after the analysis end date should be ignored.
    """
    schedule = {
        date(2025, 1, 1): 5000,  # This one should be created
        date(2029, 1, 1): 4000,  # This one should be ignored
    }
    plan = OfficeAbsorptionPlan(
        name="Test Schedule Exceeds Analysis",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2024, 1, 1),
        pace=CustomSchedulePace(schedule=schedule),
        leasing_assumptions=base_direct_lease_terms
    )
    generated_specs = plan.generate_lease_specs(
        available_vacant_suites=vacant_suites,
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date(),
        analysis_end_date=analysis_timeline.end_date.to_timestamp().date(),
    )
    
    # Only one lease spec should have been generated
    assert len(generated_specs) == 1
    assert generated_specs[0].area == 5000
    assert generated_specs[0].start_date == date(2025, 1, 1)


def test_absorption_indivisible_suite_too_large(vacant_suites, analysis_timeline, base_direct_lease_terms):
    """
    Tests that if the target area for an EqualSpreadPace deal is smaller
    than the smallest available non-divisible suite, the plan does not
    lease anything in that period and moves on.

    Scenario:
        - Total vacant area is 15,000 SF.
        - Smallest suite is 1,000 SF.
        - Plan is for 20 deals, making the target per deal 750 SF.
    Expectation:
        - Since 750 SF is smaller than any available suite and there are
          no divisible suites, no leases should be generated at all.
    """
    plan = OfficeAbsorptionPlan(
        name="Test Indivisible Too Large",
        space_filter=SpaceFilter(),
        start_date_anchor=date(2024, 1, 1),
        pace=EqualSpreadPace(total_deals=20, frequency_months=1),
        leasing_assumptions=base_direct_lease_terms
    )
    generated_specs = plan.generate_lease_specs(
        available_vacant_suites=vacant_suites,
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date(),
        analysis_end_date=analysis_timeline.end_date.to_timestamp().date(),
    )
    
    assert len(generated_specs) == 0
