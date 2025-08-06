# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.analysis import AnalysisContext
from performa.asset.office.misc_income import OfficeMiscIncome
from performa.asset.office.property import OfficeProperty
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    RevenueSubcategoryEnum,
    Timeline,
)


@pytest.fixture
def sample_context() -> AnalysisContext:
    """Provides a basic analysis context for tests."""
    timeline = Timeline.from_dates(
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
    )
    property_data = OfficeProperty.model_construct(net_rentable_area=1.0)
    return AnalysisContext(
        timeline=timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        resolved_lookups={},
        recovery_states={},
    )


def test_office_misc_income_compute_cf(sample_context: AnalysisContext):
    """Test the basic compute_cf for miscellaneous income."""
    misc_income = OfficeMiscIncome(
        name="Parking Income",
        timeline=sample_context.timeline,
        value=12000.0,
        frequency=FrequencyEnum.ANNUAL,
        subcategory=RevenueSubcategoryEnum.MISC,
    )
    cf = misc_income.compute_cf(context=sample_context)
    assert isinstance(cf, pd.Series)
    assert cf.sum() == pytest.approx(12000.0)
    assert cf.iloc[0] == pytest.approx(1000.0)
