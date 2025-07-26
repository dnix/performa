# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import pytest

from performa.analysis import AnalysisContext
from performa.asset.office.lease import OfficeLease
from performa.asset.office.rollover import (
    OfficeRolloverLeaseTerms,
    OfficeRolloverProfile,
)
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
def sample_global_settings() -> GlobalSettings:
    """Fixture for global settings."""
    return GlobalSettings(analysis_start_date=date(2024, 1, 1))


@pytest.fixture
def sample_analysis_context(sample_global_settings: GlobalSettings) -> AnalysisContext:
    """Fixture for a basic AnalysisContext."""
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=120)
    # In a real test, property_data would be a mock or a sample OfficeProperty
    return AnalysisContext(
        timeline=timeline, settings=sample_global_settings, property_data={}
    )


def create_base_lease_for_rollover_test(
    rollover_profile: OfficeRolloverProfile, upon_expiration: UponExpirationEnum
) -> OfficeLease:
    """Helper function to create a standard lease for rollover tests."""
    lease_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)  # 1-year lease
    return OfficeLease(
        timeline=lease_timeline,
        name="Test Tenant",
        suite="101",
        floor="1",
        status=LeaseStatusEnum.CONTRACT,
        area=1000.0,
        upon_expiration=upon_expiration,
        value=50.0,  # $50/sf
        unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
        frequency=FrequencyEnum.ANNUAL,
        rollover_profile=rollover_profile,
    )


def test_rollover_renew(sample_analysis_context: AnalysisContext):
    """
    Tests that a lease with upon_expiration=RENEW starts the next lease immediately,
    with no vacancy loss and using renewal terms.
    """
    # Arrange
    renewal_terms = OfficeRolloverLeaseTerms(market_rent=55.0, term_months=24)
    market_terms = OfficeRolloverLeaseTerms(market_rent=60.0, term_months=36)
    
    rollover_profile = OfficeRolloverProfile(
        name="Test Renew Profile",
        term_months=24,
        renewal_probability=1.0,  # Not directly used by RENEW, but good practice
        downtime_months=3,  # Should be ignored for RENEW
        market_terms=market_terms,
        renewal_terms=renewal_terms,
        upon_expiration=UponExpirationEnum.RENEW,
    )
    
    lease = create_base_lease_for_rollover_test(
        rollover_profile, upon_expiration=UponExpirationEnum.RENEW
    )

    # Act
    projected_cf_df = lease.project_future_cash_flows(context=sample_analysis_context)

    # Assert
    # 1. No vacancy loss was booked
    assert "vacancy_loss" not in projected_cf_df or projected_cf_df["vacancy_loss"].sum() == 0

    # 2. The new lease starts immediately after the old one.
    # Original lease ends Dec 2024. New lease starts Jan 2025.
    original_lease_end_period = pd.Period("2024-12", freq="M")
    renewal_lease_start_period = pd.Period("2025-01", freq="M")

    rent_in_last_period_of_old_lease = projected_cf_df.loc[original_lease_end_period, "base_rent"]
    rent_in_first_period_of_new_lease = projected_cf_df.loc[renewal_lease_start_period, "base_rent"]
    
    assert rent_in_last_period_of_old_lease > 0
    assert rent_in_first_period_of_new_lease > 0

    # 3. The new rent is based on renewal_terms (55/sf annual -> 55*1000/12 monthly)
    expected_renewal_rent = (55.0 * 1000) / 12
    assert pytest.approx(rent_in_first_period_of_new_lease) == expected_renewal_rent


def test_rollover_vacate(sample_analysis_context: AnalysisContext):
    """
    Tests that a lease with upon_expiration=VACATE correctly applies downtime,
    books vacancy loss, and uses market terms for the next lease.
    """
    # Arrange
    renewal_terms = OfficeRolloverLeaseTerms(market_rent=55.0, term_months=24)
    market_terms = OfficeRolloverLeaseTerms(market_rent=60.0, term_months=36)
    downtime_months = 3

    rollover_profile = OfficeRolloverProfile(
        name="Test Vacate Profile",
        term_months=36,
        renewal_probability=0.0,
        downtime_months=downtime_months,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
        upon_expiration=UponExpirationEnum.VACATE,
    )

    lease = create_base_lease_for_rollover_test(
        rollover_profile, upon_expiration=UponExpirationEnum.VACATE
    )

    # Act
    projected_cf_df = lease.project_future_cash_flows(context=sample_analysis_context)

    # Assert
    # 1. Downtime and vacancy loss are correctly applied.
    # Original lease ends Dec 2024. Downtime is Jan, Feb, Mar 2025. New lease starts Apr 2025.
    downtime_start_period = pd.Period("2025-01", freq="M")
    downtime_end_period = pd.Period("2025-03", freq="M")
    new_lease_start_period = pd.Period("2025-04", freq="M")
    
    downtime_periods = pd.period_range(start=downtime_start_period, end=downtime_end_period, freq="M")
    
    assert "vacancy_loss" in projected_cf_df.columns
    assert projected_cf_df.loc[downtime_periods, "vacancy_loss"].sum() > 0
    assert projected_cf_df.loc[downtime_periods, "base_rent"].sum() == 0

    # 2. Next lease starts after the downtime.
    assert projected_cf_df.loc[new_lease_start_period, "base_rent"] > 0
    assert projected_cf_df.loc[downtime_end_period, "base_rent"] == 0
    
    # 3. The new rent is based on market_terms (60/sf annual -> 60*1000/12 monthly)
    expected_market_rent = (60.0 * 1000) / 12
    assert pytest.approx(projected_cf_df.loc[new_lease_start_period, "base_rent"]) == expected_market_rent


def test_rollover_reabsorb(sample_analysis_context: AnalysisContext):
    """
    Tests that a lease with upon_expiration=REABSORB stops generating cash flows
    after the initial lease term ends.
    """
    # Arrange
    rollover_profile = OfficeRolloverProfile(
        name="Test Reabsorb Profile",
        term_months=12,
        renewal_probability=0.0,
        downtime_months=3,
        market_terms=OfficeRolloverLeaseTerms(market_rent=60.0, term_months=36),
        renewal_terms=OfficeRolloverLeaseTerms(market_rent=55.0, term_months=24),
        upon_expiration=UponExpirationEnum.REABSORB,
    )

    lease = create_base_lease_for_rollover_test(
        rollover_profile, upon_expiration=UponExpirationEnum.REABSORB
    )

    # Act
    projected_cf_df = lease.project_future_cash_flows(context=sample_analysis_context)

    # Assert
    # The lease expires at the end of Dec 2024.
    # There should be no cash flows (rent, vacancy loss, etc.) after this date.
    original_lease_end_period = pd.Period("2024-12", freq="M")
    first_period_after_lease_end = pd.Period("2025-01", freq="M")
    
    # Check that there was rent in the last period of the lease
    assert projected_cf_df.loc[original_lease_end_period, "base_rent"] > 0
    
    # Check that all cash flows are zero for all periods after the lease ends
    cfs_after_expiration = projected_cf_df[projected_cf_df.index >= first_period_after_lease_end]
    
    assert cfs_after_expiration.empty or (cfs_after_expiration == 0).all().all()


def test_rollover_stops_at_analysis_end(sample_global_settings: GlobalSettings):
    """
    Tests that a speculative lease created from a rollover is correctly
    truncated at the end of the analysis timeline.
    """
    # Arrange
    # Analysis timeline is 24 months, from Jan 2024 to Dec 2025
    analysis_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
    analysis_context = AnalysisContext(
        timeline=analysis_timeline, settings=sample_global_settings, property_data={}
    )
    
    # Lease timeline is 20 months, expires Aug 2025.
    lease_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=20)
    
    # Rollover lease would be 24 months, but should be cut off by analysis end.
    market_terms = OfficeRolloverLeaseTerms(market_rent=60.0, term_months=24)
    rollover_profile = OfficeRolloverProfile(
        name="Test Truncate Profile",
        term_months=24,
        renewal_probability=0.0,
        downtime_months=0, # No downtime for simplicity
        market_terms=market_terms,
        renewal_terms=market_terms, # Not used
        upon_expiration=UponExpirationEnum.VACATE,
    )

    lease = OfficeLease(
        timeline=lease_timeline,
        name="Test Tenant",
        suite="101",
        floor="1",
        status=LeaseStatusEnum.CONTRACT,
        area=1000.0,
        upon_expiration=UponExpirationEnum.VACATE,
        value=50.0,
        unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
        frequency=FrequencyEnum.ANNUAL,
        rollover_profile=rollover_profile,
    )

    # Act
    projected_cf_df = lease.project_future_cash_flows(context=analysis_context)

    # Assert
    # 1. The DataFrame should not have any periods beyond the analysis end date.
    analysis_end_period = analysis_timeline.end_date
    assert projected_cf_df.index.max() <= analysis_end_period

    # 2. There should be cashflows for the new lease right up to the analysis end.
    # Original lease ends Aug 2025. New lease starts Sep 2025. Analysis ends Dec 2025.
    new_lease_start_period = pd.Period("2025-09", freq="M")
    
    assert projected_cf_df.loc[analysis_end_period, "base_rent"] > 0
    assert projected_cf_df.loc[new_lease_start_period, "base_rent"] > 0
    
    # 3. The new lease should only have cash flows for 4 months (Sep, Oct, Nov, Dec 2025).
    new_lease_cfs = projected_cf_df[projected_cf_df.index >= new_lease_start_period]
    assert len(new_lease_cfs[new_lease_cfs["base_rent"] > 0]) == 4


# More tests will be added here for different rollover scenarios. 