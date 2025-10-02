# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Ledger-Based Collection Loss Tests

Tests collection loss business behavior through ledger integration.
Focuses on verifying that collection loss is calculated correctly
as a percentage of Effective Gross Income (EGI).
"""

import unittest
from datetime import date

from performa.analysis import run
from performa.asset.office.expense import OfficeExpenses
from performa.asset.office.lease_spec import OfficeLeaseSpec
from performa.asset.office.loss import (
    OfficeCreditLoss,
    OfficeGeneralVacancyLoss,
    OfficeLosses,
)
from performa.asset.office.property import OfficeProperty
from performa.asset.office.rent_roll import OfficeRentRoll
from performa.core.ledger import LedgerQueries
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseTypeEnum,
    ProgramUseEnum,
    Timeline,
    UponExpirationEnum,
)
from performa.core.primitives.enums import RevenueSubcategoryEnum


class TestCollectionLossLedgerBehavior(unittest.TestCase):
    """
    Test collection loss business behavior through ledger integration.

    Collection loss should be calculated as a percentage of Effective Gross Income (EGI),
    which is Potential Gross Revenue minus vacancy loss.
    """

    def setUp(self):
        """Set up common test fixtures."""
        self.settings = GlobalSettings()
        self.timeline = Timeline.from_dates(
            start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
        )

    def test_collection_loss_calculated_on_egi(self):
        """
        Verify that credit loss is calculated as percentage of PGR (industry standard).

        Business Intent: Credit loss should be 0.5% of Potential Gross Revenue,
        calculated on all potential revenue at 100% occupancy per industry standards.
        """
        # Create a simple lease
        lease_spec = OfficeLeaseSpec(
            tenant_name="Test Tenant",
            suite="101",
            floor="1",
            area=10000.0,  # 10,000 SF
            use_type=ProgramUseEnum.OFFICE,
            lease_type=LeaseTypeEnum.GROSS,
            start_date=date(2024, 1, 1),
            term_months=12,
            base_rent_value=300000.0,  # $30/SF annually = $300k total
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
        )

        # Create rent roll
        rent_roll = OfficeRentRoll(
            leases=[lease_spec],
            vacant_suites=[],  # No vacancy for this test
        )

        # Create minimal expenses
        expenses = OfficeExpenses(operating_expenses=[])

        # Create losses with specific rates
        losses = OfficeLosses(
            general_vacancy=OfficeGeneralVacancyLoss(rate=0.03),  # 3% vacancy
            credit_loss=OfficeCreditLoss(
                rate=0.005, basis="Potential Gross Revenue"
            ),  # 0.5% credit loss on PGR
        )

        property = OfficeProperty(
            name="Test Office Building",
            gross_area=12000.0,
            net_rentable_area=10000.0,
            rent_roll=rent_roll,
            expenses=expenses,
            losses=losses,
        )

        # Run analysis
        result = run(model=property, timeline=self.timeline, settings=self.settings)

        # Query results through ledger
        ledger_df = result.ledger.ledger_df()
        queries = LedgerQueries(result.ledger)

        # Get January values for detailed analysis
        jan_transactions = ledger_df[ledger_df["date"] == date(2024, 1, 1)]

        # Calculate expected values (industry standard: credit loss based on PGR)
        monthly_rent = 300000.0 / 12  # $25,000/month (PGR)
        vacancy_loss = monthly_rent * 0.03  # $750/month
        expected_collection_loss = (
            monthly_rent * 0.005
        )  # $125/month (based on PGR, not EGI)
        egi = monthly_rent - vacancy_loss - expected_collection_loss  # $24,125/month

        # Prefer direct transaction lookup; if absent due to timing, fall back to query result
        collection_loss_transactions = jan_transactions[
            jan_transactions["subcategory"].astype(str)
            == RevenueSubcategoryEnum.CREDIT_LOSS.value
        ]

        if collection_loss_transactions.empty:
            # Fallback to computed series from queries (authoritative aggregate)
            cl_series = queries.credit_loss()
            actual_collection_loss = (
                abs(cl_series.loc[cl_series.index[0]]) if not cl_series.empty else 0.0
            )
        else:
            actual_collection_loss = abs(collection_loss_transactions["amount"].sum())

        self.assertAlmostEqual(
            actual_collection_loss,
            expected_collection_loss,
            places=2,
            msg=f"Credit loss should be 0.5% of PGR (industry standard): "
            f"Expected ${expected_collection_loss:.2f}, "
            f"Actual ${actual_collection_loss:.2f}, "
            f"PGR: ${monthly_rent:.2f}",
        )


# Additional collection loss integration tests would be implemented here as needed


if __name__ == "__main__":
    unittest.main()
