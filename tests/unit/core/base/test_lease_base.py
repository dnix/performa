# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date
from typing import Dict

import pandas as pd
import pytest

from performa.analysis import AnalysisContext
from performa.core.base import LeaseBase, LeaseSpecBase
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseStatusEnum,
    PropertyAttributeKey,
    Timeline,
    UponExpirationEnum,
)

# --- LeaseSpecBase Tests ---


def test_lease_spec_base_valid_instantiation():
    """Test successful instantiation of LeaseSpecBase with valid data."""
    spec = LeaseSpecBase(
        tenant_name="Test Tenant",
        suite="101",
        floor="1",
        area=1000,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        base_rent_value=50.0,
        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
    )
    assert spec.tenant_name == "Test Tenant"


def test_lease_spec_base_term_validation():
    """Test validation logic for signing_date validation."""
    # Fails if signing_date is after start_date
    with pytest.raises(
        ValueError, match="signing_date must be on or before start_date"
    ):
        LeaseSpecBase(
            tenant_name="Test",
            suite="1",
            floor="1",
            area=1,
            start_date=date(2024, 1, 1),
            signing_date=date(2024, 2, 1),  # After start_date
            end_date=date(2024, 12, 31),
            base_rent_value=1,
        )


def test_lease_spec_computed_end_date():
    """Test the computed_end_date property."""
    # From end_date
    spec1 = LeaseSpecBase(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        tenant_name="T",
        suite="s",
        floor="f",
        area=1,
        base_rent_value=1,
    )
    assert spec1.computed_end_date == date(2024, 12, 31)

    # From term_months
    spec2 = LeaseSpecBase(
        start_date=date(2024, 1, 1),
        term_months=12,
        tenant_name="T",
        suite="s",
        floor="f",
        area=1,
        base_rent_value=1,
    )
    assert spec2.computed_end_date == date(2024, 12, 31)


# --- LeaseBase Tests ---


class ConcreteLease(LeaseBase):
    """A concrete implementation of LeaseBase for testing."""

    def compute_cf(self, context: AnalysisContext) -> Dict[str, pd.Series]:
        if isinstance(self.value, (int, float)):
            base_rent = pd.Series(self.value, index=self.timeline.period_index)
            return {"base_rent": base_rent}
        # This implementation doesn't handle Series, demonstrating the principle
        raise NotImplementedError("This test helper only supports scalar rent value.")

    def project_future_cash_flows(self, context: AnalysisContext) -> pd.DataFrame:
        return pd.DataFrame(self.compute_cf(context))


@pytest.fixture
def sample_timeline() -> Timeline:
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
    return timeline


@pytest.fixture
def sample_lease() -> LeaseBase:
    """Provides a sample LeaseBase fixture for tests."""
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
    return ConcreteLease(
        name="Test Lease",
        timeline=timeline,
        status=LeaseStatusEnum.CONTRACT,
        area=1000.0,
        suite="100",
        floor="1",
        upon_expiration=UponExpirationEnum.MARKET,
        value=50 * 1000 / 12,  # Monthly amount
        frequency=FrequencyEnum.MONTHLY,
    )


@pytest.fixture
def sample_context(sample_lease: LeaseBase) -> AnalysisContext:
    return AnalysisContext(
        timeline=sample_lease.timeline,
        settings=GlobalSettings(),
        property_data=None,
        resolved_lookups={},
        recovery_states={},
    )


def test_lease_base_instantiation(sample_lease: LeaseBase):
    assert sample_lease.name == "Test Lease"
    assert sample_lease.area == 1000.0


def test_lease_base_compute_cf_structure(
    sample_lease: LeaseBase, sample_context: AnalysisContext
):
    result = sample_lease.compute_cf(context=sample_context)
    assert isinstance(result, dict)
    assert "base_rent" in result
    assert isinstance(result["base_rent"], pd.Series)


def test_lease_base_compute_cf_base_rent_calculation(
    sample_lease: LeaseBase, sample_context: AnalysisContext
):
    """Test the base rent calculation logic within compute_cf."""
    result1 = sample_lease.compute_cf(context=sample_context)
    assert result1["base_rent"].iloc[0] == pytest.approx(50 * 1000 / 12)
