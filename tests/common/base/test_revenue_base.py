from __future__ import annotations

from datetime import date

import pytest

from performa.common.base._revenue_base import MiscIncomeBase
from performa.common.primitives import (
    RevenueSubcategoryEnum,
    Timeline,
    UnitOfMeasureEnum,
)


@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)

def test_misc_income_base_instantiation(sample_timeline: Timeline):
    """Test successful instantiation of MiscIncomeBase."""
    item = MiscIncomeBase(
        name="Parking Income",
        timeline=sample_timeline,
        value=5000,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
    )
    assert item.name == "Parking Income"
    assert item.subcategory == RevenueSubcategoryEnum.MISC
