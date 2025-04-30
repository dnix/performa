from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from performa.asset._expense import (
    CapitalExpenses,
    Expenses,
    OperatingExpenses,
    OpExItem,
)
from performa.asset._property import Property
from performa.asset._recovery import ExpensePool, Recovery

# Models to test/use
from performa.asset._revenue import Lease, RecoveryMethod, RentRoll, Tenant
from performa.core._enums import (
    FrequencyEnum,
    LeaseTypeEnum,
    ProgramUseEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from performa.core._timeline import Timeline

# Assume utils are tested separately, but we might need to mock them
# from performa.asset._calc_utils import _get_period_expenses, _get_period_occupancy, _gross_up_period_expenses

# --- Fixtures --- 

@pytest.fixture
def base_year_lease_fixture():
    """Provides a Lease with Base Year recovery structures."""
    lease_start = date(2024, 1, 1)
    lease_end = date(2028, 12, 31)
    tenant = Tenant(id="BY_Tenant", name="Base Year Tenant")
    timeline = Timeline.from_dates(lease_start, lease_end)

    # Define some expense items
    opex1 = OpExItem(
        name="OpEx 1 (Var, Rec)", 
        value=1.0, unit_of_measure=UnitOfMeasureEnum.PSF, frequency=FrequencyEnum.ANNUAL, 
        timeline=timeline, variable_ratio=0.5, recoverable_ratio=1.0, reference="net_rentable_area"
    )
    opex2 = OpExItem(
        name="OpEx 2 (Fixed, Rec)", 
        value=0.5, unit_of_measure=UnitOfMeasureEnum.PSF, frequency=FrequencyEnum.ANNUAL, 
        timeline=timeline, variable_ratio=0.0, recoverable_ratio=1.0, reference="net_rentable_area"
    )
    
    # Define an Expense Pool
    pool1 = ExpensePool(name="Pool 1", expenses=[opex1, opex2]) # Pool of recoverable expenses

    # Define Recovery structures
    recovery_by = Recovery(
        expenses=pool1,
        structure="base_year",
        base_year=2024 # Explicitly set base year for clarity, though calc uses lease start
    )
    recovery_by_minus_1 = Recovery(
        expenses=pool1,
        structure="base_year_minus1",
        base_year=2023
    )

    # Define Recovery Method
    recovery_method = RecoveryMethod(
        name="Base Year Recovery Method",
        gross_up=True,
        gross_up_percent=0.95,
        recoveries=[recovery_by, recovery_by_minus_1]
    )

    # Create the Lease
    lease = Lease(
        name="Lease with Base Year Rec",
        tenant=tenant,
        suite="200",
        floor="2",
        use_type=ProgramUseEnum.OFFICE,
        lease_type=LeaseTypeEnum.MODGROSS, # Base year often used with modified gross
        area=5000,
        timeline=timeline,
        value=30.0, unit_of_measure=UnitOfMeasureEnum.PSF, frequency=FrequencyEnum.ANNUAL,
        upon_expiration=UponExpirationEnum.MARKET,
        recovery_method=recovery_method,
        recoveries=[recovery_by, recovery_by_minus_1] # Assign recoveries directly too?
         # The design has RecoveryMethod containing Recoveries. Lease points to Method.
         # Let's remove the direct assignment here. 
    )
    
    # Create associated Property for context
    prop = Property(
        name="Base Year Test Prop",
        property_type="Office",
        net_rentable_area=10000, # Property NRA
        rent_roll=RentRoll(leases=[lease], vacant_suites=[]), 
        expenses=Expenses(
             operating_expenses=OperatingExpenses(expense_items=[opex1, opex2]), 
             capital_expenses=CapitalExpenses(expense_items=[])
        ),
        address="789 Test Ave", geography="Test", submarket="Test", market="Test", year_built=2000
    )
    
    # Return Lease and Property
    return lease, prop, opex1.model_id, opex2.model_id 

# --- Tests for Lease._calculate_and_cache_base_year_stops --- 

# We need to mock the utility functions called by the method under test
@patch('performa.asset._revenue._get_period_expenses')
@patch('performa.asset._revenue._get_period_occupancy')
@patch('performa.asset._revenue._gross_up_period_expenses')
def test_calculate_base_year_stop_simple(
    mock_gross_up, mock_get_occ, mock_get_exp, base_year_lease_fixture
):
    """Test calculation for a simple Base Year (BY) structure."""
    lease, prop, opex1_id, opex2_id = base_year_lease_fixture
    recovery_by = lease.recovery_method.recoveries[0]
    assert recovery_by.structure == "base_year"
    
    # --- Mock Setup --- 
    base_year = 2024
    by_start = date(base_year, 1, 1)
    by_end = date(base_year, 12, 31)
    timeline_by = pd.period_range(by_start, by_end, freq='M')
    
    # Mock _get_period_occupancy response
    mock_occupancy = pd.Series(0.90, index=timeline_by) # Assume 90% occupancy
    mock_get_occ.return_value = mock_occupancy
    
    # Mock _get_period_expenses response (raw monthly)
    mock_expenses_raw = {
        opex1_id: pd.Series( (1.0 * 10000 / 12), index=timeline_by), # 1.0*10000/12 = 833.33
        opex2_id: pd.Series( (0.5 * 10000 / 12), index=timeline_by)  # 0.5*10000/12 = 416.67
    }
    mock_get_exp.return_value = mock_expenses_raw
    
    # Mock _gross_up_period_expenses response (what it *should* return)
    # Opex1 (Var=0.5): Fixed=416.67, Var=416.67. GrossedVar = 416.67/0.90=462.96. Total=416.67+462.96=879.63
    # Opex2 (Var=0.0): Fixed=416.67. Total=416.67
    mock_expenses_grossed_up = {
        opex1_id: pd.Series(879.63, index=timeline_by),
        opex2_id: pd.Series(416.67, index=timeline_by)
    }
    mock_gross_up.return_value = mock_expenses_grossed_up
    # --- End Mock Setup --- 
    
    # --- Execute --- 
    lease._calculate_and_cache_base_year_stops(prop)
    # --- End Execute --- 
    
    # --- Assertions --- 
    # Check that utils were called correctly
    mock_get_occ.assert_called_once_with(prop, by_start, by_end, frequency='M')
    mock_get_exp.assert_called_once_with(prop, by_start, by_end, expense_item_ids=[opex1_id, opex2_id], frequency='M')
    # Check that gross up was called correctly
    # Need to compare args carefully, especially the items map
    call_args, call_kwargs = mock_gross_up.call_args
    assert call_args[0] == mock_expenses_raw # raw expenses
    pd.testing.assert_series_equal(call_args[1], mock_occupancy) # occupancy
    # assert call_args[2] == {opex1_id: ..., opex2_id: ...} # items map
    assert call_kwargs.get('gross_up_target_rate') == 0.95
    
    # Check the stored stop amount
    expected_annual_stop = (879.63 + 416.67) * 12 # Sum of monthly grossed up * 12
    assert recovery_by._calculated_annual_base_year_stop == pytest.approx(expected_annual_stop)
    assert recovery_by._frozen_base_year_pro_rata is None # Freeze share defaults to False

@patch('performa.asset._revenue._get_period_expenses')
@patch('performa.asset._revenue._get_period_occupancy')
@patch('performa.asset._revenue._gross_up_period_expenses')
def test_calculate_base_year_stop_partial_year(
    mock_gross_up, mock_get_occ, mock_get_exp, base_year_lease_fixture
):
    """Test annualization when base year data is partial (e.g., lease starts mid-year)."""
    # Modify fixture: Lease starts mid-2024, Base Year is still 2024
    lease, prop, opex1_id, opex2_id = base_year_lease_fixture
    lease.timeline = Timeline.from_dates(date(2024, 7, 1), date(2028, 12, 31)) # Starts July 1st
    recovery_by = lease.recovery_method.recoveries[0]
    assert recovery_by.structure == "base_year"
    
    # --- Mock Setup --- 
    base_year = 2024
    # Precise base period is first 12 months of lease: 2024-07-01 to 2025-06-30
    # However, the *data fetching* is done for the target_base_year (2024)
    by_start_fetch = date(base_year, 1, 1)
    by_end_fetch = date(base_year, 12, 31)
    timeline_fetch = pd.period_range(by_start_fetch, by_end_fetch, freq='M')
    
    mock_occupancy = pd.Series(0.90, index=timeline_fetch)
    mock_get_occ.return_value = mock_occupancy
    
    # Simulate getting full year expenses, even though we only need part for annualization base
    mock_expenses_raw = {
        opex1_id: pd.Series(833.33, index=timeline_fetch), 
        opex2_id: pd.Series(416.67, index=timeline_fetch) 
    }
    mock_get_exp.return_value = mock_expenses_raw
    
    # Mock gross-up result (same rate as before for simplicity)
    mock_expenses_grossed_up = {
        opex1_id: pd.Series(879.63, index=timeline_fetch),
        opex2_id: pd.Series(416.67, index=timeline_fetch)
    }
    mock_gross_up.return_value = mock_expenses_grossed_up
    # --- End Mock Setup --- 
    
    # --- Execute --- 
    lease._calculate_and_cache_base_year_stops(prop)
    # --- End Execute --- 

    # --- Assertions --- 
    # Precise base period for this lease: 2024-07 to 2025-06
    # Current logic fetches calendar year 2024, then slices that based on lease start.
    # Precise period: 2024-07 to 2024-12 (6 months)
    # Sum for these 6 months = (879.63 + 416.67) * 6 = 1296.3 * 6 = 7777.8
    # Annualized = 7777.8 / 6 * 12 = 15555.6
    expected_annual_stop = (879.63 + 416.67) * 12 
    
    assert recovery_by._calculated_annual_base_year_stop == pytest.approx(expected_annual_stop)

@patch('performa.asset._revenue._get_period_expenses')
@patch('performa.asset._revenue._get_period_occupancy')
# No need to mock gross-up if expenses are missing
def test_calculate_base_year_stop_missing_history(
    mock_get_occ, mock_get_exp, base_year_lease_fixture
):
    """Test BY-1 structure when historical expense data is missing."""
    lease, prop, opex1_id, opex2_id = base_year_lease_fixture
    # Target the BY-1 recovery object
    recovery_bym1 = lease.recovery_method.recoveries[1]
    assert recovery_bym1.structure == "base_year_minus1"
    
    # --- Mock Setup --- 
    base_year = 2023 # Lease starts 2024, so BY-1 is 2023
    by_start = date(base_year, 1, 1)
    by_end = date(base_year, 12, 31)
    timeline_by = pd.period_range(by_start, by_end, freq='M')
    
    # Mock occupancy (might still be available)
    mock_occupancy = pd.Series(0.85, index=timeline_by)
    mock_get_occ.return_value = mock_occupancy
    
    # Mock expense fetch to return None (or empty dict)
    mock_get_exp.return_value = None # Simulate failure to fetch/find data
    # --- End Mock Setup --- 
    
    # --- Execute --- 
    lease._calculate_and_cache_base_year_stops(prop)
    # --- End Execute --- 
    
    # --- Assertions --- 
    # Check utils were called for the relevant year
    mock_get_occ.assert_called_once_with(prop, by_start, by_end, frequency='M')
    mock_get_exp.assert_called_once_with(prop, by_start, by_end, expense_item_ids=[opex1_id, opex2_id], frequency='M')
    
    # Check that the stop was set to 0.0 due to missing expenses
    # Note: The simple BY recovery for 2024 might still be calculated if we didn't mock its expenses as missing.
    # We are specifically checking the BY-1 recovery instance.
    assert recovery_bym1._calculated_annual_base_year_stop == 0.0

# TODO: Add tests for BY+1

# --- Placeholder Tests for RecoveryMethod.calculate_recoveries changes --- 

# TODO: Add tests focusing on the base year logic in calculate_recoveries 