# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import pytest

from performa.analysis import AnalysisContext
from performa.asset.office.expense import (
    OfficeCapExItem,
    OfficeExpenses,
    OfficeOpExItem,
)
from performa.asset.office.loss import (
    OfficeCreditLoss,
    OfficeGeneralVacancyLoss,
    OfficeLosses,
)
from performa.asset.office.property import OfficeProperty
from performa.asset.office.rent_roll import OfficeRentRoll
from performa.core.ledger import LedgerBuilder, LedgerGenerationSettings
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    PercentageGrowthRate,
    PropertyAttributeKey,
    Timeline,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))


@pytest.fixture
def sample_context(sample_timeline: Timeline) -> AnalysisContext:    
    property_data = OfficeProperty(
        name="Test Property",
        gross_area=1200.0,
        net_rentable_area=1000.0,
        uid="550e8400-e29b-41d4-a716-446655440008",
        rent_roll=OfficeRentRoll(leases=[], vacant_suites=[]),
        losses=OfficeLosses(
            general_vacancy=OfficeGeneralVacancyLoss(
                vacancy_rate=0.05,
                applied_to_base_rent=True
            ),
            credit_loss=OfficeCreditLoss(
                loss_rate=0.01,
                applied_to_base_rent=True
            )
        ),
        expenses=OfficeExpenses()
    )
    ledger_builder = LedgerBuilder(settings=LedgerGenerationSettings())
    return AnalysisContext(
        timeline=sample_timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        ledger_builder=ledger_builder,
    )


def test_office_opex_item_compute_cf(sample_context: AnalysisContext):
    """Test basic cash flow calculation for an office opex item."""
    opex = OfficeOpExItem(
        name="Test Expense",
        timeline=sample_context.timeline,
        value=1200.0,
        frequency=FrequencyEnum.ANNUAL,
    )
    cf = opex.compute_cf(context=sample_context)
    assert isinstance(cf, pd.Series)
    assert cf.sum() == pytest.approx(1200.0)
    assert cf.iloc[0] == pytest.approx(100.0)


def test_opex_with_nra_reference(sample_context: AnalysisContext):
    """Test PER_UNIT calculation which relies on context."""
    opex = OfficeOpExItem(
        name="Test Expense PSF",
        timeline=sample_context.timeline,
        value=1.5,  # $/sf/yr
        reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        frequency=FrequencyEnum.ANNUAL,
    )
    cf = opex.compute_cf(context=sample_context)
    # 1.5 $/sf/yr * 1000 sf = 1500 $/yr
    assert cf.sum() == pytest.approx(1500.0)
    assert cf.iloc[0] == pytest.approx(125.0)


def test_opex_with_growth(sample_context: AnalysisContext):
    """Test cash flow with a growth rate applied."""
    opex = OfficeOpExItem(
        name="Test Growing Expense",
        timeline=sample_context.timeline,
        value=100.0,
        frequency=FrequencyEnum.MONTHLY,
        growth_rate=PercentageGrowthRate(
            name="Test Growth", value=0.12
        ),  # 12% annual -> 1% monthly
    )
    cf = opex.compute_cf(context=sample_context)
    assert cf.iloc[0] == pytest.approx(100.0 * 1.01)
    assert cf.iloc[1] == pytest.approx(100.0 * 1.01 * 1.01)
    assert cf.iloc[0] < cf.iloc[-1]


def test_expenses_container(sample_timeline: Timeline):
    opex1 = OfficeOpExItem(
        name="CAM",
        value=10,
        reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        frequency="annual",
        timeline=sample_timeline,
    )
    capex1 = OfficeCapExItem(
        name="Roof", value={"2024-06-01": 50000}, timeline=sample_timeline
    )
    expenses = OfficeExpenses(operating_expenses=[opex1], capital_expenses=[capex1])
    assert len(expenses.operating_expenses) == 1
    assert len(expenses.capital_expenses) == 1
