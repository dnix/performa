from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.asset.office.expense import (
    OfficeCapExItem,
    OfficeExpenses,
    OfficeOpExItem,
)
from performa.common.primitives import (
    FrequencyEnum,
    GrowthRate,
    Timeline,
    UnitOfMeasureEnum,
)


@pytest.fixture
def sample_timeline():
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))

def test_office_opex_item_compute_cf(sample_timeline):
    opex = OfficeOpExItem(
        name="Test OpEx",
        timeline=sample_timeline,
        value=12000,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        frequency=FrequencyEnum.ANNUAL,
    )
    cf = opex.compute_cf()
    assert isinstance(cf, pd.Series)
    assert pytest.approx(cf.sum()) == 12000
    assert pytest.approx(cf.iloc[0]) == 1000

def test_office_opex_item_variable(sample_timeline):
    opex = OfficeOpExItem(
        name="Test Var OpEx",
        timeline=sample_timeline,
        value=12000,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        frequency=FrequencyEnum.ANNUAL,
        variable_ratio=0.5
    )
    cf = opex.compute_cf(occupancy_rate=0.8)
    # Expected monthly = (1000 * 0.5 fixed) + (1000 * 0.5 variable * 0.8 occupancy) = 500 + 400 = 900
    assert pytest.approx(cf.iloc[0]) == 900
    assert pytest.approx(cf.sum()) == 900 * 12

def test_office_opex_item_with_growth(sample_timeline):
    opex = OfficeOpExItem(
        name="Growing OpEx",
        timeline=sample_timeline,
        value=1000,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        frequency=FrequencyEnum.MONTHLY,
        growth_rate=GrowthRate(name="Test Growth", value=0.12) # 12% annual -> 1% monthly
    )
    cf = opex.compute_cf()
    # First month is 1000. Second month is 1000 * 1.01 = 1010
    assert pytest.approx(cf.iloc[0]) == 1000
    assert pytest.approx(cf.iloc[1]) == 1010
    assert cf.sum() > 12000 # Should be greater than flat 12k

def test_expenses_container(sample_timeline):
    opex1 = OfficeOpExItem(name="CAM", value=10, unit_of_measure="per_unit", frequency="annual", timeline=sample_timeline)
    capex1 = OfficeCapExItem(name="Roof", value={"2024-06-01": 50000}, unit_of_measure=UnitOfMeasureEnum.CURRENCY, timeline=sample_timeline)
    expenses = OfficeExpenses(
        operating_expenses=[opex1],
        capital_expenses=[capex1]
    )
    assert len(expenses.operating_expenses) == 1
    assert len(expenses.capital_expenses) == 1
