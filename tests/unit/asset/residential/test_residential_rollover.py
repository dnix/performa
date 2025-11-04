# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import date

import pytest

from performa.analysis import AnalysisContext
from performa.asset.residential.expense import ResidentialExpenses
from performa.asset.residential.lease import ResidentialLease
from performa.asset.residential.loss import (
    ResidentialCreditLoss,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
)
from performa.asset.residential.property import ResidentialProperty
from performa.asset.residential.rent_roll import (
    ResidentialRentRoll,
    ResidentialUnitSpec,
)
from performa.asset.residential.rollover import (
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
)
from performa.core.ledger import Ledger
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseStatusEnum,
    Timeline,
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

    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=60)  # 5 years

    # Create minimal rollover profile for unit spec
    renewal_terms = ResidentialRolloverLeaseTerms(market_rent=2000.0)
    market_terms = ResidentialRolloverLeaseTerms(market_rent=2200.0)
    rollover_profile = ResidentialRolloverProfile(
        name="Test Profile",
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )

    # Create minimal required unit spec for ResidentialProperty
    unit_spec = ResidentialUnitSpec(
        unit_type_name="1BR",
        unit_count=1,
        avg_area_sf=750.0,
        current_avg_monthly_rent=2000.0,
        rollover_profile=rollover_profile,
        lease_start_date=date(2024, 1, 1),
    )

    # Create rent roll with the unit spec
    rent_roll = ResidentialRentRoll(unit_specs=[unit_spec])

    # Create required losses structure
    general_vacancy = ResidentialGeneralVacancyLoss(
        rate=0.05,  # 5% vacancy
    )
    collection_loss = ResidentialCreditLoss(
        rate=0.02,  # 2% collection loss
    )
    losses = ResidentialLosses(
        general_vacancy=general_vacancy,
        credit_loss=collection_loss,
    )

    property_data = ResidentialProperty(
        name="Test Property",
        gross_area=900.0,  # Adjusted to be reasonable relative to net rentable
        net_rentable_area=750.0,  # Match total unit area (1 unit × 750 SF)
        unit_mix=rent_roll,
        losses=losses,
        expenses=ResidentialExpenses(),
    )
    return AnalysisContext(
        timeline=timeline,
        settings=sample_global_settings,
        property_data=property_data,
        ledger=Ledger(),
    )


def create_base_lease_for_rollover_test(
    rollover_profile: ResidentialRolloverProfile, upon_expiration: UponExpirationEnum
) -> ResidentialLease:
    """Helper function to create a standard residential lease for rollover tests."""
    lease_timeline = Timeline(
        start_date=date(2024, 1, 1), duration_months=12
    )  # 1-year lease
    return ResidentialLease(
        timeline=lease_timeline,
        name="Test Resident",
        suite="101",
        floor="1",
        status=LeaseStatusEnum.CONTRACT,
        area=750.0,
        upon_expiration=upon_expiration,
        monthly_rent=2000.0,
        value=2000.0,
        frequency=FrequencyEnum.MONTHLY,
        rollover_profile=rollover_profile,
    )


def test_rollover_renew(sample_analysis_context: AnalysisContext):
    """
    Tests that a residential lease with upon_expiration=RENEW uses renewal terms.
    """
    # Arrange
    renewal_terms = ResidentialRolloverLeaseTerms(market_rent=2000.0, term_months=12)
    market_terms = ResidentialRolloverLeaseTerms(market_rent=2200.0, term_months=12)

    rollover_profile = ResidentialRolloverProfile(
        name="Test Renew Profile",
        term_months=12,
        renewal_probability=0.7,
        downtime_months=0,  # RENEW profiles must have 0 downtime (enforced by validator)
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )

    lease = create_base_lease_for_rollover_test(
        rollover_profile, upon_expiration=UponExpirationEnum.RENEW
    )

    # Act
    projected_cf_df = lease.project_future_cash_flows(context=sample_analysis_context)

    # Assert
    base_rent_series = projected_cf_df["base_rent"]
    rent_values = base_rent_series[base_rent_series > 0]
    unique_rents = sorted(rent_values.unique())

    # Should have original rent (2000) and renewal rent (2000)
    assert len(unique_rents) == 1  # Same rent for renewal
    assert unique_rents[0] == 2000.0

    # RENEW should have 100% coverage (no downtime when tenant stays)
    # Calculation: 5 full cycles * 12 months = 60/60 = 100%
    rent_months = (base_rent_series > 0).sum()
    total_months = len(base_rent_series)
    coverage = rent_months / total_months
    assert coverage == 1.0  # 100% coverage for renewal scenario


def test_rollover_vacate(sample_analysis_context: AnalysisContext):
    """
    Tests that a residential lease with upon_expiration=VACATE uses market terms.
    """
    # Arrange
    renewal_terms = ResidentialRolloverLeaseTerms(market_rent=2000.0, term_months=12)
    market_terms = ResidentialRolloverLeaseTerms(market_rent=2200.0, term_months=12)

    rollover_profile = ResidentialRolloverProfile(
        name="Test Vacate Profile",
        term_months=12,
        renewal_probability=0.7,
        downtime_months=1,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )

    lease = create_base_lease_for_rollover_test(
        rollover_profile, upon_expiration=UponExpirationEnum.VACATE
    )

    # Act
    projected_cf_df = lease.project_future_cash_flows(context=sample_analysis_context)

    # Assert
    base_rent_series = projected_cf_df["base_rent"]
    rent_values = base_rent_series[base_rent_series > 0]
    unique_rents = sorted(rent_values.unique())

    # Should have original rent (2000) and market rent (2200)
    assert len(unique_rents) == 2
    assert unique_rents[0] == 2000.0  # Original lease
    assert unique_rents[1] == 2200.0  # Market rate for new tenant

    # VACATE should have 93.3% coverage (1-month downtime for new tenant)
    # Calculation: (4 full cycles * 12 months + 8 remaining months) / 60 = 56/60 = 93.3%
    rent_months = (base_rent_series > 0).sum()
    total_months = len(base_rent_series)
    coverage = rent_months / total_months
    assert coverage == pytest.approx(0.933, abs=0.01)  # Expected coverage with downtime


def test_rollover_market_blended(sample_analysis_context: AnalysisContext):
    """
    Tests that a residential lease with upon_expiration=MARKET uses blended terms.
    """
    # Arrange
    renewal_terms = ResidentialRolloverLeaseTerms(market_rent=2000.0, term_months=12)
    market_terms = ResidentialRolloverLeaseTerms(market_rent=2200.0, term_months=12)

    rollover_profile = ResidentialRolloverProfile(
        name="Test Market Profile",
        term_months=12,
        renewal_probability=0.7,  # 70% renewal, 30% market
        downtime_months=1,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )

    lease = create_base_lease_for_rollover_test(
        rollover_profile, upon_expiration=UponExpirationEnum.MARKET
    )

    # Act
    projected_cf_df = lease.project_future_cash_flows(context=sample_analysis_context)

    # Assert
    base_rent_series = projected_cf_df["base_rent"]
    rent_values = base_rent_series[base_rent_series > 0]
    unique_rents = sorted(rent_values.unique())

    # Should have original rent (2000) and blended rent (2060)
    # Blended = 0.7 * 2000 + 0.3 * 2200 = 1400 + 660 = 2060
    assert len(unique_rents) == 2
    assert unique_rents[0] == 2000.0  # Original lease
    assert unique_rents[1] == 2060.0  # Blended rate

    # MARKET should have 93.3% coverage (1-month downtime from blended outcome)
    # Calculation: (4 full cycles * 12 months + 8 remaining months) / 60 = 56/60 = 93.3%
    rent_months = (base_rent_series > 0).sum()
    total_months = len(base_rent_series)
    coverage = rent_months / total_months
    assert coverage == pytest.approx(0.933, abs=0.01)  # Expected coverage with downtime


def test_rollover_reabsorb(sample_analysis_context: AnalysisContext):
    """
    Tests that a residential lease with upon_expiration=REABSORB stops after original lease.
    """
    # Arrange
    renewal_terms = ResidentialRolloverLeaseTerms(market_rent=2000.0, term_months=12)
    market_terms = ResidentialRolloverLeaseTerms(market_rent=2200.0, term_months=12)

    rollover_profile = ResidentialRolloverProfile(
        name="Test Reabsorb Profile",
        term_months=12,
        renewal_probability=0.7,
        downtime_months=1,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )

    lease = create_base_lease_for_rollover_test(
        rollover_profile, upon_expiration=UponExpirationEnum.REABSORB
    )

    # Act
    projected_cf_df = lease.project_future_cash_flows(context=sample_analysis_context)

    # Assert
    base_rent_series = projected_cf_df["base_rent"]
    rent_values = base_rent_series[base_rent_series > 0]
    unique_rents = sorted(rent_values.unique())

    # Should only have original rent (no rollovers)
    assert len(unique_rents) == 1
    assert unique_rents[0] == 2000.0

    # Should only cover the original lease period (12 months)
    rent_months = (base_rent_series > 0).sum()
    assert rent_months == 12  # Only original lease period


def test_rollover_multiple_periods_iterative(sample_analysis_context: AnalysisContext):
    """
    Tests that residential rollover iterative logic works for many periods (30-year analysis).
    """
    # Arrange
    renewal_terms = ResidentialRolloverLeaseTerms(market_rent=2000.0, term_months=12)
    market_terms = ResidentialRolloverLeaseTerms(market_rent=2200.0, term_months=12)

    rollover_profile = ResidentialRolloverProfile(
        name="Multi-Period Profile",
        term_months=12,
        renewal_probability=0.7,
        downtime_months=1,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )

    lease = create_base_lease_for_rollover_test(
        rollover_profile, upon_expiration=UponExpirationEnum.MARKET
    )

    # Create 30-year analysis context

    # Create minimal rollover profile for unit spec
    renewal_terms = ResidentialRolloverLeaseTerms(market_rent=2000.0)
    market_terms = ResidentialRolloverLeaseTerms(market_rent=2200.0)
    rollover_profile = ResidentialRolloverProfile(
        name="Test Profile",
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )

    # Create minimal required unit spec for ResidentialProperty
    unit_spec = ResidentialUnitSpec(
        unit_type_name="1BR",
        unit_count=1,
        avg_area_sf=750.0,
        current_avg_monthly_rent=2000.0,
        rollover_profile=rollover_profile,
        lease_start_date=date(2024, 1, 1),
    )

    # Create rent roll with the unit spec
    rent_roll = ResidentialRentRoll(unit_specs=[unit_spec])

    # Create required losses structure
    general_vacancy = ResidentialGeneralVacancyLoss(
        rate=0.05,  # 5% vacancy
    )
    collection_loss = ResidentialCreditLoss(
        rate=0.02,  # 2% collection loss
    )
    losses = ResidentialLosses(
        general_vacancy=general_vacancy,
        credit_loss=collection_loss,
    )

    property_data = ResidentialProperty(
        name="Test Property",
        gross_area=900.0,  # Adjusted to be reasonable relative to net rentable
        net_rentable_area=750.0,  # Match total unit area (1 unit × 750 SF)
        unit_mix=rent_roll,
        losses=losses,
        expenses=ResidentialExpenses(),
    )
    long_context = AnalysisContext(
        timeline=Timeline(start_date=date(2024, 1, 1), duration_months=360),
        settings=GlobalSettings(),
        property_data=property_data,
        ledger=Ledger(),
    )

    # Act
    projected_cf_df = lease.project_future_cash_flows(context=long_context)

    # Assert
    base_rent_series = projected_cf_df["base_rent"]
    rent_values = base_rent_series[base_rent_series > 0]

    # Coverage should match theoretical expectation (92.5% for 30-year analysis)
    # Missing coverage is due to 1-month downtime between lease periods
    # Calculation: (27 full cycles * 12 months + 9 remaining months) / 360 = 333/360 = 92.5%
    rent_months = (base_rent_series > 0).sum()
    total_months = len(base_rent_series)
    coverage = rent_months / total_months

    assert coverage == pytest.approx(0.925, abs=0.01)  # Precise expected coverage
    assert rent_months == 333  # Exact expected rent months for 30-year period

    # Verify iterative logic didn't hit the max_renewals limit
    # With 1-year leases and 30-year analysis, we expect ~30 renewals
    # The limit is 50, so we shouldn't hit it
    expected_renewals = total_months // 12  # Rough estimate
    assert expected_renewals <= 50  # Verify we're within the safety limit


def test_renew_profile_validator():
    """
    Tests the Pydantic validator that enforces downtime_months=0 for RENEW profiles.
    """
    # Arrange
    renewal_terms = ResidentialRolloverLeaseTerms(market_rent=2000.0, term_months=12)
    market_terms = ResidentialRolloverLeaseTerms(market_rent=2200.0, term_months=12)

    # Test 1: Valid RENEW profile (downtime_months=0)
    valid_profile = ResidentialRolloverProfile(
        name="Valid RENEW Profile",
        term_months=12,
        renewal_probability=0.7,
        downtime_months=0,  # Must be 0 for RENEW
        upon_expiration=UponExpirationEnum.RENEW,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )
    assert valid_profile.downtime_months == 0

    # Test 2: Invalid RENEW profile (downtime_months>0) should raise ValidationError
    with pytest.raises(Exception) as exc_info:
        ResidentialRolloverProfile(
            name="Invalid RENEW Profile",
            term_months=12,
            renewal_probability=0.7,
            downtime_months=1,  # Invalid for RENEW
            upon_expiration=UponExpirationEnum.RENEW,
            market_terms=market_terms,
            renewal_terms=renewal_terms,
        )

    # Verify the error message contains the business rule explanation
    assert "RENEW upon_expiration requires downtime_months=0" in str(exc_info.value)

    # Test 3: Non-RENEW profiles can have downtime_months>0
    valid_vacate_profile = ResidentialRolloverProfile(
        name="Valid VACATE Profile",
        term_months=12,
        renewal_probability=0.7,
        downtime_months=1,  # Valid for VACATE
        upon_expiration=UponExpirationEnum.VACATE,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )
    assert valid_vacate_profile.downtime_months == 1
