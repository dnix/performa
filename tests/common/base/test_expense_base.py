from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.common.base._expense_base import CapExItemBase, OpExItemBase
from performa.common.primitives import (
    ExpenseSubcategoryEnum,
    Timeline,
    UnitOfMeasureEnum,
)


@pytest.fixture
def sample_timeline() -> Timeline:
    """Provides a sample Timeline fixture for tests."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)

def test_opex_item_base_instantiation(sample_timeline: Timeline):
    """Test successful instantiation of OpExItemBase."""
    item = OpExItemBase(
        name="Property Tax",
        timeline=sample_timeline,
        value=12000,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        variable_ratio=0.5,
        recoverable_ratio=1.0,
    )
    assert item.subcategory == ExpenseSubcategoryEnum.OPEX
    assert item.variable_ratio == 0.5
    assert item.is_variable
    assert item.is_recoverable

def test_opex_item_base_properties(sample_timeline: Timeline):
    """Test the is_variable and is_recoverable properties on OpExItemBase."""
    item = OpExItemBase(
        name="Insurance",
        timeline=sample_timeline,
        value=2400,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
    )
    assert not item.is_variable
    assert not item.is_recoverable # default is 0.0

    item_rec = OpExItemBase(
        name="Insurance",
        timeline=sample_timeline,
        value=2400,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        recoverable_ratio=0.9
    )
    assert item_rec.is_recoverable

def test_capex_item_base_instantiation(sample_timeline: Timeline):
    """Test successful instantiation of CapExItemBase."""
    item = CapExItemBase(
        name="Roof Replacement",
        timeline=sample_timeline,
        value=[1000] * 12, # Must be a list, dict, or series
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
    )
    assert item.subcategory == ExpenseSubcategoryEnum.CAPEX

def test_capex_item_base_fails_with_scalar(sample_timeline: Timeline):
    """Test that CapExItemBase instantiation fails with a scalar value."""
    with pytest.raises(ValidationError):
        CapExItemBase(
            name="Roof Replacement",
            timeline=sample_timeline,
            value=120000, # Scalar value is not allowed
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        )

def test_expense_item_base_compute_cf(sample_timeline: Timeline):
    """Test the simple compute_cf implementation on the base expense class."""
    # Test with scalar value
    item1 = OpExItemBase(
        name="Test Item 1",
        timeline=sample_timeline,
        value=100,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
    )
    result1 = item1.compute_cf()
    pd.testing.assert_series_equal(result1, pd.Series(100.0, index=sample_timeline.period_index))

    # Test with Series value
    series_val = pd.Series([50] * 12, index=sample_timeline.period_index)
    item2 = OpExItemBase(
        name="Test Item 2",
        timeline=sample_timeline,
        value=series_val,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
    )
    result2 = item2.compute_cf()
    pd.testing.assert_series_equal(result2, series_val)
