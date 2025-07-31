# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.analysis import AnalysisContext
from performa.asset.office.property import OfficeProperty
from performa.asset.office.ti import OfficeTenantImprovement
from performa.core.primitives import GlobalSettings, PropertyAttributeKey, Timeline


@pytest.fixture
def sample_context() -> AnalysisContext:
    """Provides a basic analysis context for tests."""
    timeline = Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2028, 12, 31))
    property_data = OfficeProperty.model_construct(net_rentable_area=1.0)
    return AnalysisContext(
        timeline=timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        resolved_lookups={},
        recovery_states={},
    )


def test_ti_compute_cf_upfront(sample_context: AnalysisContext):
    """Test the TI compute_cf for a simple upfront payment."""
    ti = OfficeTenantImprovement(
        name="Test TI",
        timeline=sample_context.timeline,
        value=10000.0,
        payment_timing="signing",
    )
    cf = ti.compute_cf(context=sample_context)
    assert isinstance(cf, pd.Series)
    assert cf.sum() == 10000.0
    assert cf.iloc[0] == 10000.0
    assert cf.iloc[1] == 0.0

def test_ti_compute_cf_amortized(sample_context: AnalysisContext):
    """Test the TI compute_cf for an amortized payment."""
    ti = OfficeTenantImprovement(
        name="Amortized TI",
        timeline=sample_context.timeline,
        value=12000.0,
        payment_method="amortized",
        payment_timing="commencement",
        interest_rate=0.0,
        amortization_term_months=12,
    )
    cf = ti.compute_cf(context=sample_context)
    assert cf.sum() == pytest.approx(12000.0)
    assert cf.iloc[0] == pytest.approx(1000.0)
    assert cf.iloc[11] == pytest.approx(1000.0)
    assert cf.iloc[12] == 0.0

def test_ti_payment_timing(sample_context: AnalysisContext):
    """
    Tests that the payment_timing field correctly places the cash flow
    at signing (month 0) or commencement (month 1).
    """
    # Test 1: Payment at Signing
    ti_signing = OfficeTenantImprovement(
        name="Test TI Signing",
        timeline=sample_context.timeline,
        value=10000.0,
        payment_timing="signing",
    )
    cf_signing = ti_signing.compute_cf(context=sample_context)
    assert cf_signing.iloc[0] == 10000.0
    assert cf_signing.iloc[1] == 0.0
    assert cf_signing.sum() == 10000.0

    # Test 2: Payment at Commencement
    ti_commencement = OfficeTenantImprovement(
        name="Test TI Commencement",
        timeline=sample_context.timeline,
        value=20000.0,
        payment_timing="commencement",
    )
    cf_commencement = ti_commencement.compute_cf(context=sample_context)
    assert cf_commencement.iloc[0] == 0.0
    assert cf_commencement.iloc[1] == 20000.0
    assert cf_commencement.sum() == 20000.0
