from __future__ import annotations

from datetime import date

import pytest

from performa.common.base import (
    CommissionTier,
    LeasingCommissionBase,
    TenantImprovementAllowanceBase,
)
from performa.common.primitives import Timeline, UnitOfMeasureEnum


@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)

def test_leasing_commission_base_instantiation(sample_timeline: Timeline):
    """Test successful instantiation of LeasingCommissionBase."""
    item = LeasingCommissionBase(
        name="Standard LC",
        timeline=sample_timeline,
        value=0, # Simplified for base test
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        tiers=[CommissionTier(year_start=1, year_end=5, rate=0.06)],
    )
    assert item.name == "Standard LC"

def test_tenant_improvement_allowance_base_instantiation(sample_timeline: Timeline):
    """Test successful instantiation of TenantImprovementAllowanceBase."""
    item = TenantImprovementAllowanceBase(
        name="Standard TI",
        timeline=sample_timeline,
        value=50.0,
        unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
    )
    assert item.name == "Standard TI"
