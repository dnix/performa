# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import date
from uuid import uuid4

import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from performa.analysis import AnalysisContext
from performa.asset.office.expense import OfficeOpExItem
from performa.asset.office.lease import OfficeLease
from performa.asset.office.property import OfficeProperty
from performa.asset.office.recovery import ExpensePool, OfficeRecoveryMethod, Recovery
from performa.core.base import RecoveryCalculationState
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseStatusEnum,
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def sample_timeline() -> Timeline:
    """A 10-year timeline fixture."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=120)


@pytest.fixture
def sample_lease(sample_timeline: Timeline) -> OfficeLease:
    """A sample lease fixture."""
    lease_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=60)
    return OfficeLease(
        timeline=lease_timeline,
        name="Test Lease",
        suite="100",
        floor="1",
        status=LeaseStatusEnum.CONTRACT,
        area=1000.0,
        value=50.0,
        unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
        frequency=FrequencyEnum.ANNUAL,
        upon_expiration=UponExpirationEnum.MARKET,
    )


@pytest.fixture
def sample_opex_items(sample_timeline: Timeline) -> dict[str, OfficeOpExItem]:
    """Fixture for a dictionary of sample operating expense items."""
    taxes = OfficeOpExItem(
        name="Taxes",
        timeline=sample_timeline,
        value=300000.0,
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        frequency=FrequencyEnum.ANNUAL,
        recoverable_ratio=1.0,
        growth_rate=None,
    )
    cam = OfficeOpExItem(
        name="CAM",
        timeline=sample_timeline,
        value=5.0,
        unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
        frequency=FrequencyEnum.ANNUAL,
        variable_ratio=0.5,
        recoverable_ratio=1.0,
        growth_rate=None,
    )
    return {"taxes": taxes, "cam": cam}


@pytest.fixture
def pre_populated_context(
    sample_timeline: Timeline, sample_opex_items: dict[str, OfficeOpExItem]
) -> AnalysisContext:
    property_data = OfficeProperty.model_construct(net_rentable_area=20000.0)
    context = AnalysisContext(
        timeline=sample_timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        resolved_lookups={},
        recovery_states={},
    )
    for item in sample_opex_items.values():
        context.resolved_lookups[item.uid] = item.compute_cf(context=context)
    return context


def test_recovery_net(
    pre_populated_context: AnalysisContext,
    sample_lease: OfficeLease,
    sample_opex_items: dict[str, OfficeOpExItem],
):
    taxes = sample_opex_items["taxes"]
    cam = sample_opex_items["cam"]
    expense_pool = ExpensePool(name="All Expenses", expenses=[taxes, cam])
    recovery_item = Recovery(structure="net", expenses=expense_pool)
    pre_populated_context.recovery_states[recovery_item.uid] = RecoveryCalculationState(
        recovery_uid=recovery_item.uid
    )
    recovery_method = OfficeRecoveryMethod(
        name="Net Recovery", recoveries=[recovery_item], gross_up=False
    )
    recovery_cf = recovery_method.compute_cf(
        context=pre_populated_context, lease=sample_lease
    )
    
    total_monthly_expense = (
        pre_populated_context.resolved_lookups[taxes.uid].iloc[0] +
        pre_populated_context.resolved_lookups[cam.uid].iloc[0]
    )
    pro_rata_share = sample_lease.area / pre_populated_context.property_data.net_rentable_area
    expected_recovery = total_monthly_expense * pro_rata_share
    expected_series = pd.Series(expected_recovery, index=recovery_cf.index)
    assert_series_equal(recovery_cf, expected_series, check_exact=False)


def test_recovery_base_stop(
    pre_populated_context: AnalysisContext,
    sample_lease: OfficeLease,
    sample_opex_items: dict[str, OfficeOpExItem],
):
    taxes = sample_opex_items["taxes"]
    cam = sample_opex_items["cam"]
    base_stop_psf = 10.0
    expense_pool = ExpensePool(name="All Expenses", expenses=[taxes, cam])
    recovery_item = Recovery(
        structure="base_stop",
        expenses=expense_pool,
        base_amount=base_stop_psf,
        base_amount_unit="psf",
    )
    pre_populated_context.recovery_states[recovery_item.uid] = RecoveryCalculationState(
        recovery_uid=recovery_item.uid
    )
    recovery_method = OfficeRecoveryMethod(
        name="Base Stop Recovery", recoveries=[recovery_item], gross_up=False
    )
    recovery_cf = recovery_method.compute_cf(
        context=pre_populated_context, lease=sample_lease
    )

    total_monthly_expense = (
        pre_populated_context.resolved_lookups[taxes.uid].iloc[0] +
        pre_populated_context.resolved_lookups[cam.uid].iloc[0]
    )
    pro_rata_share = sample_lease.area / pre_populated_context.property_data.net_rentable_area
    tenant_total_expense_share = total_monthly_expense * pro_rata_share
    monthly_stop = (base_stop_psf * sample_lease.area) / 12.0
    expected_recovery = float(max(0, tenant_total_expense_share - monthly_stop))
    
    expected_series = pd.Series(expected_recovery, index=recovery_cf.index)
    assert_series_equal(recovery_cf, expected_series, check_exact=False)
    assert recovery_cf.sum() > 0


def test_recovery_gross_up(
    pre_populated_context: AnalysisContext,
    sample_lease: OfficeLease,
    sample_opex_items: dict[str, OfficeOpExItem],
):
    occupancy = pd.Series(1.0, index=pre_populated_context.timeline.period_index)
    occupancy.loc[pd.Period("2024-06", "M")] = 0.80
    pre_populated_context.occupancy_rate_series = occupancy

    cam = sample_opex_items["cam"]
    expense_pool = ExpensePool(name="CAM Pool", expenses=[cam])
    recovery_item = Recovery(structure="net", expenses=expense_pool)
    pre_populated_context.recovery_states[recovery_item.uid] = RecoveryCalculationState(
        recovery_uid=recovery_item.uid
    )
    recovery_method = OfficeRecoveryMethod(
        name="Gross-up Recovery",
        recoveries=[recovery_item],
        gross_up=True,
        gross_up_percent=0.95,
    )
    recovery_cf = recovery_method.compute_cf(
        context=pre_populated_context, lease=sample_lease
    )

    pro_rata_share = sample_lease.area / pre_populated_context.property_data.net_rentable_area
    cam_raw_cf = pre_populated_context.resolved_lookups[cam.uid]
    
    # Normal month
    expected_normal_recovery = cam_raw_cf.loc[pd.Period("2024-05", "M")] * pro_rata_share
    assert recovery_cf.loc[pd.Period("2024-05", "M")] == pytest.approx(expected_normal_recovery)

    # Gross-up month
    raw_monthly_expense = cam_raw_cf.loc[pd.Period("2024-06", "M")]
    fixed_part = raw_monthly_expense * (1.0 - cam.variable_ratio)
    variable_part = raw_monthly_expense * cam.variable_ratio
    grossed_up_variable_part = variable_part / 0.80
    expected_grossed_up_monthly_expense = fixed_part + grossed_up_variable_part
    expected_gross_up_recovery = expected_grossed_up_monthly_expense * pro_rata_share

    assert recovery_cf.loc[pd.Period("2024-06", "M")] == pytest.approx(expected_gross_up_recovery)
    assert recovery_cf.loc[pd.Period("2024-06", "M")] > recovery_cf.loc[pd.Period("2024-05", "M")]
