# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for CashSweep covenant class.

Tests the cash sweep covenant implementation including TRAP and PREPAY modes,
excess cash calculation, and ledger transaction posting.
"""

from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pandas as pd
import pytest

from performa.core.ledger import Ledger
from performa.core.ledger.queries import LedgerQueries
from performa.core.ledger.records import SeriesMetadata
from performa.core.primitives import (
    CashFlowCategoryEnum,
    GlobalSettings,
    RevenueSubcategoryEnum,
    SweepMode,
    Timeline,
)
from performa.deal.orchestrator import DealContext
from performa.debt.construction import ConstructionFacility
from performa.debt.covenants import CashSweep
from performa.debt.rates import FixedRate, InterestRate


def create_mock_context(timeline, noi_series, ledger_df, facility_name="Test Facility"):
    """
    Helper to create a properly mocked context for testing CashSweep.

    Args:
        timeline: Timeline object
        noi_series: NOI series for queries
        ledger_df: DataFrame for ledger.to_dataframe()
        facility_name: Name of the facility to create

    Returns:
        Tuple of (context, facility) with proper mocks
    """
    context = Mock()
    context.timeline = timeline

    # Mock ledger with DuckDB connection for LedgerQueries
    ledger = Mock(spec=Ledger)
    # Ensure ledger_df has item_name column for facility filtering
    if "item_name" not in ledger_df.columns:
        ledger_df = ledger_df.copy()
        if not ledger_df.empty:
            ledger_df["item_name"] = facility_name
        else:
            # For empty dataframes, define the column with correct dtype
            ledger_df["item_name"] = pd.Series([], dtype=str)
    ledger.to_dataframe.return_value = ledger_df
    # Mock get_query_connection() to return (connection, table_name) tuple
    # The connection will be used by LedgerQueries to execute SQL
    mock_connection = Mock()
    # Mock the SQL execute chain: .execute(sql).arrow().read_all()
    # LedgerQueries uses Arrow format for performance
    mock_arrow_reader = Mock()
    mock_arrow_table = Mock()
    # The table needs to support column access and conversion to pandas
    # Create a simple mock that returns the NOI data when accessed
    mock_arrow_table.num_rows = len(noi_series)
    # Mock column access for period and total
    # Need to handle to_pandas(date_as_object=False) parameter
    mock_period_column = Mock()

    def to_pandas_period(**kwargs):
        return pd.Series(noi_series.index)

    mock_period_column.to_pandas = to_pandas_period

    mock_total_column = Mock()

    def to_pandas_total(**kwargs):
        return pd.Series(noi_series.values)

    mock_total_column.to_pandas = to_pandas_total
    # Use __getitem__ to mock tbl['period'] and tbl['total'] access

    def mock_getitem(key):
        if key == "period":
            return mock_period_column
        elif key == "total":
            return mock_total_column
        raise KeyError(key)

    mock_arrow_table.__getitem__ = mock_getitem
    mock_arrow_reader.read_all.return_value = mock_arrow_table
    mock_connection.execute.return_value.arrow.return_value = mock_arrow_reader
    ledger.get_query_connection.return_value = (mock_connection, "ledger")
    context.ledger = ledger

    # Mock facility with uid
    facility = Mock(spec=ConstructionFacility)
    facility.name = facility_name
    facility.uid = uuid4()
    facility.outstanding_balance = 10_000_000

    # Mock deal with asset
    deal = Mock()
    asset = Mock()
    asset.uid = uuid4()
    deal.asset = asset
    deal.financing.facilities = [facility]
    context.deal = deal

    return context, facility


class TestCashSweepCreation:
    """Test CashSweep instantiation and field validation."""

    def test_cash_sweep_creation_trap_mode(self):
        """Test creating CashSweep with TRAP mode."""
        sweep = CashSweep(mode=SweepMode.TRAP, end_month=12)

        assert sweep.mode == SweepMode.TRAP
        assert sweep.end_month == 12

    def test_cash_sweep_creation_prepay_mode(self):
        """Test creating CashSweep with PREPAY mode."""
        sweep = CashSweep(mode=SweepMode.PREPAY, end_month=24)

        assert sweep.mode == SweepMode.PREPAY
        assert sweep.end_month == 24

    def test_end_month_validation_positive(self):
        """Test that end_month must be >= 1."""
        # Valid: end_month >= 1
        sweep = CashSweep(mode=SweepMode.TRAP, end_month=1)
        assert sweep.end_month == 1

        # Invalid: end_month < 1
        with pytest.raises(ValueError):
            CashSweep(mode=SweepMode.TRAP, end_month=0)

        with pytest.raises(ValueError):
            CashSweep(mode=SweepMode.TRAP, end_month=-5)


class TestTrapModeDeposits:
    """Test TRAP mode sweep deposit behavior."""

    def test_trap_mode_deposits(self):
        """Test TRAP mode posts deposits for excess cash."""
        # Setup with REAL ledger (no complex mocks)
        sweep = CashSweep(mode=SweepMode.TRAP, end_month=3)
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=6)

        # Create real ledger and post NOI
        ledger = Ledger()
        noi_series = pd.Series(
            [100_000, 150_000, 200_000, 250_000, 300_000, 350_000],
            index=timeline.period_index,
        )

        # Post NOI transactions as operating revenue
        ledger.add_series(
            noi_series,
            SeriesMetadata(
                item_name="Property Operations",
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.LEASE,
                source_id=uuid4(),
                asset_id=uuid4(),
                pass_num=1,
            ),
        )

        # Create context with real ledger
        context = Mock()
        context.timeline = timeline
        context.ledger = ledger

        # Mock deal and facility
        facility = Mock(spec=ConstructionFacility)
        facility.name = "Construction Facility"
        facility.uid = uuid4()  # Required for ledger posting
        deal = Mock()
        deal.financing.facilities = [facility]
        context.deal = deal

        # Execute
        sweep.process(context, "Construction Facility")

        # Query ledger for sweep deposits and releases
        ledger_df = ledger.to_dataframe()
        deposits = ledger_df[ledger_df["subcategory"] == "Cash Sweep Deposit"]
        releases = ledger_df[ledger_df["subcategory"] == "Cash Sweep Release"]

        # Assert: Should have 2 deposits (months 1-2) + 1 release (month 3)
        assert len(deposits) == 2, f"Expected 2 deposits, got {len(deposits)}"
        assert len(releases) == 1, f"Expected 1 release, got {len(releases)}"

        # Check deposit amounts are negative (cash trapped)
        for amount in deposits["amount"]:
            assert amount < 0, f"Deposit should be negative, got {amount}"

        # Check release amount is positive (cash released)
        release_amount = releases["amount"].iloc[0]
        assert release_amount > 0, f"Release should be positive, got {release_amount}"

        # Verify total balance: deposits + release should net to zero
        total_deposited = abs(deposits["amount"].sum())
        total_released = releases["amount"].sum()
        assert (
            abs(total_deposited - total_released) < 1.0
        ), f"Deposits ({total_deposited}) and releases ({total_released}) should balance"


class TestTrapModeRelease:
    """Test TRAP mode sweep release behavior."""

    def test_trap_mode_release(self):
        """Test TRAP mode releases trapped cash at end_month."""
        # Setup with REAL ledger
        sweep = CashSweep(mode=SweepMode.TRAP, end_month=2)
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=4)

        # Create real ledger and post NOI
        ledger = Ledger()
        noi_series = pd.Series(
            [50_000, 50_000, 50_000, 50_000], index=timeline.period_index
        )
        ledger.add_series(
            noi_series,
            SeriesMetadata(
                item_name="Property Operations",
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.LEASE,
                source_id=uuid4(),
                asset_id=uuid4(),
                pass_num=1,
            ),
        )

        # Create context
        context = Mock()
        context.timeline = timeline
        context.ledger = ledger
        facility = Mock(spec=ConstructionFacility)
        facility.name = "Test Facility"
        facility.uid = uuid4()
        deal = Mock()
        deal.financing.facilities = [facility]
        context.deal = deal

        # Execute
        sweep.process(context, "Test Facility")

        # Query ledger
        ledger_df = ledger.to_dataframe()
        deposits = ledger_df[ledger_df["subcategory"] == "Cash Sweep Deposit"]
        releases = ledger_df[ledger_df["subcategory"] == "Cash Sweep Release"]

        # Assert: 1 deposit (month 1) + 1 release (month 2) = 2 total
        assert len(deposits) == 1, f"Expected 1 deposit, got {len(deposits)}"
        assert len(releases) == 1, f"Expected 1 release, got {len(releases)}"

        # Check deposit
        assert deposits["amount"].iloc[0] < 0, "Deposit should be negative"

        # Check release
        release_amount = releases["amount"].iloc[0]
        assert release_amount > 0, "Release should be positive"
        assert (
            release_amount == 50_000
        ), f"Release should equal deposit, got {release_amount}"

        # Verify release occurs at end_month (month 2, index 1)
        release_date = pd.Timestamp(releases["date"].iloc[0])
        expected_date = timeline.period_index[1].to_timestamp()
        assert (
            release_date == expected_date
        ), f"Release should occur at {expected_date}, got {release_date}"


class TestNoSweepOnZeroExcess:
    """Test that sweep doesn't trigger when no excess cash."""

    def test_no_sweep_on_zero_excess(self):
        """Test sweep doesn't trigger when NOI is zero or negative."""
        # Setup
        sweep = CashSweep(mode=SweepMode.TRAP, end_month=3)

        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=4)

        # Mock queries - zero/negative NOI
        noi_series = pd.Series(
            [0, -50_000, 0, 100_000],  # No excess until month 4
            index=timeline.period_index,
        )

        # Mock empty debt service
        ledger_df = pd.DataFrame({
            "entity": [],
            "date": [],
            "category": [],
            "subcategory": [],
            "amount": [],
        })

        # Create mock context
        context, facility = create_mock_context(timeline, noi_series, ledger_df)

        # Execute
        sweep.process(context, "Test Facility")

        # Assert: No sweep deposits (months 1-3 had no excess)
        # But sweep ends at month 3, so no transactions at all
        assert context.ledger.add_series.call_count == 0

    def test_no_sweep_when_debt_service_exceeds_noi(self):
        """Test sweep doesn't trigger when debt service exceeds NOI."""
        # Setup
        sweep = CashSweep(mode=SweepMode.TRAP, end_month=3)
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=4)

        # Mock positive NOI
        noi_series = pd.Series(
            [100_000, 100_000, 100_000, 100_000], index=timeline.period_index
        )

        # Mock debt service that exceeds NOI
        ledger_df = pd.DataFrame({
            "entity": ["Test Facility"] * 4,
            "date": list(timeline.period_index),
            "category": ["Financing"] * 4,
            "subcategory": ["Interest Payment"] * 4,
            "amount": [-150_000, -150_000, -150_000, -150_000],  # Exceeds NOI
        })

        # Create mock context
        context, facility = create_mock_context(timeline, noi_series, ledger_df)

        # Execute
        sweep.process(context, "Test Facility")

        # Assert: No sweep (debt service exceeds NOI, so no excess cash)
        assert context.ledger.add_series.call_count == 0


class TestFacilityNotFound:
    """Test error handling when facility not found."""

    def test_facility_not_found_raises_error(self):
        """Test that process() raises ValueError if facility not found."""
        # Setup
        sweep = CashSweep(mode=SweepMode.TRAP, end_month=2)

        # Mock context
        context = Mock()
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=2)
        context.timeline = timeline

        # Mock empty facilities list
        deal = Mock()
        deal.financing.facilities = []
        context.deal = deal

        # Execute and assert
        with pytest.raises(ValueError, match="Facility not found"):
            sweep.process(context, "Nonexistent Facility")


class TestPrepaySweeInterestSignConvention:
    """
    Test sign convention for interest paid from sweep in PREPAY mode.
    
    This test suite ensures the sign convention bug is prevented:
    - Interest payments are ALWAYS negative (debt service outflow)
    - Even when paid from sweep instead of reserve
    - Validates the fix for the sign convention violation
    """

    def test_prepay_sweep_interest_payment_sign_convention(self):
        """
        Test that interest paid from sweep is recorded as NEGATIVE (debt service).
        
        Scenario: Construction with pre-leased units generating NOI
        - NOI during construction pays interest directly (sweep)
        - Interest from sweep must be posted as negative (outflow)
        - This prevents the sign convention violation caught in code review
        """
        # Setup: Construction loan with PREPAY sweep
        sweep = CashSweep(mode=SweepMode.PREPAY, end_month=12)
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        
        facility = ConstructionFacility(
            name="Test Construction",
            interest_rate=InterestRate(details=FixedRate(rate=0.08)),
            ltc_ratio=0.70,
            loan_term_months=12,
            cash_sweep=sweep,
        )
        
        # Create real ledger with NOI during construction (pre-leased units)
        ledger = Ledger()
        noi_amount = 100_000.0  # Monthly NOI from pre-leased units
        
        # Post NOI for all periods (simulates pre-leased revenue)
        noi_series = pd.Series(
            [noi_amount] * len(timeline.period_index),
            index=timeline.period_index
        )
        ledger.add_series(
            noi_series,
            SeriesMetadata(
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.LEASE,
                item_name="Pre-Leased Revenue",
                source_id="test-source",
                asset_id="test-asset",
                pass_num=1,
            )
        )
        
        # Create real context with capital uses to trigger draws
        settings = GlobalSettings()
        mock_deal = Mock()
        mock_deal.name = "Test Deal"
        mock_deal.asset = Mock()
        mock_deal.asset.uid = "test-asset"
        
        # Mock capital plan with draws
        mock_capital_plan = Mock()
        mock_capital_plan.total_budget = 10_000_000.0
        mock_deal.asset.capital_plan = mock_capital_plan
        
        context = DealContext(
            timeline=timeline,
            settings=settings,
            deal=mock_deal,
            ledger=ledger,
        )
        
        # Post some capital uses to trigger loan draws and interest
        capital_uses_series = pd.Series(
            [-1_000_000.0] * 6,  # First 6 months
            index=timeline.period_index[:6]
        )
        ledger.add_series(
            capital_uses_series,
            SeriesMetadata(
                category=CashFlowCategoryEnum.CAPITAL,
                subcategory="Hard Costs",
                item_name="Construction Costs",
                source_id="test-source",
                asset_id="test-asset",
                pass_num=1,
            )
        )
        
        # Compute cash flows (this executes the sweep logic)
        result = facility.compute_cf(context)
        
        # Verify interest from sweep exists and is NEGATIVE
        ledger_df = ledger.to_dataframe()
        interest_from_sweep = ledger_df[
            ledger_df["item_name"].str.contains("Interest \\(from sweep\\)", na=False, regex=True)
        ]
        
        # CRITICAL ASSERTIONS: Sign Convention
        assert len(interest_from_sweep) > 0, \
            "Should have interest from sweep (NOI pays interest)"
        
        assert (interest_from_sweep["amount"] < 0).all(), \
            "Interest from sweep MUST be negative (debt service outflow)"
        
        assert interest_from_sweep["subcategory"].iloc[0] == "Interest Payment", \
            "Should be categorized as Interest Payment"
        
        total_interest_from_sweep = interest_from_sweep["amount"].sum()
        print(f"\n✓ Interest from sweep correctly recorded as NEGATIVE")
        print(f"  Total interest paid from sweep: ${total_interest_from_sweep:,.0f}")
        print(f"  Number of periods with sweep interest: {len(interest_from_sweep)}")
        
        # Additional validation: Verify it's in debt service query results
        queries = LedgerQueries(ledger)
        debt_service = queries.debt_service()
        
        # Interest from sweep should be included in debt service
        assert debt_service.sum() < 0, "Debt service total should be negative"
        print(f"  Included in debt_service() query: ${debt_service.sum():,.0f}")

    def test_prepay_sweep_interest_vs_reserve_parity(self):
        """
        Test that interest from sweep has same sign as interest from reserve.
        
        Both should be negative (debt service), just different sources.
        """
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        
        # Scenario A: Interest from reserve (no NOI, no sweep)
        facility_reserve = ConstructionFacility(
            name="Reserve Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.08)),
            ltc_ratio=0.70,
            loan_term_months=12,
            cash_sweep=None,  # No sweep - uses reserve
        )
        
        ledger_reserve = Ledger()
        settings = GlobalSettings()
        mock_deal_reserve = Mock()
        mock_deal_reserve.name = "Reserve Deal"
        mock_deal_reserve.asset = Mock()
        mock_deal_reserve.asset.uid = "test-asset-reserve"
        mock_capital_plan = Mock()
        mock_capital_plan.total_budget = 5_000_000.0
        mock_deal_reserve.asset.capital_plan = mock_capital_plan
        
        context_reserve = DealContext(
            timeline=timeline,
            settings=settings,
            deal=mock_deal_reserve,
            ledger=ledger_reserve,
        )
        
        # Post capital uses
        capital_uses = pd.Series(
            [-500_000.0] * 6,
            index=timeline.period_index[:6]
        )
        ledger_reserve.add_series(
            capital_uses,
            SeriesMetadata(
                category=CashFlowCategoryEnum.CAPITAL,
                subcategory="Hard Costs",
                item_name="Construction",
                source_id="test-source-reserve",
                asset_id="test-asset-reserve",
                pass_num=1,
            )
        )
        
        facility_reserve.compute_cf(context_reserve)
        
        # Scenario B: Interest from sweep (with NOI)
        facility_sweep = ConstructionFacility(
            name="Sweep Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.08)),
            ltc_ratio=0.70,
            loan_term_months=12,
            cash_sweep=CashSweep(mode=SweepMode.PREPAY, end_month=12),
        )
        
        ledger_sweep = Ledger()
        mock_deal_sweep = Mock()
        mock_deal_sweep.name = "Sweep Deal"
        mock_deal_sweep.asset = Mock()
        mock_deal_sweep.asset.uid = "test-asset-sweep"
        mock_deal_sweep.asset.capital_plan = mock_capital_plan
        
        context_sweep = DealContext(
            timeline=timeline,
            settings=settings,
            deal=mock_deal_sweep,
            ledger=ledger_sweep,
        )
        
        # Post capital uses AND NOI
        capital_uses_sweep = pd.Series(
            [-500_000.0] * 6,
            index=timeline.period_index[:6]
        )
        ledger_sweep.add_series(
            capital_uses_sweep,
            SeriesMetadata(
                category=CashFlowCategoryEnum.CAPITAL,
                subcategory="Hard Costs",
                item_name="Construction",
                source_id="test-source-sweep",
                asset_id="test-asset-sweep",
                pass_num=1,
            )
        )
        
        noi_sweep = pd.Series(
            [50_000.0] * 6,
            index=timeline.period_index[:6]
        )
        ledger_sweep.add_series(
            noi_sweep,
            SeriesMetadata(
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.LEASE,
                item_name="Pre-Leased Revenue",
                source_id="test-source-sweep",
                asset_id="test-asset-sweep",
                pass_num=1,
            )
        )
        
        facility_sweep.compute_cf(context_sweep)
        
        # Compare: Both should have negative interest
        df_reserve = ledger_reserve.to_dataframe()
        df_sweep = ledger_sweep.to_dataframe()
        
        interest_reserve = df_reserve[
            df_reserve["item_name"].str.contains("Capitalized Interest", na=False)
        ]
        interest_sweep_items = df_sweep[
            df_sweep["item_name"].str.contains("Interest \\(from sweep\\)", na=False, regex=True)
        ]
        
        if len(interest_sweep_items) > 0:
            # Both types of interest should be negative
            assert (interest_reserve["amount"] < 0).all(), \
                "Interest from reserve must be negative"
            assert (interest_sweep_items["amount"] < 0).all(), \
                "Interest from sweep must be negative"
            
            print("\n✓ Sign parity confirmed:")
            print(f"  Interest from reserve: NEGATIVE ✓")
            print(f"  Interest from sweep:   NEGATIVE ✓")
        else:
            print("\n✓ Sweep had no effect (NOI insufficient), reserve used")
