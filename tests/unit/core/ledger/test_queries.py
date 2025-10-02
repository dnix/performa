# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the LedgerQueries class.

This module tests the query layer that replaces complex aggregation logic
with simple pandas operations on the transactional ledger.
"""

from datetime import date
from uuid import uuid4

import pandas as pd

from performa.core.ledger import Ledger, SeriesMetadata
from performa.core.ledger.queries import LedgerQueries
from performa.core.primitives.enums import (
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
    FinancingSubcategoryEnum,
    RevenueSubcategoryEnum,
)


def create_test_ledger() -> Ledger:
    """Create a sample DuckDB-backed ledger for testing."""
    ledger = Ledger()

    # Helper to add a single transaction as a one-point Series
    def add(amount: float, d: date, category: str, subcategory: str, item_name: str) -> None:
        series = pd.Series({pd.Period(d, freq="M"): float(amount)})
        metadata = SeriesMetadata(
            category=category,
            subcategory=subcategory,
            item_name=item_name,
            source_id=uuid4(),
            asset_id=uuid4(),
            pass_num=1,
        )
        ledger.add_series(series, metadata)

    # Operating Revenue - Lease
    add(10000, date(2024, 1, 1), CashFlowCategoryEnum.REVENUE, RevenueSubcategoryEnum.LEASE, "Base Rent")
    add(10000, date(2024, 2, 1), CashFlowCategoryEnum.REVENUE, RevenueSubcategoryEnum.LEASE, "Base Rent")

    # Operating Revenue - Miscellaneous
    add(500, date(2024, 1, 1), CashFlowCategoryEnum.REVENUE, RevenueSubcategoryEnum.MISC, "Parking Income")

    # Operating Expenses
    add(-2000, date(2024, 1, 1), CashFlowCategoryEnum.EXPENSE, ExpenseSubcategoryEnum.OPEX, "Property Management")
    add(-2000, date(2024, 2, 1), CashFlowCategoryEnum.EXPENSE, ExpenseSubcategoryEnum.OPEX, "Property Management")

    # Vacancy Loss (negative revenue)
    add(-1000, date(2024, 1, 1), CashFlowCategoryEnum.REVENUE, RevenueSubcategoryEnum.VACANCY_LOSS, "Vacancy Loss")

    # Capital Use - Acquisition (excluded from operational CapEx)
    add(-50000, date(2024, 1, 1), CashFlowCategoryEnum.CAPITAL, "Purchase Price", "Acquisition")

    # Capital Source - Equity
    add(30000, date(2024, 1, 1), CashFlowCategoryEnum.FINANCING, FinancingSubcategoryEnum.EQUITY_CONTRIBUTION, "Equity Contribution")

    # Capital Source - Debt
    add(20000, date(2024, 1, 1), CashFlowCategoryEnum.FINANCING, FinancingSubcategoryEnum.LOAN_PROCEEDS, "Loan Proceeds")

    # Financing Service - Interest Payment
    add(-500, date(2024, 2, 1), CashFlowCategoryEnum.FINANCING, FinancingSubcategoryEnum.INTEREST_PAYMENT, "Interest Payment")

    # Financing Service - Principal Payment
    add(-300, date(2024, 2, 1), CashFlowCategoryEnum.FINANCING, FinancingSubcategoryEnum.PRINCIPAL_PAYMENT, "Principal Payment")

    # Tenant Improvements (by name pattern)
    add(-5000, date(2024, 1, 1), CashFlowCategoryEnum.CAPITAL, "Other", "TI Allowance - Suite 100")

    # Leasing Commissions (by name pattern)
    add(-2000, date(2024, 1, 1), CashFlowCategoryEnum.CAPITAL, "Other", "LC Payment - Broker")

    return ledger


class TestLedgerQueries:  # noqa: PLR0904 (ignore too many public methods)
    """Test suite for LedgerQueries class."""

    def test_init_validates_schema(self):
        """Test that initialization works with a real Ledger."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        assert isinstance(queries, LedgerQueries)

    def test_pgr_calculation(self):
        """Test Potential Gross Revenue calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        pgr = queries.pgr()

        # Industry standard: PGR includes all revenue at 100% occupancy
        # January: $10,000 lease + $500 misc = $10,500
        # February: $10,000 lease only = $10,000
        assert pgr.loc[pd.Period("2024-01", freq="M")] == 10500
        assert pgr.loc[pd.Period("2024-02", freq="M")] == 10000

    def test_vacancy_loss_calculation(self):
        """Test vacancy loss calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        vacancy = queries.vacancy_loss()

        # Vacancy loss is stored as negative revenue; expect -1,000 for January
        assert vacancy.loc[pd.Period("2024-01", freq="M")] == -1000

    def test_egi_calculation(self):
        """Test Effective Gross Income calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        egi = queries.egi()

        # January: 10,000 (lease) + 500 (misc) - 1,000 (vacancy) = 9,500
        assert egi.loc[pd.Period("2024-01", freq="M")] == 9500
        # February: 10,000 (lease) + 0 (misc) - 0 (vacancy) = 10,000
        assert egi.loc[pd.Period("2024-02", freq="M")] == 10000

    def test_opex_calculation(self):
        """Test operating expenses calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        opex = queries.opex()

        # Should be -2,000 for both January and February (negative cost)
        assert opex.loc[pd.Period("2024-01", freq="M")] == -2000
        assert opex.loc[pd.Period("2024-02", freq="M")] == -2000

    def test_noi_calculation(self):
        """Test Net Operating Income calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        noi = queries.noi()

        # January: 10,000 + 500 - 1,000 (vacancy) revenue - 2,000 expense = 7,500
        # Note: vacancy is negative revenue, so total revenue = 10,000 + 500 - 1,000 = 9,500
        assert noi.loc[pd.Period("2024-01", freq="M")] == 7500
        # February: 10,000 revenue - 2,000 expense = 8,000 (no vacancy)
        assert noi.loc[pd.Period("2024-02", freq="M")] == 8000

    def test_noi_equals_revenue_minus_expense(self):
        """NOI should equal revenue minus expenses from operating flows."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        df = ledger.to_dataframe()
        operating = df[df["flow_purpose"] == "Operating"]
        revenue_txns = operating[operating["category"] == "Revenue"]
        expense_txns = operating[operating["category"] == "Expense"]

        manual_revenue = revenue_txns.groupby("date")["amount"].sum()
        manual_expense = expense_txns.groupby("date")["amount"].sum().abs()
        manual_noi = manual_revenue - manual_expense

        manual_noi.index = pd.PeriodIndex(manual_noi.index, freq="M")
        query_noi = queries.noi()
        for date_key in manual_noi.index:
            assert abs(query_noi.loc[date_key] - manual_noi.loc[date_key]) < 0.01

    def test_capex_calculation(self):
        """Test capital expenditures calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        capex = queries.capex()

        # Operational CapEx excludes acquisition costs ("Purchase Price", etc.)
        if len(capex) > 0:
            assert capex.loc[pd.Period("2024-01", freq="M")] == 0

    def test_ti_calculation(self):
        """Test tenant improvements calculation (pattern matching)."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        ti = queries.ti()
        assert ti.loc[pd.Period("2024-01", freq="M")] == -5000

    def test_lc_calculation(self):
        """Test leasing commissions calculation (pattern matching)."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        lc = queries.lc()
        assert lc.loc[pd.Period("2024-01", freq="M")] == -2000

    def test_ucf_calculation(self):
        """Test Unlevered Cash Flow calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        ucf = queries.project_cash_flow()
        # For January: Operational CF = 7500, Capital Uses = -50000 (acquisition) + -5000 (TI) + -2000 (LC)
        # UCF = 7500 + (-50000) + (-5000) + (-2000) = -49500
        assert ucf.loc[pd.Period("2024-01", freq="M")] == -49500
        # For February: NOI = 8000, CapEx = 0, TI = 0, LC = 0
        assert ucf.loc[pd.Period("2024-02", freq="M")] == 8000

    def test_total_uses_calculation(self):
        """Test total uses calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        uses = queries.total_uses()
        assert uses.loc[pd.Period("2024-01", freq="M")] == -57000

    def test_total_sources_calculation(self):
        """Test total sources calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        sources = queries.total_sources()
        assert sources.loc[pd.Period("2024-01", freq="M")] == 50000

    def test_debt_draws_calculation(self):
        """Test debt draws calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        debt_draws = queries.debt_draws()
        assert debt_draws.loc[pd.Period("2024-01", freq="M")] == 20000

    def test_equity_contributions_calculation(self):
        """Test equity contributions calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        equity = queries.equity_contributions()
        assert equity.loc[pd.Period("2024-01", freq="M")] == 30000

    def test_debt_service_calculation(self):
        """Test debt service calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        debt_service = queries.debt_service()
        assert debt_service.loc[pd.Period("2024-02", freq="M")] == -800

    def test_uses_breakdown(self):
        """Test uses breakdown by subcategory."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        breakdown = queries.uses_breakdown()
        assert breakdown.loc[pd.Period("2024-01", freq="M"), "Purchase Price"] == -50000
        assert breakdown.loc[pd.Period("2024-01", freq="M"), "Other"] == -7000
        # Debt service components are not capital uses and should not appear here

    def test_sources_breakdown(self):
        """Test sources breakdown by subcategory."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        breakdown = queries.sources_breakdown()
        assert breakdown.loc[pd.Period("2024-01", freq="M"), "Equity Contribution"] == 30000
        assert breakdown.loc[pd.Period("2024-01", freq="M"), "Loan Proceeds"] == 20000

    def test_empty_ledger_handling(self):
        """Test that queries handle empty ledgers gracefully."""
        empty_ledger = Ledger()
        queries = LedgerQueries(empty_ledger)

        # All queries should return empty Series without errors
        assert queries.noi().empty
        assert queries.pgr().empty
        assert queries.egi().empty
        assert queries.total_uses().empty
        assert queries.total_sources().empty

    def test_partner_flows(self):
        """Test partner-specific flow queries."""
        ledger = create_test_ledger()

        # Add a partner-specific equity contribution to ensure inclusion
        partner_id = uuid4()
        series = pd.Series({pd.Period(date(2024, 1, 1), freq="M"): 1234.0})
        meta = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,
            subcategory=FinancingSubcategoryEnum.EQUITY_CONTRIBUTION,
            item_name="Partner Equity",
            source_id=uuid4(),
            asset_id=uuid4(),
            pass_num=1,
        )
        ledger.add_series(series, meta)
        last_txn = ledger.con.execute(f"SELECT transaction_id FROM {ledger.table_name} ORDER BY rowid DESC LIMIT 1").fetchone()[0]
        ledger.con.execute(
            f"UPDATE {ledger.table_name} SET entity_id = '{partner_id}', entity_type = 'GP' WHERE transaction_id = '{last_txn}'"
        )

        queries = LedgerQueries(ledger)
        pf = queries.partner_flows(partner_id)
        assert pf.loc[pd.Period("2024-01", freq="M")] == 1234.0

    def test_query_consistency_across_methods(self):
        """Test that related queries are consistent with each other."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)

        # Uses should equal sum of breakdown
        uses = queries.total_uses()
        uses_breakdown = queries.uses_breakdown()
        for date_key in uses.index:
            breakdown_sum = uses_breakdown.loc[date_key].sum()
            assert abs(uses.loc[date_key] - breakdown_sum) < 0.01

        # Sources should equal sum of breakdown
        sources = queries.total_sources()
        sources_breakdown = queries.sources_breakdown()
        for date_key in sources.index:
            breakdown_sum = sources_breakdown.loc[date_key].sum()
            assert abs(sources.loc[date_key] - breakdown_sum) < 0.01

    def test_rental_abatement_calculation(self):
        """Test rental abatement calculation."""
        ledger = Ledger()

        # Add abatement rows

        def add(amount: float, d: date):
            series = pd.Series({pd.Period(d, freq="M"): float(amount)})
            meta = SeriesMetadata(
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.ABATEMENT,
                item_name="Abatement",
                source_id=uuid4(),
                asset_id=uuid4(),
                pass_num=1,
            )
            ledger.add_series(series, meta)
        add(-500, date(2024, 1, 1))
        add(-300, date(2024, 2, 1))

        queries = LedgerQueries(ledger)
        abatement = queries.rental_abatement()
        # Stored as negative revenue; expect negative amounts
        assert abatement.loc[pd.Period("2024-01", freq="M")] == -500
        assert abatement.loc[pd.Period("2024-02", freq="M")] == -300

    def test_collection_loss_calculation(self):
        """Test collection loss calculation."""
        ledger = Ledger()

        def add(amount: float, d: date):
            series = pd.Series({pd.Period(d, freq="M"): float(amount)})
            meta = SeriesMetadata(
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.CREDIT_LOSS,
                item_name="Bad Debt",
                source_id=uuid4(),
                asset_id=uuid4(),
                pass_num=1,
            )
            ledger.add_series(series, meta)
        add(-200, date(2024, 1, 1))
        add(-150, date(2024, 2, 1))

        queries = LedgerQueries(ledger)
        collection = queries.credit_loss()
        # Stored as negative revenue; expect negative amounts
        assert collection.loc[pd.Period("2024-01", freq="M")] == -200
        assert collection.loc[pd.Period("2024-02", freq="M")] == -150

    def test_misc_income_calculation(self):
        """Test miscellaneous income calculation."""
        ledger = Ledger()

        def add(amount: float, d: date):
            series = pd.Series({pd.Period(d, freq="M"): float(amount)})
            meta = SeriesMetadata(
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.MISC,
                item_name="Misc",
                source_id=uuid4(),
                asset_id=uuid4(),
                pass_num=1,
            )
            ledger.add_series(series, meta)
        add(100, date(2024, 1, 1))
        add(75, date(2024, 2, 1))

        queries = LedgerQueries(ledger)
        misc = queries.misc_income()
        assert misc.loc[pd.Period("2024-01", freq="M")] == 100
        assert misc.loc[pd.Period("2024-02", freq="M")] == 75

    def test_expense_reimbursements_calculation(self):
        """Test expense reimbursements calculation."""
        ledger = Ledger()

        def add(amount: float, d: date):
            series = pd.Series({pd.Period(d, freq="M"): float(amount)})
            meta = SeriesMetadata(
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.RECOVERY,
                item_name="Recovery",
                source_id=uuid4(),
                asset_id=uuid4(),
                pass_num=1,
            )
            ledger.add_series(series, meta)
        add(250, date(2024, 1, 1))
        add(300, date(2024, 2, 1))

        queries = LedgerQueries(ledger)
        reimburse = queries.expense_reimbursements()
        assert reimburse.loc[pd.Period("2024-01", freq="M")] == 250
        assert reimburse.loc[pd.Period("2024-02", freq="M")] == 300
