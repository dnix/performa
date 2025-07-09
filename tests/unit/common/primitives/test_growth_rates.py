from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.common.primitives import GrowthRate, GrowthRates


# GrowthRate Tests
def test_growth_rate_instantiation():
    """Test successful instantiation of GrowthRate with various value types."""
    GrowthRate(name="Constant", value=0.05)
    
    series_val = pd.Series([0.02, 0.03], index=pd.period_range('2024-01', periods=2, freq='M'))
    GrowthRate(name="Series", value=series_val)

    dict_val = {date(2024, 1, 1): 0.01, date(2025, 1, 1): 0.015}
    GrowthRate(name="Dict", value=dict_val)

def test_growth_rate_validation_fails():
    """Test that GrowthRate validation fails for out-of-bounds values."""
    with pytest.raises(ValidationError):
        GrowthRate(name="Too High", value=1.1)
    
    with pytest.raises(ValidationError):
        GrowthRate(name="Too Low", value=-0.1)

    bad_series = pd.Series([0.05, 0.1])
    with pytest.raises(ValueError, match="must have a PeriodIndex"):
        GrowthRate(name="Bad Index", value=bad_series)
        
    bad_values_series = pd.Series([0.05, 1.2], index=pd.period_range('2024-01', periods=2, freq='M'))
    with pytest.raises(ValueError, match="Growth rates in Series must be between 0 and 1"):
        GrowthRate(name="Bad Series", value=bad_values_series)

    bad_dict = {date(2024, 1, 1): -0.1}
    with pytest.raises(ValidationError):
        GrowthRate(name="Bad Dict", value=bad_dict)

# GrowthRates Tests
def test_growth_rates_base_with_default_rate():
    """Test the with_default_rate classmethod."""
    default_rate = 0.03
    growth_rates = GrowthRates.with_default_rate(default_rate)
    
    assert growth_rates.default_rate == default_rate
    assert growth_rates.general_growth.value == default_rate
    assert growth_rates.market_rent_growth.value == default_rate
    assert growth_rates.operating_expense_growth.name == "Operating Expenses"

def test_growth_rates_base_with_custom_rates():
    """Test the with_custom_rates classmethod for extending the model."""
    custom_rates = GrowthRates.with_custom_rates(
        default_rate=0.02,
        extra_rates={
            "inflation_rate": GrowthRate(name="Inflation", value=0.025)
        },
        market_rent_growth=GrowthRate(name="Custom Market Rent", value=0.04)
    )

    assert hasattr(custom_rates, "inflation_rate")
    assert custom_rates.inflation_rate.value == 0.025
    assert custom_rates.market_rent_growth.value == 0.04
    # Check that a field not provided was filled by the default
    assert custom_rates.general_growth.value == 0.02

    # Test that it fails if no default is provided and a field is missing
    with pytest.raises(ValueError, match="must be provided if not all standard"):
        GrowthRates.with_custom_rates(
             extra_rates={"inflation_rate": GrowthRate(name="Inflation", value=0.025)}
        )
