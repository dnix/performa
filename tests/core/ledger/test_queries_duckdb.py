# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the DuckDB-based ledger queries implementation.

This module provides comprehensive testing of all SQL-based query methods
to ensure functional parity with the original pandas implementation and
validate query accuracy with various data scenarios.
"""

import uuid

import pandas as pd

from performa.core.ledger import Ledger, LedgerQueries
from performa.core.ledger.records import SeriesMetadata
from performa.core.primitives.enums import (
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
    FinancingSubcategoryEnum,
    RevenueSubcategoryEnum,
    ValuationSubcategoryEnum,
)


class TestLedgerQueries:
    """Comprehensive test suite for DuckDB-based ledger queries."""

    def create_test_ledger(self) -> Ledger:
        """Create a ledger with comprehensive test data for query testing."""
        ledger = Ledger()
        dates = pd.date_range("2024-01-01", periods=3, freq="M")

        # Add revenue data (lease)
        lease_series = pd.Series([1000.0, 1100.0, 1200.0], index=dates)
        lease_metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(lease_series, lease_metadata)

        # Add revenue data (miscellaneous)
        misc_series = pd.Series([50.0, 55.0, 60.0], index=dates)
        misc_metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.MISC,
            item_name="Parking Income",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(misc_series, misc_metadata)

        # Add expense data (opex)
        opex_series = pd.Series([-200.0, -220.0, -240.0], index=dates)
        opex_metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.EXPENSE,
            subcategory=ExpenseSubcategoryEnum.OPEX,
            item_name="Property Management",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(opex_series, opex_metadata)

        # Add expense data (capex)
        capex_series = pd.Series([-500.0, 0.0, -300.0], index=dates)
        capex_metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.EXPENSE,
            subcategory=ExpenseSubcategoryEnum.CAPEX,
            item_name="HVAC Replacement",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(capex_series, capex_metadata)

        # Add financing data (debt service)
        debt_service_series = pd.Series([-100.0, -100.0, -100.0], index=dates)
        debt_service_metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,
            subcategory=FinancingSubcategoryEnum.INTEREST_PAYMENT,
            item_name="Loan Interest",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(debt_service_series, debt_service_metadata)

        return ledger

    def test_initialization(self):
        """Test that DuckDB queries initialize correctly."""
        ledger = Ledger()
        queries = LedgerQueries(ledger)

        # Test that connection is established
        assert queries.con is not None
        assert queries.table_name == "transactions"

    def test_empty_ledger_queries(self):
        """Test all query methods with empty ledger."""
        ledger = Ledger()
        queries = LedgerQueries(ledger)

        # Test that empty queries return empty Series
        assert queries.pgr().empty
        assert queries.gpr().empty
        assert queries.egi().empty
        assert queries.noi().empty
        assert queries.opex().empty
        assert queries.capex().empty
        assert queries.debt_service().empty
        assert queries.revenue().empty

    def test_revenue_queries(self):
        """Test revenue-related query methods."""
        ledger = self.create_test_ledger()
        queries = LedgerQueries(ledger)

        # Test Potential Gross Revenue (lease + misc)
        pgr = queries.pgr()
        assert len(pgr) == 3
        assert pgr.sum() == 3465.0  # (1000+50) + (1100+55) + (1200+60)

        # Test Gross Potential Rent (lease only)
        gpr = queries.gpr()
        assert len(gpr) == 3
        assert gpr.sum() == 3300.0  # 1000 + 1100 + 1200

        # Test Effective Gross Income (all revenue)
        egi = queries.egi()
        assert len(egi) == 3
        assert egi.sum() == 3465.0  # Same as PGR in this test case

        # Test Total Revenue
        revenue = queries.revenue()
        assert len(revenue) == 3
        assert revenue.sum() == 3465.0

        # Test Tenant Revenue (lease only, same as GPR in this case)
        tenant_revenue = queries.tenant_revenue()
        assert len(tenant_revenue) == 3
        assert tenant_revenue.sum() == 3300.0

        # Test Miscellaneous Income
        misc_income = queries.misc_income()
        assert len(misc_income) == 3
        assert misc_income.sum() == 165.0  # 50 + 55 + 60

    def test_expense_queries(self):
        """Test expense-related query methods."""
        ledger = self.create_test_ledger()
        queries = LedgerQueries(ledger)

        # Test Operating Expenses
        opex = queries.opex()
        assert len(opex) == 3
        assert opex.sum() == -660.0  # -200 + -220 + -240

        # Test Capital Expenditures
        capex = queries.capex()
        assert len(capex) == 3  # 3 months total (including zeros from resampling)
        assert capex.sum() == -800.0  # -500 + 0 + -300

    def test_noi_calculation(self):
        """Test Net Operating Income calculation."""
        ledger = self.create_test_ledger()
        queries = LedgerQueries(ledger)

        # NOI = All Operating flows (Revenue + OpEx + CapEx in this case)
        noi = queries.noi()
        assert len(noi) == 3
        assert noi.sum() == 2005.0  # 3465 (revenue) + (-660) (opex) + (-800) (capex)

        # Verify calculation consistency - NOI includes ALL operating flows
        revenue = queries.revenue()
        opex = queries.opex()
        capex = queries.capex()
        expected_noi = (
            revenue.sum() + opex.sum() + capex.sum()
        )  # all expenses are negative
        assert abs(noi.sum() - expected_noi) < 0.01

    def test_cash_flow_queries(self):
        """Test cash flow-related query methods."""
        ledger = self.create_test_ledger()
        queries = LedgerQueries(ledger)

        # Test Unlevered Cash Flow (project-level pre-debt)
        ucf = queries.project_cash_flow()
        assert len(ucf) == 3
        # Project Cash Flow (PCF) = Operational CF + Capital Uses + Disposition Proceeds
        # For this dataset: no capital uses/sources beyond OpEx/CapEx, so
        # Operational CF = Revenue (3465) + OpEx (-660) + CapEx (-800) = 2005
        assert ucf.sum() == 2005.0

    def test_financing_queries(self):
        """Test financing-related query methods."""
        ledger = self.create_test_ledger()
        queries = LedgerQueries(ledger)

        # Test Debt Service
        debt_service = queries.debt_service()
        assert len(debt_service) == 3
        assert debt_service.sum() == -300.0  # -100 * 3

        # Test empty financing queries
        equity_contributions = queries.equity_contributions()
        assert equity_contributions.empty

        debt_draws = queries.debt_draws()
        assert debt_draws.empty

    def test_single_transaction_queries(self):
        """Test queries with single transaction."""
        ledger = Ledger()
        dates = pd.date_range("2024-01-01", periods=1, freq="M")

        # Add single revenue transaction
        series = pd.Series([1000.0], index=dates)
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(series, metadata)

        queries = LedgerQueries(ledger)

        # Test single transaction queries
        pgr = queries.pgr()
        assert len(pgr) == 1
        assert pgr.sum() == 1000.0

        noi = queries.noi()
        assert len(noi) == 1
        assert noi.sum() == 1000.0

    def test_complex_multi_period_data(self):
        """Test queries with complex multi-period data."""
        ledger = Ledger()

        # Create data over 12 months
        dates = pd.date_range("2024-01-01", periods=12, freq="M")

        # Add monthly escalating rent
        rent_amounts = [1000 + (i * 10) for i in range(12)]  # $1000, $1010, $1020...
        rent_series = pd.Series(rent_amounts, index=dates)

        rent_metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Escalating Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(rent_series, rent_metadata)

        queries = LedgerQueries(ledger)

        # Test 12-month data
        pgr = queries.pgr()
        assert len(pgr) == 12

        # Verify escalation pattern
        expected_total = sum(rent_amounts)
        assert abs(pgr.sum() - expected_total) < 0.01

        # Test monthly progression
        assert pgr.iloc[0] == 1000.0  # First month
        assert pgr.iloc[-1] == 1110.0  # Last month (1000 + 11*10)

    def test_date_handling_and_resampling(self):
        """Test proper date handling and monthly resampling."""
        ledger = Ledger()

        # Add data with specific dates
        specific_dates = pd.to_datetime(["2024-01-15", "2024-02-28", "2024-03-10"])
        series = pd.Series([1000.0, 2000.0, 3000.0], index=specific_dates)

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(series, metadata)

        queries = LedgerQueries(ledger)

        # Test that dates are properly aggregated by month
        pgr = queries.pgr()
        assert len(pgr) == 3
        assert pgr.sum() == 6000.0

        # Verify PeriodIndex type for compatibility
        assert isinstance(pgr.index, pd.PeriodIndex)
        assert pgr.index.freq == "M"

    def test_aggregation_accuracy(self):
        """Test accuracy of SQL aggregations."""
        ledger = Ledger()
        dates = pd.date_range("2024-01-01", periods=3, freq="M")

        # Add precise decimal amounts to test floating point accuracy
        precise_amounts = [1000.12, 2000.34, 3000.56]
        series = pd.Series(precise_amounts, index=dates)

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Precise Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(series, metadata)

        queries = LedgerQueries(ledger)

        # Test precise aggregation
        pgr = queries.pgr()
        expected_total = sum(precise_amounts)
        assert abs(pgr.sum() - expected_total) < 0.01

    def test_zero_amount_filtering(self):
        """Test that zero amounts are properly handled."""
        ledger = Ledger()
        dates = pd.date_range("2024-01-01", periods=3, freq="M")

        # Include zero and non-zero amounts
        series = pd.Series([1000.0, 0.0, 2000.0], index=dates)

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Mixed Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(series, metadata)

        queries = LedgerQueries(ledger)

        # Test that query handles zero amounts correctly
        # (Zero filtering happens at ledger level, but resampling fills gaps)
        pgr = queries.pgr()
        assert (
            len(pgr) == 3
        )  # 3 periods due to monthly resampling (includes filled zero)
        assert pgr.sum() == 3000.0  # 1000 + 0 + 2000 (zero added by resampling)

    def test_breakdown_queries(self):
        """Test breakdown query methods that return DataFrames."""
        ledger = self.create_test_ledger()
        queries = LedgerQueries(ledger)

        # Test uses breakdown
        uses_breakdown = queries.uses_breakdown()
        # Should be empty since our test data doesn't have capital uses
        assert isinstance(uses_breakdown, pd.DataFrame)

        # Test sources breakdown
        sources_breakdown = queries.sources_breakdown()
        # Should be empty since our test data doesn't have capital sources
        assert isinstance(sources_breakdown, pd.DataFrame)

    def test_valuation_queries(self):
        """Test valuation-related query methods."""
        ledger = Ledger()
        dates = pd.date_range("2024-01-01", periods=2, freq="M")

        # Add valuation data
        valuation_series = pd.Series([1000000.0, 1050000.0], index=dates)
        valuation_metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.VALUATION,
            subcategory=ValuationSubcategoryEnum.ASSET_VALUATION,
            item_name="Property Appraisal",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(valuation_series, valuation_metadata)

        queries = LedgerQueries(ledger)

        # Test asset valuations
        valuations = queries.asset_valuations()
        assert len(valuations) == 2
        assert valuations.sum() == 2050000.0

        # Test asset value at specific date
        test_period = pd.Period("2024-01", freq="M")
        value_at_date = queries.asset_value_at(test_period)
        assert value_at_date == 1000000.0

    def test_categorical_queries(self):
        """Test capital uses/sources by category queries."""
        ledger = Ledger()
        dates = pd.date_range("2024-01-01", periods=1, freq="M")

        # Add capital data
        series = pd.Series([-1000000.0], index=dates)  # Negative for capital use
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.CAPITAL,
            subcategory="Purchase Price",  # This should map to Capital Use flow_purpose
            item_name="Property Acquisition",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        ledger.add_series(series, metadata)

        queries = LedgerQueries(ledger)

        # Test capital uses by category
        uses_by_category = queries.capital_uses_by_category()
        assert isinstance(uses_by_category, pd.Series)

        # Test capital sources by category
        sources_by_category = queries.capital_sources_by_category()
        assert isinstance(sources_by_category, pd.Series)

    def test_query_method_names_and_types(self):
        """Test that all expected query methods exist and return correct types."""
        ledger = self.create_test_ledger()
        queries = LedgerQueries(ledger)

        # List of methods that should return pd.Series
        series_methods = [
            "pgr",
            "gpr",
            "tenant_revenue",
            "vacancy_loss",
            "egi",
            "opex",
            "noi",
            "capex",
            "ti",
            "lc",
            "project_cash_flow",
            "total_uses",
            "total_sources",
            "debt_draws",
            "debt_service",
            "equity_contributions",
            "gp_distributions",
            "lp_distributions",
            "rental_abatement",
            "credit_loss",
            "misc_income",
            "expense_reimbursements",
            "revenue",
            "operational_cash_flow",
            "project_cash_flow",
            "equity_partner_flows",
            "debt_balance",
            "construction_draws",
            "cumulative_construction_draws",
            "asset_valuations",
        ]

        # Test that all series methods exist and return Series
        for method_name in series_methods:
            assert hasattr(queries, method_name), f"Missing method: {method_name}"
            method = getattr(queries, method_name)
            result = method()
            assert isinstance(result, pd.Series), (
                f"Method {method_name} should return Series"
            )

        # List of methods that should return pd.DataFrame
        dataframe_methods = [
            "uses_breakdown",
            "sources_breakdown",
            "_get_valuation_transactions",
        ]

        # Test that all DataFrame methods exist and return DataFrame
        for method_name in dataframe_methods:
            assert hasattr(queries, method_name), f"Missing method: {method_name}"
            method = getattr(queries, method_name)
            result = method()
            assert isinstance(result, pd.DataFrame), (
                f"Method {method_name} should return DataFrame"
            )

        # Special methods
        assert hasattr(queries, "asset_value_at")
        assert hasattr(queries, "partner_flows")
        assert hasattr(queries, "capital_uses_by_category")
        assert hasattr(queries, "capital_sources_by_category")

        # Test asset_value_at returns float
        test_period = pd.Period("2024-01", freq="M")
        value = queries.asset_value_at(test_period)
        assert isinstance(value, float)

        # Test partner_flows with UUID
        partner_flows = queries.partner_flows(uuid.uuid4())
        assert isinstance(partner_flows, pd.Series)
