from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pandas as pd
import pytest

from performa.asset._expense import OpExItem

# Models to test/use
from performa.asset._recovery import ExpensePool, Recovery, RecoveryMethod
from performa.core._enums import FrequencyEnum, UnitOfMeasureEnum
from performa.core._settings import GlobalSettings
from performa.core._timeline import Timeline

# --- Fixtures --- 

@pytest.fixture
def recovery_method_fixture():
    """Provides a RecoveryMethod with various Recovery structures."""
    # Define Expense Items (need UUIDs)
    opex_fixed_rec = OpExItem(
        name="Fixed Rec", value=1000, unit_of_measure=UnitOfMeasureEnum.AMOUNT, 
        frequency=FrequencyEnum.ANNUAL, timeline=Timeline.from_dates(date(2023,1,1), date(2025,12,31)),
        variable_ratio=0.0, recoverable_ratio=1.0
    )
    opex_var_rec = OpExItem(
        name="Var Rec", value=2400, unit_of_measure=UnitOfMeasureEnum.AMOUNT, 
        frequency=FrequencyEnum.ANNUAL, timeline=Timeline.from_dates(date(2023,1,1), date(2025,12,31)),
        variable_ratio=0.5, recoverable_ratio=1.0
    )
    opex_var_nonrec = OpExItem(
        name="Var NonRec", value=500, unit_of_measure=UnitOfMeasureEnum.AMOUNT, 
        frequency=FrequencyEnum.ANNUAL, timeline=Timeline.from_dates(date(2023,1,1), date(2025,12,31)),
        variable_ratio=0.8, recoverable_ratio=0.0
    )
    
    expense_map = { # For lookup mocking
        opex_fixed_rec.model_id: opex_fixed_rec,
        opex_var_rec.model_id: opex_var_rec,
        opex_var_nonrec.model_id: opex_var_nonrec
    }

    # Expense Pools
    pool_rec = ExpensePool(name="Recoverable Pool", expenses=[opex_fixed_rec, opex_var_rec])

    # Recovery Structures
    rec_net = Recovery(expenses=pool_rec, structure="net")
    rec_stop = Recovery(expenses=pool_rec, structure="base_stop", base_amount=1.50, base_amount_unit='psf') # 1.50 $/SF/Yr stop
    rec_by = Recovery(expenses=pool_rec, structure="base_year", base_year=2024) 
    rec_fixed = Recovery(expenses=pool_rec, structure="fixed", base_amount=1200) # 1200 $/Yr fixed recovery

    # Pre-calculate a base year stop for testing rec_by
    rec_by._calculated_annual_base_year_stop = 2000.0 # Assume 2000 $/Yr stop was calculated

    # Recovery Method
    method = RecoveryMethod(
        name="Test Recovery Method",
        gross_up=True,
        gross_up_percent=0.90,
        recoveries=[rec_net, rec_stop, rec_by, rec_fixed] # Include various types
    )
    
    return method, expense_map

# --- Tests for RecoveryMethod.calculate_recoveries --- 

def test_calculate_recoveries_grossup_applied(recovery_method_fixture):
    """Test that gross-up logic is applied correctly within calculate_recoveries."""
    method, expense_map = recovery_method_fixture
    fixed_id = list(expense_map.keys())[0]
    var_id = list(expense_map.keys())[1]
    
    timeline = pd.period_range(start=date(2024, 1, 1), periods=12, freq='M')
    tenant_area = 1000.0
    prop_area = 10000.0
    occupancy = pd.Series(0.80, index=timeline) # Below 90% target
    pro_rata = tenant_area / prop_area

    # Mock lookup_fn to return raw monthly expenses
    mock_lookup = MagicMock()
    def side_effect(key):
        if key == fixed_id: 
            return pd.Series(1000/12, index=timeline)
        if key == var_id: 
            return pd.Series(2400/12, index=timeline) # 200/month
        # Don't need nonrec for Net recovery test
        raise LookupError(f"Unexpected key: {key}")
    mock_lookup.side_effect = side_effect

    # Call calculate_recoveries with necessary context
    # Use a simple mock for property_data for now
    # TODO: Create a pytest fixture for a mock Property object
    mock_prop = SimpleNamespace(property_area=prop_area)
    total_recoveries = method.calculate_recoveries(
        tenant_area=tenant_area,
        property_data=mock_prop, # Corrected - Pass mock object
        timeline=timeline,
        occupancy_rate=occupancy,
        lookup_fn=mock_lookup,
        global_settings=GlobalSettings() # Corrected - Pass default settings
    )
    
    # --- Assertions --- 
    # Check mock calls for the first recovery (Net) pool items
    mock_lookup.assert_has_calls([call(fixed_id), call(var_id)], any_order=True)
    
    # Expected Pool Expense Calculation (for Net recovery):
    # Fixed Item (1000/12 = 83.33): var=0.0 -> No gross up -> Stays 83.33
    # Var Item (2400/12 = 200): var=0.5 -> Fixed=100, Var=100. GrossedVar=100/0.8=125. Total=100+125=225
    # Total Monthly Pool Expense = 83.33 + 225 = 308.33
    # Expected Net Recovery = 308.33 * pro_rata (0.1) = 30.833
    
    # We calculated total across all recovery types, need expected sum
    # Net: 308.33 * 0.1 = 30.83
    # Stop: Base=1.5*1000/12 = 125. ExpenseShare = 308.33*0.1=30.83. Rec=max(0, 30.83-125)=0
    # BY: Stop=2000/12=166.67. Expense=308.33. Rec=max(0, 308.33-166.67)*0.1 = 14.166
    # Fixed: 1200/12 = 100
    # Total Monthly = 30.83 + 0 + 14.17 + 100 = 145.00 (approx)
    # Total Annual = 145.00 * 12 = 1740
    
    assert total_recoveries.sum() == pytest.approx(1740.0, rel=1e-2)

def test_calculate_recoveries_base_year_used(recovery_method_fixture):
    """Test that the pre-calculated base year stop is used."""
    method, expense_map = recovery_method_fixture
    fixed_id = list(expense_map.keys())[0]
    var_id = list(expense_map.keys())[1]
    rec_by = method.recoveries[2] # The Base Year recovery object
    assert rec_by.structure == "base_year"
    assert rec_by._calculated_annual_base_year_stop == 2000.0 # Check fixture setup
    
    timeline = pd.period_range(start=date(2025, 1, 1), periods=12, freq='M') # Year after base year
    tenant_area = 1000.0
    prop_area = 10000.0
    occupancy = pd.Series(0.95, index=timeline) # AT target, no gross up needed
    
    # Mock lookup_fn - gross-up won't apply
    mock_lookup = MagicMock()
    def side_effect(key):
        if key == fixed_id: 
            return pd.Series(1000/12, index=timeline) # Moved to new line
        if key == var_id: 
            return pd.Series(2400/12, index=timeline) # Moved to new line
        raise LookupError(f"Unexpected key: {key}")
    mock_lookup.side_effect = side_effect
    
    # Call calculate_recoveries with necessary context
    # Use a simple mock for property_data for now
    # FIXME: Create a pytest fixture for a mock Property object
    mock_prop = SimpleNamespace(property_area=prop_area)
    total_recoveries = method.calculate_recoveries(
        tenant_area=tenant_area,
        property_data=mock_prop, # Corrected - Pass mock object
        timeline=timeline,
        occupancy_rate=occupancy,
        lookup_fn=mock_lookup,
        global_settings=GlobalSettings() # Corrected - Pass default settings
    )
    
    # --- Assertions --- 
    # Expected Pool Expense: 83.33 + 200.00 = 283.33 (no gross-up)
    # Expected BY Recovery: MonthlyStop = 2000/12 = 166.67
    # Rec = max(0, 283.33 - 166.67) * pro_rata(0.1) = 116.66 * 0.1 = 11.666
    # Total includes Net + Stop + BY + Fixed
    # Net: 283.33 * 0.1 = 28.33
    # Stop: Base=1.5*1000/12 = 125. ExpenseShare = 283.33*0.1=28.33. Rec=max(0, 28.33-125)=0
    # BY: 11.67
    # Fixed: 1200/12 = 100
    # Total = 28.33 + 0 + 11.67 + 100 = 140.00 (monthly)
    # Total Annual = 140.00 * 12 = 1680
    
    assert total_recoveries.sum() == pytest.approx(1680.0, rel=1e-3)

# TODO: Add test for frozen pro-rata share usage
# TODO: Add test for pool_size_override usage
# TODO: Add test for base_amount_unit = 'total' in Base Stop 

@pytest.mark.parametrize(
    "recovery_structure, expected_first_month_recovery",
    [
        ("net", 20.0),  # (100 + 100) * (1000 / 10000) = 20
        # TODO: Add tests for other structures (base_stop, base_year, fixed)
    ]
)
def test_recovery_method_simple(recovery_structure, expected_first_month_recovery):
    """Test calculate_recoveries with basic structures."""
    # --- Setup ---
    start_date = date(2024, 1, 1)
    end_date = date(2024, 12, 31)
    timeline = pd.period_range(start=start_date, end=end_date, freq='M')
    tenant_area = 1000
    prop_area = 10000 # Simple 10% pro-rata
    occupancy = 1.0 # Assume full occupancy for simplicity

    # Mock expense items
    exp1 = OpExItem(name="Exp1", subcategory="Test", timeline=Timeline(start_date=start_date, duration_months=12), value=100)

def test_recovery_method_grossup():
    """Test calculate_recoveries with gross-up enabled."""
    # --- Setup ---
    start_date = date(2024, 1, 1)
    end_date = date(2024, 12, 31)
    timeline = pd.period_range(start=start_date, end=end_date, freq='M')
    tenant_area = 1000
    prop_area = 10000
    occupancy = 0.8 # Less than 1.0 to trigger gross-up
    gross_up_target = 0.95

    # Variable recoverable expense
    exp_var = OpExItem(
        name="ExpVar", 
        subcategory="Test", 
        timeline=Timeline(start_date=start_date, duration_months=12), 
        value=100, # Monthly amount
        variable_ratio=0.5, # 50% variable
        recoverable_ratio=1.0 # 100% recoverable
    )
    # Fixed non-recoverable expense
    exp_fixed_nonrec = OpExItem(
        name="ExpFixedNonRec", 
        subcategory="Test", 
        timeline=Timeline(start_date=start_date, duration_months=12), 
        value=50, # Monthly amount
        variable_ratio=0.0, 
        recoverable_ratio=0.0
    )

    pool = ExpensePool(name="Test Pool", expenses=[exp_var, exp_fixed_nonrec])
    recovery = Recovery(expenses=pool, structure="net")
    method = RecoveryMethod(
        name="Test GrossUp Method", 
        recoveries=[recovery],
        gross_up=True, 
        gross_up_percent=gross_up_target
    )

    # Mock lookup function
    mock_lookup = MagicMock()
    def side_effect(item_id):
        if item_id == exp_var.model_id:
            return pd.Series(100.0, index=timeline)
        elif item_id == exp_fixed_nonrec.model_id:
            return pd.Series(50.0, index=timeline)
        raise LookupError(f"Unknown ID: {item_id}")
    mock_lookup.side_effect = side_effect
    
    # --- Execute ---
    # Call calculate_recoveries with necessary context
    # Use a simple mock for property_data for now
    # TODO: Create a pytest fixture for a mock Property object
    mock_prop = SimpleNamespace(property_area=prop_area)
    total_recoveries = method.calculate_recoveries(
        tenant_area=tenant_area,
        property_data=mock_prop, # Corrected - Pass mock object
        timeline=timeline,
        occupancy_rate=occupancy,
        lookup_fn=mock_lookup,
        global_settings=GlobalSettings() # Corrected - Pass default settings
    )
    
    # --- Assert ---
    # Expected Calculation:
    # ExpVar: 100 = 50 Fixed + 50 Variable
    # Gross-up Variable: 50 / 0.8 = 62.5
    # Total Grossed-up ExpVar = 50 + 62.5 = 112.5
    # ExpFixedNonRec: 50 (fixed, non-rec, not grossed-up in recovery calc)
    # Pool Expense for Recovery Calc = 112.5 (only ExpVar is considered here as it's recoverable)
    # Pro-rata = 1000 / 10000 = 0.1
    # Recovery = 112.5 * 0.1 = 11.25 per month
    expected_monthly_recovery = 11.25
    pd.testing.assert_series_equal(
        total_recoveries,
        pd.Series(expected_monthly_recovery, index=timeline),
        check_dtype=False,
        atol=0.01
    ) 