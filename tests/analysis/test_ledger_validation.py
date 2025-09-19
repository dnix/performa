# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Ledger Validation Tests

These tests validate that the ledger is working correctly and accurately
captures all financial transactions from the analysis workflow.
"""

import pandas as pd
import pytest

from performa.analysis import run
from performa.asset.residential import (
    ResidentialCreditLoss,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialOpExItem,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
)
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    Timeline,
    UnleveredAggregateLineKey,
)


@pytest.fixture
def simple_residential_property():
    """Simple residential property for ledger testing."""
    timeline = Timeline.from_dates("2024-01-01", "2024-12-31")

    # Create lease terms for market and renewal scenarios
    market_terms = ResidentialRolloverLeaseTerms(
        market_rent=2000.0,
        renewal_rent_increase_percent=0.04,
    )

    renewal_terms = ResidentialRolloverLeaseTerms(
        market_rent=2000.0,
        renewal_rent_increase_percent=0.04,
    )

    rollover_profile = ResidentialRolloverProfile(
        name="Standard Rollover",
        renewal_probability=0.8,
        months_notice=2,
        downtime_months=1,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )

    unit_spec = ResidentialUnitSpec(
        unit_type_name="1BR Unit",
        unit_count=10,
        avg_area_sf=800.0,
        current_avg_monthly_rent=2000.0,
        rollover_profile=rollover_profile,
    )

    rent_roll = ResidentialRentRoll(unit_specs=[unit_spec])

    expenses = ResidentialExpenses(
        operating_expenses=[
            ResidentialOpExItem(
                name="Property Management",
                timeline=timeline,
                value=0.05,  # 5% of EGI
                reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
                frequency=FrequencyEnum.MONTHLY,
            ),
        ]
    )

    losses = ResidentialLosses(
        general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),
        credit_loss=ResidentialCreditLoss(rate=0.02),
    )

    return ResidentialProperty(
        uid="550e8400-e29b-41d4-a716-446655440001",  # Valid UUID format
        name="Test Property",
        gross_area=8000.0,
        net_rentable_area=8000.0,
        unit_mix=rent_roll,
        expenses=expenses,
        losses=losses,
    )


@pytest.fixture
def analysis_timeline():
    return Timeline.from_dates("2024-01-01", "2024-12-31")


@pytest.fixture
def global_settings():
    return GlobalSettings()


class TestLedgerBasicFunctionality:
    """Test that the ledger is built correctly and contains expected data."""

    def test_ledger_is_created(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that running analysis creates a ledger."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        # Ledger should exist and not be empty
        assert result.ledger is not None
        ledger_df = result.ledger.ledger_df()
        assert not ledger_df.empty

        # Ledger should have required columns
        required_columns = [
            "date",
            "amount",
            "flow_purpose",
            "category",
            "subcategory",
            "item_name",
        ]
        for col in required_columns:
            assert col in ledger_df.columns, f"Missing required column: {col}"

    def test_ledger_has_transactions(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that ledger contains actual transactions."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        ledger_df = result.ledger.ledger_df()

        # Should have transactions from multiple sources
        unique_purposes = ledger_df["flow_purpose"].unique()
        assert "Operating" in unique_purposes

        # Should have both revenue and expense transactions
        revenue_transactions = ledger_df[ledger_df["category"] == "Revenue"]
        expense_transactions = ledger_df[ledger_df["category"] == "Expense"]

        assert len(revenue_transactions) > 0, "Should have revenue transactions"
        assert len(expense_transactions) > 0, "Should have expense transactions"

    def test_ledger_dates_align_with_timeline(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that ledger dates align with analysis timeline."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        ledger_df = result.ledger.ledger_df()

        # All dates should be within timeline range
        min_date = ledger_df["date"].min()
        max_date = ledger_df["date"].max()

        timeline_start = analysis_timeline.start_date.to_timestamp().date()
        timeline_end = analysis_timeline.end_date.to_timestamp().date()

        # Convert timestamps to dates for comparison
        min_date_as_date = min_date.date() if hasattr(min_date, "date") else min_date
        max_date_as_date = max_date.date() if hasattr(max_date, "date") else max_date

        assert min_date_as_date >= timeline_start
        assert max_date_as_date <= timeline_end


class TestLedgerAccuracy:
    """Test that ledger calculations match traditional summary calculations."""

    def test_ledger_noi_matches_summary(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that NOI calculated from ledger matches summary NOI."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        # Calculate NOI from ledger (correctly: Revenue - Expenses)
        ledger_df = result.ledger.ledger_df()
        operating_flows = ledger_df[ledger_df["flow_purpose"] == "Operating"]

        # Separate revenue and expense flows
        revenue_flows = operating_flows[operating_flows["category"] == "Revenue"]
        expense_flows = operating_flows[operating_flows["category"] == "Expense"]

        # Calculate NOI properly: Revenue - Expenses
        revenue_by_date = (
            revenue_flows.groupby("date")["amount"].sum()
            if not revenue_flows.empty
            else pd.Series(dtype=float)
        )
        expense_by_date = (
            expense_flows.groupby("date")["amount"].sum()
            if not expense_flows.empty
            else pd.Series(dtype=float)
        )

        # Align indices and calculate NOI
        all_dates = (
            revenue_by_date.index.union(expense_by_date.index)
            if not revenue_by_date.empty or not expense_by_date.empty
            else pd.Index([])
        )
        revenue_aligned = revenue_by_date.reindex(all_dates, fill_value=0)
        expense_aligned = expense_by_date.reindex(all_dates, fill_value=0)
        ledger_noi = (
            revenue_aligned + expense_aligned
        )  # Expenses are now negative, so addition gives subtraction

        # Convert ledger calculation index to Period to match result index
        ledger_noi.index = pd.PeriodIndex(ledger_noi.index, freq="M")

        # Get NOI from result
        result_noi = result.noi

        # Should be close (allowing for floating point differences)
        assert len(ledger_noi) == len(result_noi), "Different number of periods"

        # Check a few specific months
        for date in ledger_noi.index[:3]:  # Check first 3 months
            ledger_value = ledger_noi[date]
            result_value = result_noi[date] if date in result_noi.index else 0
            assert (
                abs(ledger_value - result_value) < 0.01
            ), f"NOI mismatch for {date}: ledger={ledger_value}, result={result_value}"

    def test_revenue_transactions_make_sense(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that revenue transactions have expected values."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        ledger_df = result.ledger.ledger_df()
        revenue_transactions = ledger_df[ledger_df["category"] == "Revenue"]

        # Should have lease revenue
        lease_revenue = revenue_transactions[
            revenue_transactions["subcategory"] == "Lease"
        ]
        assert len(lease_revenue) > 0, "Should have lease revenue transactions"

        # Monthly revenue should be reasonable (10 units * $2000 = $20,000/month)
        monthly_revenue = lease_revenue.groupby("date")["amount"].sum()
        expected_monthly = 10 * 2000  # 10 units * $2000/month

        # Check first month (should be close to expected)
        first_month_revenue = monthly_revenue.iloc[0]
        assert (
            15000 <= first_month_revenue <= 25000
        ), f"Unexpected first month revenue: {first_month_revenue}"


class TestLedgerMetadata:
    """Test that ledger metadata is populated correctly."""

    def test_transactions_have_source_ids(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that transactions have source model IDs."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        ledger_df = result.ledger.ledger_df()

        # All transactions should have source IDs
        transactions_with_ids = ledger_df[ledger_df["source_id"].notna()]
        assert len(transactions_with_ids) == len(
            ledger_df
        ), "All transactions should have source IDs"

    def test_transactions_have_pass_numbers(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that transactions have valid pass numbers."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        ledger_df = result.ledger.ledger_df()

        # All transactions should have pass numbers
        valid_passes = ledger_df["pass_num"].isin([1, 2])
        assert valid_passes.all(), "All transactions should have pass_num of 1 or 2"

    def test_asset_id_is_consistent(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that all transactions have the same asset ID."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        ledger_df = result.ledger.ledger_df()

        # All transactions should have same asset ID
        unique_asset_ids = ledger_df["asset_id"].unique()
        assert (
            len(unique_asset_ids) == 1
        ), f"Expected 1 asset ID, got {len(unique_asset_ids)}"

        # Should match the property UID
        expected_asset_id = simple_residential_property.uid
        assert unique_asset_ids[0] == expected_asset_id


class TestLedgerQuerying:
    """Test that ledger can be queried effectively."""

    def test_ledger_query_object_works(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that LedgerQuery can be created and used."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        # Should be able to create queries
        queries = result.get_ledger_queries()
        assert queries is not None

        # Should be able to get NOI
        noi = queries.noi()
        assert not noi.empty

    def test_can_filter_by_transaction_type(
        self, simple_residential_property, analysis_timeline, global_settings
    ):
        """Test that we can filter transactions by type."""
        result = run(
            model=simple_residential_property,
            timeline=analysis_timeline,
            settings=global_settings,
        )

        ledger_df = result.ledger.ledger_df()

        # Should be able to filter by category
        revenue_only = ledger_df[ledger_df["category"] == "Revenue"]
        expense_only = ledger_df[ledger_df["category"] == "Expense"]

        assert len(revenue_only) > 0
        assert len(expense_only) > 0
        assert len(revenue_only) + len(expense_only) <= len(
            ledger_df
        )  # <= because there might be other categories
