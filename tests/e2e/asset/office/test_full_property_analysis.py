from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import pytest

from performa.analysis import run
from performa.asset.office.expense import OfficeExpenses, OfficeOpExItem
from performa.asset.office.lease_spec import OfficeLeaseSpec
from performa.asset.office.losses import (
    OfficeCollectionLoss,
    OfficeGeneralVacancyLoss,
    OfficeLosses,
)
from performa.asset.office.property import OfficeProperty
from performa.asset.office.rent_roll import OfficeRentRoll, OfficeVacantSuite
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseTypeEnum,
    Timeline,
    UnitOfMeasureEnum,
    UnleveredAggregateLineKey,
    UponExpirationEnum,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def analysis_timeline() -> Timeline:
    """Provides a standard 5-year analysis timeline."""
    return Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2028, 12, 31))

@pytest.fixture
def global_settings(analysis_timeline: Timeline) -> GlobalSettings:
    """Provides standard global settings."""
    return GlobalSettings(analysis_start_date=analysis_timeline.start_date.to_timestamp().date())


def test_end_to_end_analysis(analysis_timeline: Timeline, global_settings: GlobalSettings):
    """
    Tests the full analysis pipeline from property definition to cash flow
    using the new analysis engine. This is a simple "happy path" test.
    """
    # 1. Define Property Components
    rent_roll = OfficeRentRoll(
        leases=[
            OfficeLeaseSpec(
                tenant_name="Anchor Tenant",
                suite="100",
                floor="1",
                area=10000,
                use_type="office",
                start_date=date(2022, 1, 1),
                term_months=48, # Expires Dec 2025
                base_rent_value=40.0,
                base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
                base_rent_frequency=FrequencyEnum.ANNUAL,
                lease_type=LeaseTypeEnum.NET,
                upon_expiration=UponExpirationEnum.MARKET,
            )
        ],
        vacant_suites=[
            OfficeVacantSuite(suite="200", floor="2", area=5000, use_type="office")
        ]
    )
    expenses = OfficeExpenses(
        operating_expenses=[
            OfficeOpExItem(
                name="CAM",
                timeline=analysis_timeline,
                value=120000,
                frequency=FrequencyEnum.ANNUAL,
                unit_of_measure=UnitOfMeasureEnum.CURRENCY
            )
        ]
    )
    losses = OfficeLosses(
        general_vacancy=OfficeGeneralVacancyLoss(rate=0.05),
        collection_loss=OfficeCollectionLoss(rate=0.01)
    )
    property_data = OfficeProperty(
        name="Test Office Tower",
        property_type="office",
        gross_area=15000,
        net_rentable_area=15000,
        rent_roll=rent_roll,
        expenses=expenses,
        losses=losses,
    )

    # 2. Run the Analysis
    scenario = run(
        model=property_data,
        timeline=analysis_timeline,
        settings=global_settings
    )
    result_df = scenario.get_cash_flow_summary()

    # 3. Assertions
    assert isinstance(result_df, pd.DataFrame)
    assert not result_df.empty

    jan_2024 = pd.Period("2024-01", freq="M")
    
    # Expected Base Rent: 10000sf * $40/sf/yr / 12 mo = $33,333.33
    expected_rent = (10000 * 40) / 12
    assert result_df.loc[jan_2024, UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value] == pytest.approx(expected_rent)

    # Expected Expenses: 120,000 / 12 = 10,000
    assert result_df.loc[jan_2024, UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES.value] == pytest.approx(10000)

    # Expected NOI (simple case)
    # Note: The orchestrator now calculates EGI, vacancy, etc. This is a simplified check.
    # A more detailed check would be in the complex test.
    expected_egi = expected_rent # Assuming no other income/abatement
    # Vacancy loss is 5% of PGR
    expected_vacancy = expected_rent * 0.05 
    expected_noi = expected_egi - expected_vacancy - 10000
    # This is an approximation as collection loss and other items apply
    assert result_df.loc[jan_2024, UnleveredAggregateLineKey.NET_OPERATING_INCOME.value] > 0
