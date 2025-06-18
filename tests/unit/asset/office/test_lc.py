from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.analysis import AnalysisContext
from performa.asset.office.lc import CommissionTier, OfficeLeasingCommission
from performa.asset.office.property import OfficeProperty
from performa.common.primitives import GlobalSettings, Timeline, UnitOfMeasureEnum


@pytest.fixture
def sample_context() -> AnalysisContext:
    """Provides a basic analysis context for tests."""
    # Use a 5-year timeline to test tiers properly
    timeline = Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2028, 12, 31))
    property_data = OfficeProperty.model_construct(net_rentable_area=1.0)
    return AnalysisContext(
        timeline=timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        resolved_lookups={},
        recovery_states={},
    )

def test_lc_tiered_calculation(sample_context: AnalysisContext):
    """
    Tests that the tiered leasing commission is calculated correctly.
    """
    lc = OfficeLeasingCommission(
        name="Test Tiered LC",
        timeline=sample_context.timeline, # 5 year timeline
        value=100000.0, # Annual rent
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        landlord_broker_percentage=0.5,
        tenant_broker_percentage=0.5,
        tiers=[
            CommissionTier(year_start=1, year_end=1, rate=0.04), # 4% for year 1
            CommissionTier(year_start=2, year_end=3, rate=0.03), # 3% for years 2-3
            CommissionTier(year_start=4, rate=0.02),             # 2% for years 4-5
        ],
    )

    cf = lc.compute_cf(context=sample_context)
    
    # Expected calculation:
    # Year 1: 100,000 * 1 * 0.04 = 4,000
    # Year 2-3: 100,000 * 2 * 0.03 = 6,000
    # Year 4-5: 100,000 * 2 * 0.02 = 4,000
    # Total = 14,000
    
    assert cf.sum() == pytest.approx(14000.0)
    assert cf.iloc[0] == pytest.approx(14000.0)
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
        value=100000.0, # Annual rent
        unit_of_measure=UnitOfMeasureEnum.CURRENCY,
        landlord_broker_percentage=0.5,
        tenant_broker_percentage=0.5,
        tiers=[
            CommissionTier(year_start=1, year_end=1, rate=0.04), # 4% for year 1
            CommissionTier(year_start=2, rate=0.02),             # 2% for years 2-3.5
        ],
    )

    cf = lc.compute_cf(context=sample_context)
    
    # Expected calculation:
    # Year 1: 100,000 * 1.0 * 0.04 = 4,000
    # Year 2-3.5 (2.5 years): 100,000 * 2.5 * 0.02 = 5,000
    # Total = 9,000
    
    assert cf.sum() == pytest.approx(9000.0)
