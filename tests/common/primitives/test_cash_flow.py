from __future__ import annotations

from datetime import date
from uuid import UUID

import pandas as pd
import pytest

from performa.common.primitives._cash_flow import CashFlowModel
from performa.common.primitives._enums import (
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
    FrequencyEnum,
    UnitOfMeasureEnum,
)
from performa.common.primitives._growth_rates import GrowthRate
from performa.common.primitives._timeline import Timeline


@pytest.fixture
def sample_timeline() -> Timeline:
    """Provides a sample Timeline fixture for tests."""
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))


class MinimalConcreteCashFlowModel(CashFlowModel):
    """A minimal, concrete implementation of CashFlowModel for testing."""

    def compute_cf(self, **kwargs) -> pd.Series:
        # A simple implementation for testing purposes
        return pd.Series([self.value] * self.timeline.duration_months, index=self.timeline.period_index)


def test_cashflowmodel_is_abc():
    """Test that the base CashFlowModel is abstract and cannot be instantiated."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        CashFlowModel()


def test_minimal_concrete_cashflowmodel_instantiation(sample_timeline: Timeline):
    """Test successful instantiation of a concrete CashFlowModel subclass."""
    model = MinimalConcreteCashFlowModel(
        name="Test Rent",
        category=CashFlowCategoryEnum.REVENUE,
        subcategory="SomeSubCategory",
        timeline=sample_timeline,
        value=1000.0,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        frequency=FrequencyEnum.MONTHLY,
    )
    assert model.name == "Test Rent"
    assert model.value == 1000.0
    assert model.timeline == sample_timeline


def test_cashflowmodel_default_field_values(sample_timeline: Timeline):
    """Test the default values of optional fields in CashFlowModel."""
    model = MinimalConcreteCashFlowModel(
        name="Test Expense",
        category=CashFlowCategoryEnum.EXPENSE,
        subcategory=ExpenseSubcategoryEnum.OPEX,
        timeline=sample_timeline,
        value=500.0,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
    )
    assert isinstance(model.model_id, UUID)
    assert model.description is None
    assert model.account is None
    assert model.reference is None
    assert model.frequency == FrequencyEnum.MONTHLY


def test_resolve_reference_direct_value(sample_timeline: Timeline):
    """Test resolve_reference with a direct numeric value."""
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=1, unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        reference=123.45
    )
    assert model.resolve_reference() == 123.45


def test_resolve_reference_with_lookup_fn(sample_timeline: Timeline):
    """Test resolve_reference with a string identifier and a lookup function."""
    lookup_data = {"some_key": 543.21}
    def lookup_fn(key):
        return lookup_data.get(key)

    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=1, unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        reference="some_key"
    )
    assert model.resolve_reference(lookup_fn=lookup_fn) == 543.21


def test_resolve_reference_missing_lookup_fn(sample_timeline: Timeline):
    """Test that resolve_reference raises ValueError if a lookup_fn is required but not provided."""
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=1, unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        reference="some_key"
    )
    with pytest.raises(ValueError, match="A lookup function is required"):
        model.resolve_reference()


def test_convert_frequency(sample_timeline: Timeline):
    """Test the _convert_frequency method."""
    # Monthly frequency should not change the value
    model_monthly = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=1200, unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        frequency=FrequencyEnum.MONTHLY
    )
    assert model_monthly._convert_frequency(1200) == 1200

    # Annual frequency should divide the value by 12
    model_annual = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=1200, unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        frequency=FrequencyEnum.ANNUAL
    )
    assert model_annual._convert_frequency(1200) == 100


def test_cast_to_flow(sample_timeline: Timeline):
    """Test the _cast_to_flow method with various input types."""
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=0, unit_of_measure=UnitOfMeasureEnum.CURRENCY
    )

    # Test with scalar
    series_from_scalar = model._cast_to_flow(100)
    assert isinstance(series_from_scalar, pd.Series)
    assert len(series_from_scalar) == 12
    assert (series_from_scalar == 100).all()

    # Test with list
    list_val = [i for i in range(12)]
    series_from_list = model._cast_to_flow(list_val)
    assert isinstance(series_from_list, pd.Series)
    pd.testing.assert_series_equal(series_from_list, pd.Series(list_val, index=sample_timeline.period_index))

    # Test with dict
    dict_val = {'2024-01': 1, '2024-02': 2}
    series_from_dict = model._cast_to_flow(dict_val)
    assert isinstance(series_from_dict, pd.Series)
    assert series_from_dict['2024-01'] == 1
    assert series_from_dict['2024-03'] == 0 # Test fill_value

    # Test with Series
    series_val = pd.Series([10, 20], index=pd.period_range(start='2024-02', periods=2, freq='M'))
    series_from_series = model._cast_to_flow(series_val)
    assert series_from_series['2024-02'] == 10
    assert series_from_series['2024-01'] == 0


def test_align_flow_series(sample_timeline: Timeline):
    """Test the _align_flow_series method."""
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=0, unit_of_measure=UnitOfMeasureEnum.CURRENCY
    )
    misaligned_series = pd.Series([100], index=pd.period_range(start='2025-01', periods=1, freq='M'))
    aligned_series = model._align_flow_series(misaligned_series)
    
    pd.testing.assert_series_equal(aligned_series, pd.Series([0.0] * 12, index=sample_timeline.period_index, dtype='float64'))
    assert aligned_series.sum() == 0

    # Test series that partially overlaps
    partially_aligned_series = pd.Series([10, 20], index=pd.period_range(start='2024-12', periods=2, freq='M'))
    aligned_series_2 = model._align_flow_series(partially_aligned_series)
    assert aligned_series_2['2024-12'] == 10
    assert aligned_series_2.sum() == 10


def test_apply_compounding_growth_constant_rate(sample_timeline: Timeline):
    """Test _apply_compounding_growth with a constant annual rate."""
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=0, unit_of_measure=UnitOfMeasureEnum.CURRENCY
    )
    base_series = pd.Series(100.0, index=sample_timeline.period_index)
    growth_rate = GrowthRate(name="Test Growth", value=0.12) # 12% annual growth -> 1% monthly

    grown_series = model._apply_compounding_growth(base_series, growth_rate)
    
    # With corrected logic, growth applies from period 0.
    # Month 1: 100 * (1.01) = 101
    # Month 2: 100 * (1.01)^2 = 102.01
    assert grown_series.iloc[0] == pytest.approx(100.0 * 1.01)
    assert grown_series.iloc[1] == pytest.approx(100.0 * (1.01**2))
    assert grown_series.iloc[11] == pytest.approx(100.0 * (1.01**12))


def test_apply_compounding_growth_series_rate(sample_timeline: Timeline):
    """Test _apply_compounding_growth with a pandas Series of monthly rates."""
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=0, unit_of_measure=UnitOfMeasureEnum.CURRENCY
    )
    base_series = pd.Series(100.0, index=sample_timeline.period_index)
    
    # Rates are monthly and start partway through
    rate_index = pd.period_range(start='2024-03', periods=3, freq='M')
    rate_series = pd.Series([0.01, 0.02, 0.015], index=rate_index)
    growth_rate = GrowthRate(name="Test Series Growth", value=rate_series)

    grown_series = model._apply_compounding_growth(base_series, growth_rate)

    # Rates before March are 0, so factor is 1.
    assert grown_series.iloc[0] == 100.0 
    assert grown_series.iloc[1] == 100.0
    # Growth starts in March
    assert grown_series.iloc[2] == pytest.approx(100.0 * 1.01)
    # Compounded in April
    assert grown_series.iloc[3] == pytest.approx(100.0 * 1.01 * 1.02)
    # Compounded in May
    assert grown_series.iloc[4] == pytest.approx(100.0 * 1.01 * 1.02 * 1.015)
    # Rate is forward-filled, so May's rate of 1.5% is used again.
    assert grown_series.iloc[5] == pytest.approx(grown_series.iloc[4] * 1.015)
