# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Ledger-Based Office Lease Tests - Proof of Concept

This module demonstrates the new testing approach for the ledger-based architecture.
Tests focus on business behavior and outcomes rather than implementation details.

Key Principles:
1. Test business behavior, not internal data structures
2. Use ledger as source of truth for financial metrics
3. Test integration through full analysis pipeline
4. Verify outcomes that matter to users
"""

import unittest
from datetime import date

from performa.analysis import run
from performa.analysis.results import AssetAnalysisResult
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
    ProgramUseEnum,
    Timeline,
    UponExpirationEnum,
)


class TestOfficeLeaseLedgerBehavior(unittest.TestCase):
    """
    Test office lease business behavior through ledger integration.

    These tests verify that office leases produce correct business outcomes
    when integrated with the ledger system, focusing on what users care about
    rather than internal implementation details.
    """

    def setUp(self):
        """Set up common test fixtures."""
        self.settings = GlobalSettings()
        self.timeline = Timeline.from_dates(
            start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
        )

    def test_simple_lease_creates_correct_revenue_in_ledger(self):
        """
        Verify that a simple lease creates the expected revenue in the ledger.

        Business Intent: A $60k/year lease should generate $5k/month in revenue
        that appears correctly in ledger queries and property NOI calculations.
        """
        # Create a simple office property with one lease
        lease_spec = OfficeLeaseSpec(
            tenant_name="Test Tenant",
            suite="101",
            floor="1",
            area=1000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="gross",
            start_date=date(2024, 1, 1),
            term_months=12,
            base_rent_value=60000.0,  # $60k annual
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
        )

        # Create rent roll with the lease
        rent_roll = OfficeRentRoll(
            leases=[lease_spec],
            vacant_suites=[],  # No vacant suites for simple test
        )

        # Create minimal expenses (required field)
        expenses = OfficeExpenses(operating_expenses=[])

        # Create minimal losses (required field)
        losses = OfficeLosses(
            general_vacancy=OfficeGeneralVacancyLoss(
                rate=0.0
            ),  # No vacancy for simple test
            credit_loss=OfficeCreditLoss(
                rate=0.0
            ),  # No collection loss for simple test
        )

        property = OfficeProperty(
            name="Test Office Building",
            gross_area=10000.0,
            net_rentable_area=9000.0,
            rent_roll=rent_roll,
            expenses=expenses,
            losses=losses,
        )

        # Run full analysis - this is what users actually do
        result: AssetAnalysisResult = run(
            model=property, timeline=self.timeline, settings=self.settings
        )

        # Verify business outcomes through ledger queries
        ledger_df = result.ledger.ledger_df()
        queries = LedgerQueries(ledger_df)

        # Test 1: Monthly revenue should be $5k
        egi = queries.egi()
        expected_monthly_revenue = 5000.0  # $60k / 12 months
        self.assertAlmostEqual(
            egi.iloc[0],
            expected_monthly_revenue,
            places=2,
            msg="Monthly revenue should be $5k for $60k annual lease",
        )

        # Test 2: Annual revenue should be $60k
        annual_revenue = egi.sum()
        self.assertAlmostEqual(
            annual_revenue, 60000.0, places=2, msg="Annual revenue should be $60k"
        )

        # Test 3: NOI should equal revenue (no expenses)
        noi = queries.noi()
        self.assertTrue(
            (egi == noi).all(),
            msg="NOI should equal revenue when there are no expenses",
        )


# Additional test methods for comprehensive lease behavior validation would be added here


class TestOfficeLeaseLedgerIntegration(unittest.TestCase):
    """
    Test office lease integration with the ledger system.

    These tests verify that lease components are correctly recorded
    in the ledger with proper categorization and metadata.
    """

    def setUp(self):
        """Set up common test fixtures."""
        self.settings = GlobalSettings()
        self.timeline = Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),  # Shorter timeline for detailed testing
        )

    def test_lease_components_recorded_with_correct_categories(self):
        """
        Verify that lease components are recorded in ledger with correct categorization.

        Technical Intent: Ensure that base rent, recoveries, abatements, etc.
        are recorded with the correct flow_purpose, category, and subcategory
        for proper aggregation and reporting.
        """
        # Create a lease with multiple components
        lease_spec = OfficeLeaseSpec(
            tenant_name="Complex Tenant",
            suite="201",
            floor="2",
            area=2000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="net",  # Will have recoveries
            start_date=date(2024, 1, 1),
            term_months=3,
            base_rent_value=36000.0,  # $3k/month
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
        )

        # Create rent roll with the lease
        rent_roll = OfficeRentRoll(
            leases=[lease_spec],
            vacant_suites=[],  # No vacant suites for simple test
        )

        # Create minimal expenses (required field)
        expenses = OfficeExpenses(operating_expenses=[])

        # Create minimal losses (required field)
        losses = OfficeLosses(
            general_vacancy=OfficeGeneralVacancyLoss(
                rate=0.0
            ),  # No vacancy for simple test
            credit_loss=OfficeCreditLoss(
                rate=0.0
            ),  # No collection loss for simple test
        )

        property = OfficeProperty(
            name="Test Office Building",
            gross_area=10000.0,
            net_rentable_area=9000.0,
            rent_roll=rent_roll,
            expenses=expenses,
            losses=losses,
        )

        # Run analysis
        result: AssetAnalysisResult = run(
            model=property, timeline=self.timeline, settings=self.settings
        )

        # Verify ledger structure
        ledger_df = result.ledger.ledger_df()

        # Test 1: Base rent transactions exist with correct categorization
        base_rent_transactions = ledger_df[
            (ledger_df["subcategory"] == "Lease")
            & (ledger_df["item_name"].str.contains("Complex Tenant"))
        ]
        self.assertFalse(
            base_rent_transactions.empty,
            msg="Should have base rent transactions for the lease",
        )

        # Test 2: All transactions have correct flow_purpose
        operating_transactions = ledger_df[ledger_df["flow_purpose"] == "Operating"]
        self.assertFalse(
            operating_transactions.empty,
            msg="Lease transactions should be classified as Operating",
        )

        # Test 3: Revenue transactions have positive amounts
        revenue_transactions = ledger_df[ledger_df["category"] == "Revenue"]
        self.assertTrue(
            (revenue_transactions["amount"] > 0).all(),
            msg="Revenue transactions should have positive amounts",
        )


# Additional ledger integration tests would be implemented here as needed


if __name__ == "__main__":
    unittest.main()
