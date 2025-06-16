from __future__ import annotations

from datetime import date

import pytest

from performa.asset.office.misc_income import OfficeMiscIncome
from performa.common.primitives import FrequencyEnum, Timeline, UnitOfMeasureEnum


@pytest.fixture
def sample_timeline():
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))

def test_office_misc_income_compute_cf(sample_timeline):
    misc_income = OfficeMiscIncome(
        name="Test Misc Income",
        timeline=sample_timeline,
        value=6000,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        frequency=FrequencyEnum.ANNUAL,
    )
    cf = misc_income.compute_cf()
    assert pytest.approx(cf.sum()) == 6000
    assert pytest.approx(cf.iloc[0]) == 500
