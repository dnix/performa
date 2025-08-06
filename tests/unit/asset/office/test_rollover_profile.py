# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pytest

from performa.asset.office.rollover import (
    OfficeRolloverLeaseTerms,
    OfficeRolloverProfile,
    OfficeRolloverTenantImprovement,
)
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    PercentageGrowthRate,
    PropertyAttributeKey,
    Timeline,
)


@pytest.fixture
def sample_global_settings():
    return GlobalSettings()


@pytest.fixture
def sample_timeline():
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2028, 12, 31))


def test_calculate_rent_with_growth(sample_global_settings):
    terms = OfficeRolloverLeaseTerms(
        market_rent=100.0,
        frequency=FrequencyEnum.ANNUAL,
        growth_rate=PercentageGrowthRate(name="Test Growth", value=0.03)  # 3% annual
    )
    profile = OfficeRolloverProfile(
        name="Test Profile",
        term_months=60,
        renewal_probability=0.5,
        downtime_months=3,
        market_terms=terms,
        renewal_terms=terms,
    )
    
    rent = profile._calculate_rent(terms, date(2025, 6, 15), sample_global_settings)
    # Base monthly rent = 100/12 = 8.333
    # as_of_date is before analysis_start_date, so no growth should apply
    assert rent == (100.0 / 12.0)
    

def test_blend_lease_terms(sample_timeline):
    market_terms = OfficeRolloverLeaseTerms(
        market_rent=60.0,
        ti_allowance=OfficeRolloverTenantImprovement(
            value=20.0, 
            reference=PropertyAttributeKey.NET_RENTABLE_AREA
        )
    )
    renewal_terms = OfficeRolloverLeaseTerms(
        market_rent=50.0,
        ti_allowance=OfficeRolloverTenantImprovement(
            value=10.0, 
            reference=PropertyAttributeKey.NET_RENTABLE_AREA
        )
    )
    profile = OfficeRolloverProfile(
        name="Test Profile",
        term_months=60,
        renewal_probability=0.75,  # 75% renewal
        downtime_months=3,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )

    blended = profile.blend_lease_terms()
    # Blended Rent: (50 * 0.75) + (60 * 0.25) = 37.5 + 15 = 52.5
    assert pytest.approx(blended.market_rent) == 52.5
    # Blended TI: (10 * 0.75) + (20 * 0.25) = 7.5 + 5 = 12.5
    assert pytest.approx(blended.ti_allowance.value) == 12.5
