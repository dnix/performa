# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.analysis import AnalysisContext
from performa.asset.office.lc import CommissionTier, OfficeLeasingCommission
from performa.asset.office.lease import OfficeLease
from performa.asset.office.property import OfficeProperty
from performa.core.primitives import GlobalSettings, PropertyAttributeKey, Timeline


@pytest.fixture
def sample_context() -> AnalysisContext:
    """Provides a basic analysis context for tests."""
    # Start timeline earlier to capture signing payments in late 2023
    timeline = Timeline.from_dates(start_date=date(2023, 11, 1), end_date=date(2028, 12, 31))
    property_data = OfficeProperty.model_construct(net_rentable_area=1.0)
    return AnalysisContext(
        timeline=timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        resolved_lookups={},
        recovery_states={},
    )


@pytest.fixture
def sample_lease() -> OfficeLease:
    """Provides a sample lease with signing_date for testing split payments."""
    from performa.asset.office.lease_spec import OfficeLeaseSpec
    from performa.core.primitives import (
        LeaseTypeEnum,
        ProgramUseEnum,
        UponExpirationEnum,
    )
    
    spec = OfficeLeaseSpec(
        tenant_name="Test Tenant",
        suite="100",
        floor="1",
        area=1000.0,
        use_type=ProgramUseEnum.OFFICE,
        signing_date=date(2023, 11, 15),  # Signed before lease start
        start_date=date(2024, 1, 1),     # Commencement date
        term_months=60,
        base_rent_value=50.0,
        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        lease_type=LeaseTypeEnum.GROSS,
        upon_expiration=UponExpirationEnum.RENEW
    )
    
    timeline = Timeline.from_dates(start_date=spec.start_date, end_date=spec.computed_end_date)
    analysis_start_date = date(2023, 11, 1)  # Analysis starts early enough to capture signing
    return OfficeLease.from_spec(spec=spec, timeline=timeline, analysis_start_date=analysis_start_date)


def test_lc_tiered_calculation(sample_context: AnalysisContext):
    """
    Tests that the tiered leasing commission is calculated correctly.
    """
    lc = OfficeLeasingCommission(
        name="Test Tiered LC",
        timeline=sample_context.timeline,  # Extended timeline (Nov 2023 - Dec 2028)
        value=100000.0,  # Annual rent
        landlord_broker_percentage=0.5,
        tenant_broker_percentage=0.5,
        tiers=[
            CommissionTier(year_start=1, year_end=1, rate=0.04),  # 4% for year 1
            CommissionTier(year_start=2, year_end=3, rate=0.03),  # 3% for years 2-3
            CommissionTier(year_start=4, rate=0.02),             # 2% for years 4-5
        ],
    )

    cf = lc.compute_cf(context=sample_context)
    
    # Calculate actual term length based on timeline
    term_in_years = sample_context.timeline.duration_months / 12.0  # ~5.17 years
    
    # Expected calculation:
    # Year 1: 100,000 * 1 * 0.04 = 4,000
    # Year 2-3: 100,000 * 2 * 0.03 = 6,000
    # Year 4-5.17: 100,000 * 2.17 * 0.02 = 4,333.33
    # Total = 14,333.33
    
    assert cf.sum() == pytest.approx(14333.33, rel=1e-2)
    assert cf.iloc[0] == pytest.approx(14333.33, rel=1e-2)
    assert cf.iloc[1] == 0.0


def test_lc_partial_term(sample_context: AnalysisContext):
    """
    Tests that the tiered calculation correctly handles a lease term
    that is not a whole number of years.
    """
    # Create a 3.5 year timeline (42 months)
    timeline = Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2027, 6, 30))
    
    lc = OfficeLeasingCommission(
        name="Test Partial Term LC",
        timeline=timeline,
        value=100000.0,  # Annual rent
        landlord_broker_percentage=0.5,
        tenant_broker_percentage=0.5,
        tiers=[
            CommissionTier(year_start=1, year_end=1, rate=0.04),  # 4% for year 1
            CommissionTier(year_start=2, rate=0.02),             # 2% for years 2-3.5
        ],
    )

    cf = lc.compute_cf(context=sample_context)
    
    # Expected calculation:
    # Year 1: 100,000 * 1.0 * 0.04 = 4,000
    # Year 2-3.5 (2.5 years): 100,000 * 2.5 * 0.02 = 5,000
    # Total = 9,000
    
    assert cf.sum() == pytest.approx(9000.0)


def test_commission_tier_split_payment_validation():
    """Test that CommissionTier validates payment percentage splits."""
    # Valid: 50/50 split
    tier = CommissionTier(
        year_start=1, year_end=5, rate=0.06,
        signing_percentage=0.5, commencement_percentage=0.5
    )
    assert tier.signing_percentage == 0.5
    assert tier.commencement_percentage == 0.5
    
    # Valid: 100% at signing (default)
    tier_default = CommissionTier(year_start=1, year_end=5, rate=0.06)
    assert tier_default.signing_percentage == 1.0
    assert tier_default.commencement_percentage == 0.0
    
    # Invalid: percentages don't sum to 1.0
    with pytest.raises(ValueError, match="Payment percentages must sum to 1.0"):
        CommissionTier(
            year_start=1, year_end=5, rate=0.06,
            signing_percentage=0.6, commencement_percentage=0.5  # Sum = 1.1
        )


def test_lc_split_payment_timing(sample_context: AnalysisContext, sample_lease: OfficeLease):
    """Test LC with split payments between signing and commencement."""
    lc = OfficeLeasingCommission(
        name="Split Payment LC",
        timeline=sample_context.timeline,  # Use the extended timeline
        value=100000.0,  # Annual rent
        landlord_broker_percentage=0.5,
        tenant_broker_percentage=0.5,
        tiers=[
            CommissionTier(
                year_start=1, year_end=5, rate=0.06,
                signing_percentage=0.5,      # 50% at signing
                commencement_percentage=0.5  # 50% at commencement
            )
        ],
    )
    
    # Set lease context for date-based timing
    sample_context.current_lease = sample_lease
    cf = lc.compute_cf(context=sample_context)
    
    # Expected calculation:
    # Total commission: 100,000 * 5 * 0.06 = 30,000
    # 50% at signing (Nov 2023): 15,000
    # 50% at commencement (Jan 2024): 15,000
    
    assert cf.sum() == pytest.approx(30000.0)
    
    # Check that payments occur in correct periods
    # Signing payment should occur in Nov 2023
    nov_2023 = pd.Period("2023-11", freq="M")
    # Commencement payment should occur in Jan 2024  
    jan_2024 = pd.Period("2024-01", freq="M")
    
    if nov_2023 in cf.index:
        assert cf[nov_2023] == pytest.approx(15000.0)
    if jan_2024 in cf.index:
        assert cf[jan_2024] == pytest.approx(15000.0)


def test_lc_multiple_tiers_different_payment_schedules(sample_context: AnalysisContext, sample_lease: OfficeLease):
    """Test LC with multiple tiers having different payment timing."""
    lc = OfficeLeasingCommission(
        name="Multi-Tier Split LC",
        timeline=sample_context.timeline,  # Use the extended timeline
        value=100000.0,  # Annual rent
        landlord_broker_percentage=0.5,
        tenant_broker_percentage=0.5,
        tiers=[
            # Years 1-3: 50/50 split
            CommissionTier(
                year_start=1, year_end=3, rate=0.06,
                signing_percentage=0.5, commencement_percentage=0.5
            ),
            # Years 4-5: 100% at signing
            CommissionTier(
                year_start=4, year_end=5, rate=0.03,
                signing_percentage=1.0, commencement_percentage=0.0
            )
        ],
    )
    
    # Set lease context for date-based timing
    sample_context.current_lease = sample_lease
    cf = lc.compute_cf(context=sample_context)
    
    # Expected calculation:
    # Tier 1 (Years 1-3): 100,000 * 3 * 0.06 = 18,000
    #   - 50% at signing: 9,000
    #   - 50% at commencement: 9,000
    # Tier 2 (Years 4-5): 100,000 * 2 * 0.03 = 6,000
    #   - 100% at signing: 6,000
    # Total: 24,000
    
    assert cf.sum() == pytest.approx(24000.0)


def test_lc_split_payment_without_signing_date_error(sample_context: AnalysisContext):
    """Test that LC requiring signing payment fails when no signing_date provided."""
    lc = OfficeLeasingCommission(
        name="Signing Required LC",
        timeline=sample_context.timeline,
        value=100000.0,
        landlord_broker_percentage=0.5,
        tenant_broker_percentage=0.5,
        tiers=[
            CommissionTier(
                year_start=1, year_end=5, rate=0.06,
                signing_percentage=1.0,  # Requires signing date
                commencement_percentage=0.0
            )
        ],
    )
    
    # Create a lease without signing_date
    from performa.asset.office.lease_spec import OfficeLeaseSpec
    from performa.core.primitives import (
        LeaseTypeEnum,
        ProgramUseEnum,
        UponExpirationEnum,
    )
    
    spec_no_signing = OfficeLeaseSpec(
        tenant_name="Test Tenant",
        suite="100",
        floor="1",
        area=1000.0,
        use_type=ProgramUseEnum.OFFICE,
        signing_date=None,  # No signing date
        start_date=date(2024, 1, 1),
        term_months=60,
        base_rent_value=50.0,
        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        lease_type=LeaseTypeEnum.GROSS,
        upon_expiration=UponExpirationEnum.RENEW
    )
    
    timeline = Timeline.from_dates(start_date=spec_no_signing.start_date, end_date=spec_no_signing.computed_end_date)
    analysis_start_date = date(2023, 11, 1)  # Analysis starts early enough to capture signing
    lease_no_signing = OfficeLease.from_spec(spec=spec_no_signing, timeline=timeline, analysis_start_date=analysis_start_date)
    
    # Set lease context without signing date
    sample_context.current_lease = lease_no_signing
    
    # Should raise error when trying to compute with signing-based payment
    with pytest.raises(ValueError, match="LC tier requires signing payment but no signing_date provided"):
        lc.compute_cf(context=sample_context)


def test_lc_backward_compatibility_without_lease_context(sample_context: AnalysisContext):
    """Test that LC still works without lease context (backward compatibility)."""
    lc = OfficeLeasingCommission(
        name="Traditional LC",
        timeline=sample_context.timeline,
        value=100000.0,
        landlord_broker_percentage=0.5,
        tenant_broker_percentage=0.5,
        tiers=[
            CommissionTier(year_start=1, year_end=5, rate=0.06)  # Default: 100% at signing
        ],
    )
    
    # Don't set current_lease - should fall back to timeline logic
    sample_context.current_lease = None
    cf = lc.compute_cf(context=sample_context)
    
    # Expected: 100,000 * 5 * 0.06 = 30,000 at first period
    assert cf.sum() == pytest.approx(30000.0)
    assert cf.iloc[0] == pytest.approx(30000.0)  # All payment in first period
