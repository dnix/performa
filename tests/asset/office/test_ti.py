from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.asset.office.ti import OfficeTenantImprovement
from performa.common.primitives import Timeline, UnitOfMeasureEnum


@pytest.fixture
def sample_timeline():
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2028, 12, 31))

def test_ti_upfront(sample_timeline):
    ti = OfficeTenantImprovement(
        name="Upfront TI",
        timeline=sample_timeline,
        value=50000,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        payment_method="upfront",
    )
    cf = ti.compute_cf()
    assert cf.sum() == 50000
    assert cf[pd.Period("2024-01", freq="M")] == 50000
    assert cf.where(cf != 0).count() == 1

def test_ti_amortized(sample_timeline):
    ti = OfficeTenantImprovement(
        name="Amortized TI",
        timeline=sample_timeline,
        value=60000,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        payment_method="amortized",
        interest_rate=0.05,
        amortization_term_months=60
    )
    cf = ti.compute_cf()
    # 60000 at 5% for 60 months is $1132.27/mo
    assert pytest.approx(cf.sum(), abs=1) == 1132.27 * 60
    assert pytest.approx(cf[pd.Period("2024-01", freq="M")], abs=0.01) == 1132.27
    assert cf[pd.Period("2028-12", freq="M")] > 0 # Should still be paying in the last month
    assert len(cf[cf > 0]) == 60

def test_ti_amortized_no_interest(sample_timeline):
    ti = OfficeTenantImprovement(
        name="Amortized TI No Interest",
        timeline=sample_timeline,
        value=60000,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        payment_method="amortized",
        interest_rate=0.0,
        amortization_term_months=60
    )
    cf = ti.compute_cf()
    assert pytest.approx(cf.sum()) == 60000
    assert pytest.approx(cf[pd.Period("2024-01", freq="M")]) == 1000.0
