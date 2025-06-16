from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.asset.office.lc import OfficeLeasingCommission
from performa.common.base import CommissionTier
from performa.common.primitives import Timeline, UnitOfMeasureEnum


@pytest.fixture
def sample_timeline():
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2028, 12, 31))

def test_lc_tiered_full_years(sample_timeline):
    lc = OfficeLeasingCommission(
        name="Tiered LC Full Years",
        timeline=sample_timeline,
        value=200000, # Annual Rent
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        tiers=[
            CommissionTier(year_start=1, year_end=1, rate=0.06),
            CommissionTier(year_start=2, year_end=5, rate=0.03),
        ]
    )
    cf = lc.compute_cf()
    # Year 1: 200000 * 1 * 0.06 = 12000
    # Year 2-5 (4 years): 200000 * 4 * 0.03 = 24000
    # Total = 12000 + 24000 = 36000
    assert pytest.approx(cf.sum()) == 36000
    assert cf[pd.Period("2024-01", freq="M")] == 36000

def test_lc_open_ended_tier(sample_timeline):
    lc = OfficeLeasingCommission(
        name="Tiered LC Open End",
        timeline=sample_timeline,
        value=100000, # Annual Rent
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        tiers=[
            CommissionTier(year_start=1, year_end=2, rate=0.05),
            CommissionTier(year_start=3, rate=0.02), # Open ended
        ]
    )
    cf = lc.compute_cf()
    # Year 1-2 (2 years): 100000 * 2 * 0.05 = 10000
    # Year 3-5 (3 years): 100000 * 3 * 0.02 = 6000
    # Total = 10000 + 6000 = 16000
    assert pytest.approx(cf.sum()) == 16000
