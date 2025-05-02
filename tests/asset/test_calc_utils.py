from datetime import date
from uuid import UUID

import pandas as pd
import pytest

# Import the utility functions to test
from performa.asset._calc_utils import (
    _get_period_expenses,
    _get_period_occupancy,
    _gross_up_period_expenses,
)
from performa.asset._expense import (
    CapitalExpenses,
    Expenses,
    OperatingExpenses,
    OpExItem,
)

# Import necessary models for creating fixtures
from performa.asset._property import Property
from performa.asset._revenue import Lease, RentRoll, Tenant
from performa.core._enums import (
    FrequencyEnum,
    LeaseTypeEnum,
    ProgramUseEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from performa.core._timeline import Timeline

# --- Fixtures --- 

@pytest.fixture
def sample_property_fixture() -> Property:
    """Provides a basic Property object with a simple rent roll."""
    lease1_start = date(2023, 1, 1)
    lease1_end = date(2024, 12, 31)
    lease2_start = date(2023, 7, 1)
    lease2_end = date(2024, 6, 30)
    
    tenant1 = Tenant(id="T1", name="Tenant 1")
    tenant2 = Tenant(id="T2", name="Tenant 2")

    lease1 = Lease(
        name="Lease 1",
        tenant=tenant1,
        suite="101",
        floor="1",
        use_type=ProgramUseEnum.OFFICE,
        lease_type=LeaseTypeEnum.NNN,
        area=1000,
        timeline=Timeline.from_dates(lease1_start, lease1_end),
        value=20.0, # Assume $/SF/Year
        unit_of_measure=UnitOfMeasureEnum.PSF,
        frequency=FrequencyEnum.ANNUAL,
        upon_expiration=UponExpirationEnum.MARKET
    )
    
    lease2 = Lease(
        name="Lease 2",
        tenant=tenant2,
        suite="102",
        floor="1",
        use_type=ProgramUseEnum.OFFICE,
        lease_type=LeaseTypeEnum.NNN,
        area=500,
        timeline=Timeline.from_dates(lease2_start, lease2_end),
        value=22.0, # Assume $/SF/Year
        unit_of_measure=UnitOfMeasureEnum.PSF,
        frequency=FrequencyEnum.ANNUAL,
        upon_expiration=UponExpirationEnum.MARKET
    )
    
    rent_roll = RentRoll(leases=[lease1, lease2], vacant_suites=[])
    
    # Assume simple expenses for now, not strictly needed for occupancy test
    expenses = Expenses(
        operating_expenses=OperatingExpenses(expense_items=[]),
        capital_expenses=CapitalExpenses(expense_items=[])
    )

    prop = Property(
        name="Test Property",
        property_type="Office",
        net_rentable_area=2000, # Total NRA
        rent_roll=rent_roll,
        expenses=expenses,
        # Other required Property fields might need defaults
        address="123 Main St",
        geography="Test City",
        submarket="Downtown",
        market="Test Market",
        year_built=2000
    )
    return prop

@pytest.fixture
def property_with_expenses() -> Property:
    """Provides a Property object with some OpEx items."""
    
    # OpEx Item 1: Fixed Amount per Year
    opex1_timeline = Timeline.from_dates(date(2023, 1, 1), date(2025, 12, 31))
    opex1 = OpExItem(
        name="Insurance",
        value=12000.0, # 12000 $/Year
        unit_of_measure=UnitOfMeasureEnum.AMOUNT,
        frequency=FrequencyEnum.ANNUAL,
        timeline=opex1_timeline,
        variable_ratio=0.0, # Fixed
        recoverable_ratio=1.0
    )
    
    # OpEx Item 2: Per SF per Year, Variable
    opex2_timeline = Timeline.from_dates(date(2023, 1, 1), date(2025, 12, 31))
    opex2 = OpExItem(
        name="Janitorial",
        value=1.5, # 1.5 $/SF/Year
        unit_of_measure=UnitOfMeasureEnum.PSF,
        frequency=FrequencyEnum.ANNUAL,
        timeline=opex2_timeline,
        variable_ratio=0.8, # 80% Variable
        recoverable_ratio=1.0,
        reference="net_rentable_area" # Reference NRA for PSF calc
    )
    
    # OpEx Item 3: Percentage of EGI (requires more complex lookup setup later)
    # opex3_timeline = Timeline.from_dates(date(2023, 1, 1), date(2025, 12, 31))
    # opex3 = OpExItem(
    #     name="Management Fee",
    #     value=3.0, # 3% 
    #     unit_of_measure=UnitOfMeasureEnum.BY_PERCENT,
    #     frequency=FrequencyEnum.MONTHLY, # Assume % applies monthly to monthly EGI
    #     timeline=opex3_timeline,
    #     variable_ratio=0.0, # Fixed % usually
    #     recoverable_ratio=0.0, # Usually not recoverable
    #     reference="Total Effective Gross Income" # Reference an aggregate
    # )
    
    operating_expenses = OperatingExpenses(expense_items=[opex1, opex2])
    expenses_obj = Expenses(
        operating_expenses=operating_expenses,
        capital_expenses=CapitalExpenses(expense_items=[])
    )

    prop = Property(
        name="Test Prop w/ Expenses",
        property_type="Office",
        net_rentable_area=2000, 
        rent_roll=RentRoll(leases=[], vacant_suites=[]), # Keep rent roll simple for this fixture
        expenses=expenses_obj,
        address="456 Side St",
        geography="Test City",
        submarket="Suburban",
        market="Test Market",
        year_built=2010
    )
    return prop

# --- Tests for _get_period_occupancy --- 

def test_get_period_occupancy_full_overlap(sample_property_fixture):
    """Test occupancy calc when period fully overlaps with leases."""
    prop = sample_property_fixture
    start = date(2023, 8, 1)
    end = date(2024, 5, 31)
    
    occ_series = _get_period_occupancy(prop, start, end, frequency='M')
    
    assert occ_series is not None
    assert isinstance(occ_series, pd.Series)
    assert isinstance(occ_series.index, pd.PeriodIndex)
    assert occ_series.index.freq == 'M'
    
    expected_periods = pd.period_range(start, end, freq='M')
    pd.testing.assert_index_equal(occ_series.index, expected_periods)
    
    # Expected occupancy: (1000 + 500) / 2000 = 0.75 during overlap
    expected_occ = 1500 / 2000
    assert all(occ_series == expected_occ)

def test_get_period_occupancy_partial_overlap(sample_property_fixture):
    """Test occupancy calc with partial lease overlaps."""
    prop = sample_property_fixture
    start = date(2023, 1, 1)
    end = date(2024, 12, 31) # Full analysis period
    
    occ_series = _get_period_occupancy(prop, start, end, frequency='M')
    
    assert occ_series is not None
    
    # Periods breakdown:
    # 2023-01 to 2023-06: Only Lease 1 (1000 / 2000 = 0.5)
    # 2023-07 to 2024-06: Lease 1 + Lease 2 (1500 / 2000 = 0.75)
    # 2024-07 to 2024-12: Only Lease 1 (1000 / 2000 = 0.5)
    
    periods_part1 = pd.period_range(date(2023, 1, 1), date(2023, 6, 30), freq='M')
    periods_part2 = pd.period_range(date(2023, 7, 1), date(2024, 6, 30), freq='M')
    periods_part3 = pd.period_range(date(2024, 7, 1), date(2024, 12, 31), freq='M')
    
    assert all(occ_series.loc[periods_part1] == 0.5)
    assert all(occ_series.loc[periods_part2] == 0.75)
    assert all(occ_series.loc[periods_part3] == 0.5)
    
def test_get_period_occupancy_no_overlap(sample_property_fixture):
    """Test occupancy calc when period does not overlap leases."""
    prop = sample_property_fixture
    start = date(2025, 1, 1)
    end = date(2025, 12, 31)
    
    occ_series = _get_period_occupancy(prop, start, end, frequency='M')
    
    assert occ_series is not None
    expected_periods = pd.period_range(start, end, freq='M')
    pd.testing.assert_index_equal(occ_series.index, expected_periods)
    assert all(occ_series == 0.0)

def test_get_period_occupancy_zero_nra():
    """Test occupancy calc when property NRA is zero."""
    # Create a minimal property with zero NRA
    prop = Property(
        name="Zero NRA Prop", property_type="Office", net_rentable_area=0, 
        rent_roll=RentRoll(leases=[], vacant_suites=[]), # Empty rent roll
        expenses=Expenses(operating_expenses=OperatingExpenses(expense_items=[]), capital_expenses=CapitalExpenses(expense_items=[])), 
        address="-", geography="-", submarket="-", market="-", year_built=2000
    )
    start = date(2023, 1, 1)
    end = date(2023, 12, 31)
    
    occ_series = _get_period_occupancy(prop, start, end, frequency='M')
    assert occ_series is None # Expect None if NRA is zero

def test_get_period_occupancy_empty_rentroll(sample_property_fixture):
    """Test occupancy calc with an empty rent roll."""
    prop = sample_property_fixture
    prop.rent_roll = RentRoll(leases=[], vacant_suites=[]) # Override rent roll
    start = date(2023, 1, 1)
    end = date(2023, 12, 31)
    
    occ_series = _get_period_occupancy(prop, start, end, frequency='M')
    
    assert occ_series is not None
    expected_periods = pd.period_range(start, end, freq='M')
    pd.testing.assert_index_equal(occ_series.index, expected_periods)
    assert all(occ_series == 0.0)

# --- Placeholder Tests for _get_period_expenses --- 

def test_get_period_expenses_monthly(property_with_expenses):
    """Test fetching expenses for a monthly period."""
    prop = property_with_expenses
    opex1_id = prop.expenses.operating_expenses.expense_items[0].model_id
    opex2_id = prop.expenses.operating_expenses.expense_items[1].model_id
    
    start = date(2024, 1, 1)
    end = date(2024, 3, 31)
    
    expense_dict = _get_period_expenses(prop, start, end, [opex1_id, opex2_id], frequency='M')
    
    assert expense_dict is not None
    assert isinstance(expense_dict, dict)
    assert set(expense_dict.keys()) == {opex1_id, opex2_id}
    
    # Check Opex1 (Insurance: 12000/yr = 1000/month)
    opex1_cf = expense_dict[opex1_id]
    assert isinstance(opex1_cf, pd.Series)
    expected_periods = pd.period_range(start, end, freq='M')
    pd.testing.assert_index_equal(opex1_cf.index, expected_periods)
    assert all(opex1_cf == 1000.0)
    
    # Check Opex2 (Janitorial: 1.5/sf/yr * 2000sf = 3000/yr = 250/month)
    opex2_cf = expense_dict[opex2_id]
    assert isinstance(opex2_cf, pd.Series)
    pd.testing.assert_index_equal(opex2_cf.index, expected_periods)
    assert all(opex2_cf == 250.0)
    
def test_get_period_expenses_annual(property_with_expenses):
    """Test fetching expenses aggregated annually."""
    prop = property_with_expenses
    opex1_id = prop.expenses.operating_expenses.expense_items[0].model_id
    opex2_id = prop.expenses.operating_expenses.expense_items[1].model_id
    
    start = date(2023, 1, 1)
    end = date(2024, 12, 31) # Two full years
    
    expense_dict = _get_period_expenses(prop, start, end, [opex1_id, opex2_id], frequency='A')
    
    assert expense_dict is not None
    assert set(expense_dict.keys()) == {opex1_id, opex2_id}
    
    expected_periods = pd.period_range(start, end, freq='A-DEC') # Annual frequency

    # Check Opex1 (Insurance: 12000/yr)
    opex1_cf = expense_dict[opex1_id]
    assert isinstance(opex1_cf, pd.Series)
    pd.testing.assert_index_equal(opex1_cf.index, expected_periods)
    assert all(opex1_cf == 12000.0)
    
    # Check Opex2 (Janitorial: 1.5/sf/yr * 2000sf = 3000/yr)
    opex2_cf = expense_dict[opex2_id]
    assert isinstance(opex2_cf, pd.Series)
    pd.testing.assert_index_equal(opex2_cf.index, expected_periods)
    assert all(opex2_cf == 3000.0)
    
def test_get_period_expenses_partial_period(property_with_expenses):
    """Test fetching expenses for a period that doesn't align with item timeline."""
    prop = property_with_expenses
    opex1_id = prop.expenses.operating_expenses.expense_items[0].model_id
    
    start = date(2025, 6, 1) # Starts within opex1 timeline
    end = date(2026, 5, 31) # Ends after opex1 timeline
    
    expense_dict = _get_period_expenses(prop, start, end, [opex1_id], frequency='M')
    
    assert expense_dict is not None
    opex1_cf = expense_dict[opex1_id]
    
    expected_periods = pd.period_range(start, end, freq='M')
    pd.testing.assert_index_equal(opex1_cf.index, expected_periods)
    
    # Opex1 ends 2025-12-31. Should have 1000/month until then, 0 after.
    periods_active = pd.period_range(date(2025, 6, 1), date(2025, 12, 31), freq='M')
    periods_inactive = pd.period_range(date(2026, 1, 1), date(2026, 5, 31), freq='M')
    
    assert all(opex1_cf.loc[periods_active] == 1000.0)
    assert all(opex1_cf.loc[periods_inactive] == 0.0)

def test_get_period_expenses_missing_id(property_with_expenses):
    """Test fetching expenses when some IDs are not found."""
    prop = property_with_expenses
    opex1_id = prop.expenses.operating_expenses.expense_items[0].model_id
    missing_id = UUID() # Generate a random UUID
    
    start = date(2024, 1, 1)
    end = date(2024, 12, 31)
    
    expense_dict = _get_period_expenses(prop, start, end, [opex1_id, missing_id], frequency='A')
    
    assert expense_dict is not None
    assert set(expense_dict.keys()) == {opex1_id} # Should only contain the found ID
    assert all(expense_dict[opex1_id] == 12000.0)
    
def test_get_period_expenses_no_matches(property_with_expenses):
    """Test fetching expenses when no requested IDs are found."""
    prop = property_with_expenses
    missing_id = UUID()
    
    start = date(2024, 1, 1)
    end = date(2024, 12, 31)
    
    expense_dict = _get_period_expenses(prop, start, end, [missing_id], frequency='A')
    
    assert expense_dict == {} # Expect empty dict

# --- Tests for _gross_up_period_expenses --- 

@pytest.fixture
def gross_up_fixture_data(property_with_expenses):
    """Provides data needed for _gross_up_period_expenses tests."""
    prop = property_with_expenses
    opex1 = prop.expenses.operating_expenses.expense_items[0]
    opex2 = prop.expenses.operating_expenses.expense_items[1]
    
    # Simulate raw expense calculation results (monthly)
    timeline = pd.period_range(start=date(2024, 1, 1), periods=12, freq='M')
    raw_expenses = {
        opex1.model_id: pd.Series(1000.0, index=timeline), # Insurance (fixed)
        opex2.model_id: pd.Series(250.0, index=timeline)  # Janitorial (variable)
    }
    
    # Example occupancy series (low occupancy triggering gross-up)
    occupancy_series = pd.Series(0.80, index=timeline) # 80% occupancy
    
    # Map of items needed for variable_ratio lookup
    expense_items_map = {item.model_id: item for item in [opex1, opex2]}
    
    return raw_expenses, occupancy_series, expense_items_map

def test_gross_up_expenses_applies(gross_up_fixture_data):
    """Test gross-up when occupancy is below target."""
    raw_expenses, occupancy_series, expense_items_map = gross_up_fixture_data
    opex1_id = list(expense_items_map.keys())[0]
    opex2_id = list(expense_items_map.keys())[1]

    grossed_up_dict = _gross_up_period_expenses(
        raw_expenses, occupancy_series, expense_items_map, gross_up_target_rate=0.95
    )
    
    assert opex1_id in grossed_up_dict
    assert opex2_id in grossed_up_dict
    
    # Opex1 (Insurance) is fixed (var_ratio=0.0), should not change
    pd.testing.assert_series_equal(grossed_up_dict[opex1_id], raw_expenses[opex1_id])
    
    # Opex2 (Janitorial) is 80% variable, should be grossed up
    # Raw = 250. Fixed = 250 * 0.2 = 50. Variable = 250 * 0.8 = 200.
    # GrossedUp Variable = 200 / 0.80 = 250
    # Total GrossedUp = Fixed + GrossedUp Variable = 50 + 250 = 300
    expected_opex2_grossed_up = pd.Series(300.0, index=occupancy_series.index)
    pd.testing.assert_series_equal(grossed_up_dict[opex2_id], expected_opex2_grossed_up, check_dtype=False)

def test_gross_up_expenses_not_needed(gross_up_fixture_data):
    """Test gross-up when occupancy is at or above target."""
    raw_expenses, _, expense_items_map = gross_up_fixture_data
    opex1_id = list(expense_items_map.keys())[0]
    opex2_id = list(expense_items_map.keys())[1]
    
    # High occupancy, should not trigger gross-up
    high_occupancy = pd.Series(0.98, index=raw_expenses[opex1_id].index)
    
    grossed_up_dict = _gross_up_period_expenses(
        raw_expenses, high_occupancy, expense_items_map, gross_up_target_rate=0.95
    )
    
    # Both expenses should be unchanged
    pd.testing.assert_series_equal(grossed_up_dict[opex1_id], raw_expenses[opex1_id])
    pd.testing.assert_series_equal(grossed_up_dict[opex2_id], raw_expenses[opex2_id])

def test_gross_up_expenses_no_occupancy(gross_up_fixture_data):
    """Test gross-up when occupancy data is missing."""
    raw_expenses, _, expense_items_map = gross_up_fixture_data
    opex1_id = list(expense_items_map.keys())[0]
    opex2_id = list(expense_items_map.keys())[1]
    
    grossed_up_dict = _gross_up_period_expenses(
        raw_expenses, None, expense_items_map, gross_up_target_rate=0.95
    )
    
    # Should return raw expenses if occupancy is None
    assert grossed_up_dict == raw_expenses
    pd.testing.assert_series_equal(grossed_up_dict[opex1_id], raw_expenses[opex1_id])
    pd.testing.assert_series_equal(grossed_up_dict[opex2_id], raw_expenses[opex2_id])

def test_gross_up_only_recoverable(property_with_expenses):
    """Test that only recoverable items are grossed up (even if variable)."""
    prop = property_with_expenses
    opex1 = prop.expenses.operating_expenses.expense_items[0] # Insurance (Recoverable=1.0, Var=0.0)
    opex2 = prop.expenses.operating_expenses.expense_items[1] # Janitorial (Recoverable=1.0, Var=0.8)
    
    # Add a third expense that is variable but NOT recoverable
    opex3_timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
    opex3 = OpExItem(
        name="NonRecoverableVar",
        value=500.0, # 500/month
        unit_of_measure=UnitOfMeasureEnum.AMOUNT,
        frequency=FrequencyEnum.MONTHLY,
        timeline=opex3_timeline,
        variable_ratio=0.5, # 50% Variable
        recoverable_ratio=0.0 # << Not Recoverable
    )
    
    timeline = opex3_timeline.period_index
    raw_expenses = {
        opex1.model_id: pd.Series(1000.0, index=timeline),
        opex2.model_id: pd.Series(250.0, index=timeline),
        opex3.model_id: pd.Series(500.0, index=timeline)
    }
    occupancy_series = pd.Series(0.80, index=timeline)
    expense_items_map = {item.model_id: item for item in [opex1, opex2, opex3]}
    
    grossed_up_dict = _gross_up_period_expenses(
        raw_expenses, occupancy_series, expense_items_map, gross_up_target_rate=0.95
    )
    
    # Opex1 (Fixed) and Opex3 (Non-Recoverable) should be unchanged
    pd.testing.assert_series_equal(grossed_up_dict[opex1.model_id], raw_expenses[opex1.model_id])
    pd.testing.assert_series_equal(grossed_up_dict[opex3.model_id], raw_expenses[opex3.model_id])
    
    # Opex2 (Variable, Recoverable) should be grossed up (300.0 from previous test)
    expected_opex2_grossed_up = pd.Series(300.0, index=occupancy_series.index)
    pd.testing.assert_series_equal(grossed_up_dict[opex2.model_id], expected_opex2_grossed_up, check_dtype=False) 