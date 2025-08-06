# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pytest

from performa.core.base import (
    CommissionTier,
    LeasingCommissionBase,
    TenantImprovementAllowanceBase,
)
from performa.core.primitives import (
    PropertyAttributeKey,
    Timeline,
)


@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)


def test_leasing_commission_base_instantiation(sample_timeline: Timeline):
    """Test successful instantiation of LeasingCommissionBase."""
    item = LeasingCommissionBase(
        name="Standard LC",
        timeline=sample_timeline,
        value=0,  # Simplified for base test
        tiers=[CommissionTier(year_start=1, year_end=5, rate=0.06)],
    )
    assert item.name == "Standard LC"


def test_tenant_improvement_allowance_base_instantiation(sample_timeline: Timeline):
    """Test successful instantiation of TenantImprovementAllowanceBase."""
    item = TenantImprovementAllowanceBase(
        name="Standard TI",
        timeline=sample_timeline,
        value=50.0,
        reference=PropertyAttributeKey.NET_RENTABLE_AREA,
    )
    assert item.name == "Standard TI"


def test_payment_timing(sample_context):
    """
    Tests that the payment_timing field correctly places the cash flow
    at signing (month 0) or commencement (month 1) for base cost models.
    """
    context = sample_context(timeline_duration=24)

    # Test 1: TI at Signing
    ti_signing = TenantImprovementAllowanceBase(
        name="Test TI Signing",
        timeline=context.timeline,
        value=10000.0,
        payment_timing="signing",
    )
    cf_signing = ti_signing.compute_cf(context=context)
    assert cf_signing.iloc[0] == 10000.0
    assert cf_signing.iloc[1] == 0.0
    assert cf_signing.sum() == 10000.0

    # Test 2: TI at Commencement
    ti_commencement = TenantImprovementAllowanceBase(
        name="Test TI Commencement",
        timeline=context.timeline,
        value=20000.0,
        payment_timing="commencement",
    )
    cf_commencement = ti_commencement.compute_cf(context=context)
    assert cf_commencement.iloc[0] == 0.0
    assert cf_commencement.iloc[1] == 20000.0
    assert cf_commencement.sum() == 20000.0

    # Test 3: LC at Signing
    lc_signing = LeasingCommissionBase(
        name="Test LC Signing",
        timeline=context.timeline,
        value=5000.0,
        payment_timing="signing",
    )
    cf_lc_signing = lc_signing.compute_cf(context=context)
    assert cf_lc_signing.iloc[0] == 5000.0
    assert cf_lc_signing.sum() == 5000.0

    # Test 4: LC at Commencement (should still be month 0 as per base logic)
    lc_commencement = LeasingCommissionBase(
        name="Test LC Commencement",
        timeline=context.timeline,
        value=6000.0,
        payment_timing="commencement",
    )
    cf_lc_commencement = lc_commencement.compute_cf(context=context)
    assert cf_lc_commencement.iloc[0] == 6000.0
    assert cf_lc_commencement.sum() == 6000.0
