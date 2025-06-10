from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.common.base._lease_base import LeaseBase, LeaseSpecBase
from performa.common.primitives import (
    FrequencyEnum,
    LeaseStatusEnum,
    ProgramUseEnum,
    Timeline,
    UnitOfMeasureEnum,
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
        use_type=ProgramUseEnum.OFFICE,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        base_rent_value=50.0,
        base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
        upon_expiration=UponExpirationEnum.MARKET,
    )
    assert spec.tenant_name == "Test Tenant"

def test_lease_spec_base_term_validation():
    """Test validation logic for term (end_date vs term_months)."""
    # Fails if neither end_date nor term_months is provided
    with pytest.raises(ValueError, match="Either end_date or term_months must be provided"):
        LeaseSpecBase(
            tenant_name="Test", suite="1", floor="1", area=1, use_type="office",
            start_date=date(2024, 1, 1), base_rent_value=1, base_rent_unit_of_measure="currency",
            upon_expiration="market"
        )
    
    # Fails if end_date is before start_date
    with pytest.raises(ValueError, match="end_date must be after start_date"):
        LeaseSpecBase(
            tenant_name="Test", suite="1", floor="1", area=1, use_type="office",
            start_date=date(2024, 1, 1), end_date=date(2023, 12, 31),
            base_rent_value=1, base_rent_unit_of_measure="currency", upon_expiration="market"
        )

def test_lease_spec_computed_end_date():
    """Test the computed_end_date property."""
    # From end_date
    spec1 = LeaseSpecBase(
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
        tenant_name="T", suite="s", floor="f", area=1, use_type="office", base_rent_value=1,
        base_rent_unit_of_measure="currency", upon_expiration="market"
    )
    assert spec1.computed_end_date == date(2024, 12, 31)

    # From term_months
    spec2 = LeaseSpecBase(
        start_date=date(2024, 1, 1), term_months=12,
        tenant_name="T", suite="s", floor="f", area=1, use_type="office", base_rent_value=1,
        base_rent_unit_of_measure="currency", upon_expiration="market"
    )
    assert spec2.computed_end_date == date(2024, 12, 31)


# --- LeaseBase Tests ---

@pytest.fixture
def sample_lease() -> LeaseBase:
    """Provides a sample LeaseBase fixture for tests."""
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
    return LeaseBase(
        name="Test Lease",
        timeline=timeline,
        status=LeaseStatusEnum.CONTRACT,
        area=1000.0,
        value=50 * 1000 / 12, # Monthly amount
        unit_of_measure=UnitOfMeasureEnum.CURRENCY, # Test with currency first
        frequency=FrequencyEnum.MONTHLY,
    )

def test_lease_base_compute_cf_structure(sample_lease: LeaseBase):
    """Test that compute_cf returns a dictionary with the expected keys."""
    result = sample_lease.compute_cf()
    assert isinstance(result, dict)
    assert "base_rent" in result
    assert "abatement_applied" in result
    assert isinstance(result["base_rent"], pd.Series)
    assert isinstance(result["abatement_applied"], pd.Series)

def test_lease_base_compute_cf_base_rent_calculation(sample_lease: LeaseBase):
    """Test the base rent calculation logic within compute_cf."""
    # Test 1: Monthly currency value (from fixture)
    result1 = sample_lease.compute_cf()
    expected_rent = 50 * 1000 / 12
    pd.testing.assert_series_equal(
        result1["base_rent"],
        pd.Series(expected_rent, index=sample_lease.timeline.period_index, dtype='float64')
    )

    # Test 2: Annual currency value
    lease2 = sample_lease.copy(updates={
        "frequency": FrequencyEnum.ANNUAL,
        "value": 50 * 1000
    })
    result2 = lease2.compute_cf()
    pd.testing.assert_series_equal(
        result2["base_rent"],
        pd.Series(expected_rent, index=sample_lease.timeline.period_index, dtype='float64')
    )

    # Test 3: Per-unit value
    lease3 = sample_lease.copy(updates={
        "unit_of_measure": UnitOfMeasureEnum.PER_UNIT,
        "frequency": FrequencyEnum.ANNUAL,
        "value": 50.0  # $/sf/yr
    })
    result3 = lease3.compute_cf()
    pd.testing.assert_series_equal(
        result3["base_rent"],
        pd.Series(expected_rent, index=sample_lease.timeline.period_index, dtype='float64')
    )

def test_lease_base_compute_cf_raises_for_non_scalar(sample_lease: LeaseBase):
    """Test that compute_cf raises a NotImplementedError for non-scalar rent values."""
    series_val = pd.Series([1000] * 12, index=sample_lease.timeline.period_index)
    lease_with_series = sample_lease.copy(updates={"value": series_val})
    
    with pytest.raises(NotImplementedError, match="only supports scalar rent value"):
        lease_with_series.compute_cf()
