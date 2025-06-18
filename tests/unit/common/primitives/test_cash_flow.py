from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.analysis import AnalysisContext
from performa.common.primitives import (
    AggregateLineKey,
    CashFlowModel,
    FrequencyEnum,
    GlobalSettings,
    Timeline,
    UnitOfMeasureEnum,
)


class MinimalConcreteCashFlowModel(CashFlowModel):
    """A minimal, concrete implementation of CashFlowModel for testing."""
    pass # Inherits the concrete compute_cf

@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)

@pytest.fixture
def sample_context(sample_timeline: Timeline) -> AnalysisContext:
    return AnalysisContext(timeline=sample_timeline, settings=GlobalSettings(), property_data=None)

def test_instantiation_with_list_value(sample_timeline: Timeline):
    """Test that a CashFlowModel can be instantiated with a list value."""
    list_val = [i for i in range(12)]
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=list_val, unit_of_measure=UnitOfMeasureEnum.CURRENCY
    )
    assert model.value == list_val

def test_instantiation_with_series_value(sample_timeline: Timeline):
    series_val = pd.Series(range(12), index=sample_timeline.period_index)
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=series_val, unit_of_measure=UnitOfMeasureEnum.CURRENCY
    )
    pd.testing.assert_series_equal(model.value, series_val)

def test_reference_is_aggregate_line_key(sample_timeline: Timeline):
    """Test that the reference field accepts AggregateLineKey enum values."""
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=1, unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        reference=AggregateLineKey.TOTAL_OPERATING_EXPENSES
    )
    assert model.reference == AggregateLineKey.TOTAL_OPERATING_EXPENSES

    with pytest.raises(ValidationError):
        MinimalConcreteCashFlowModel(
            name="Test", category="cat", subcategory="sub",
            timeline=sample_timeline, value=1, unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            reference="invalid-aggregate-key"
        )
