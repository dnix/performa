from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.analysis import AnalysisContext
from performa.core.base import CapExItemBase, OpExItemBase
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    Timeline,
    UnitOfMeasureEnum,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def sample_timeline() -> Timeline:
    """A 1-year timeline fixture."""
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))

@pytest.fixture
def sample_context(sample_timeline: Timeline) -> AnalysisContext:
    property_data = None # Not needed for these base tests
    return AnalysisContext(
        timeline=sample_timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        resolved_lookups={},
        recovery_states={},
    )


def test_expense_item_base_compute_cf(sample_context: AnalysisContext):
    """Test the simple compute_cf implementation on the base expense class."""
    item1 = OpExItemBase(
        name="Test Item 1",
        timeline=sample_context.timeline,
        value=100,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
    )
    result1 = item1.compute_cf(context=sample_context)
    assert isinstance(result1, pd.Series)
    assert result1.iloc[0] == 100
    assert result1.sum() == 1200

    item2 = OpExItemBase(
        name="Test Item 2",
        timeline=sample_context.timeline,
        value=120,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        frequency=FrequencyEnum.ANNUAL,
    )
    result2 = item2.compute_cf(context=sample_context)
    assert result2.iloc[0] == 10
    assert result2.sum() == 120


def test_capex_item_base(sample_context: AnalysisContext):
    """Test the CapExItemBase compute_cf implementation."""
    capex = CapExItemBase(
        name="Test CapEx",
        timeline=sample_context.timeline,
        value={"2024-06-01": 50000},
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
    )
    result = capex.compute_cf(context=sample_context)
    assert result.sum() == 50000
    assert result.loc[pd.Period("2024-06", "M")] == 50000
    assert result.loc[pd.Period("2024-05", "M")] == 0 