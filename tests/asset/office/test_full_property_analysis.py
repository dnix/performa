from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

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
from performa.common.primitives import (
    AggregateLineKey,
    FrequencyEnum,
    GlobalSettings,
    LeaseTypeEnum,
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)


class TestFullPropertyAnalysis(unittest.TestCase):
    def test_end_to_end_analysis(self):
        """
        Tests the full analysis pipeline from property definition to cash flow
        using the new analysis engine.
        """
        # 1. Setup Timeline and Settings
        analysis_start = date(2024, 1, 1)
        analysis_end = date(2028, 12, 31)
        timeline = Timeline.from_dates(start_date=analysis_start, end_date=analysis_end)
        settings = GlobalSettings(analysis_start_date=analysis_start)

        # 2. Define Property Components
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
                    timeline=timeline,
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

        # 4. Run the Analysis using the new `run` function
        scenario = run(
            model=property_data,
            timeline=timeline,
            settings=settings
        )
        result_df = scenario.get_cash_flow_summary()

        # 5. Assertions
        self.assertIsInstance(result_df, pd.DataFrame)
        self.assertFalse(result_df.empty)

        jan_2024 = pd.Period("2024-01", freq="M")
        
        # Expected Base Rent for Anchor Tenant: 10000sf * $40/sf/yr / 12 mo = $33,333.33
        expected_rent = (10000 * 40) / 12
        self.assertAlmostEqual(
            result_df.loc[jan_2024, AggregateLineKey.POTENTIAL_GROSS_REVENUE.value], 
            expected_rent, 
            places=2
        )

        # Expected Expenses: 120,000 / 12 = 10,000
        self.assertAlmostEqual(
            result_df.loc[jan_2024, AggregateLineKey.TOTAL_OPERATING_EXPENSES.value], 
            10000, 
            places=2
        )

        # Expected Net Cash Flow (NOI in this simple case)
        expected_noi = expected_rent - 10000
        self.assertAlmostEqual(
            result_df.loc[jan_2024, AggregateLineKey.NET_OPERATING_INCOME.value], 
            expected_noi, 
            places=2
        )


if __name__ == "__main__":
    unittest.main()
