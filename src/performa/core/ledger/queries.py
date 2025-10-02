# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Ledger query layer for DuckDB-backed transactions.

This module implements all query methods against the transactional ledger.
There are no alternate backends or fallbacks; results are produced via SQL
and returned as pandas objects with consistent time indexing.

Features:
- SQL-optimized aggregations for financial calculations
- Consistent API used throughout the codebase
- Monthly PeriodIndex outputs for time series
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import pandas as pd

from ..primitives.enums import (
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
    FinancingSubcategoryEnum,
    RevenueSubcategoryEnum,
    TransactionPurpose,
    ValuationSubcategoryEnum,
    enum_to_string,
)

if TYPE_CHECKING:
    from .ledger import Ledger

################################################################################
# SUBCATEGORY GROUPINGS (EXACT COPY FROM queries_main.py)
################################################################################

# === FINANCING SUBCATEGORY GROUPINGS ===

# Debt service payments using disaggregated I&P approach [NEGATIVE AMOUNTS]
DEBT_SERVICE_SUBCATEGORIES = [
    FinancingSubcategoryEnum.INTEREST_PAYMENT,  # Interest payments
    FinancingSubcategoryEnum.PRINCIPAL_PAYMENT,  # Principal payments
]

# Debt funding sources [POSITIVE AMOUNTS]
DEBT_FUNDING_SUBCATEGORIES = [
    FinancingSubcategoryEnum.LOAN_PROCEEDS,  # Initial loan funding
    FinancingSubcategoryEnum.REFINANCING_PROCEEDS,  # Refinancing proceeds
]

# Debt payoff methods [NEGATIVE AMOUNTS]
DEBT_PAYOFF_SUBCATEGORIES = [
    FinancingSubcategoryEnum.PREPAYMENT,  # Loan payoff at disposition
    FinancingSubcategoryEnum.REFINANCING_PAYOFF,  # Refinancing payoff
]

# All debt cash outflows: recurring service + one-time payoffs [NEGATIVE AMOUNTS]
# Use this for complete debt outflow calculations (levered CF, total debt costs)
# Separates semantically:
#   - DEBT_SERVICE_SUBCATEGORIES: Recurring obligations (I+P)
#   - DEBT_PAYOFF_SUBCATEGORIES: One-time financing events (payoffs)
#   - ALL_DEBT_OUTFLOWS_SUBCATEGORIES: Complete picture for cash flow analysis
ALL_DEBT_OUTFLOWS_SUBCATEGORIES = DEBT_SERVICE_SUBCATEGORIES + DEBT_PAYOFF_SUBCATEGORIES

# Equity partner flows [MIXED AMOUNTS]
EQUITY_PARTNER_SUBCATEGORIES = [
    FinancingSubcategoryEnum.EQUITY_CONTRIBUTION,  # Partner contributions (+)
    FinancingSubcategoryEnum.EQUITY_DISTRIBUTION,  # Distributions (-)
    FinancingSubcategoryEnum.PREFERRED_RETURN,  # Preferred returns (-)
    FinancingSubcategoryEnum.PROMOTE,  # Promote payments (-)
]

# Debt balance tracking
DEBT_INCREASE_SUBCATEGORIES = DEBT_FUNDING_SUBCATEGORIES  # [POSITIVE AMOUNTS]
DEBT_DECREASE_SUBCATEGORIES = [  # [NEGATIVE AMOUNTS]
    FinancingSubcategoryEnum.PRINCIPAL_PAYMENT,  # Principal reduces balance
    FinancingSubcategoryEnum.PREPAYMENT,  # Full payoff
    FinancingSubcategoryEnum.REFINANCING_PAYOFF,  # Refinancing payoff
]

# === REVENUE SUBCATEGORY GROUPINGS ===

# Gross revenue sources [POSITIVE AMOUNTS]
GROSS_REVENUE_SUBCATEGORIES = [
    RevenueSubcategoryEnum.LEASE,  # Base rent revenue
    RevenueSubcategoryEnum.MISC,  # Miscellaneous income
    RevenueSubcategoryEnum.RECOVERY,  # Expense recoveries
]

# Revenue adjustments [NEGATIVE AMOUNTS]
REVENUE_LOSS_SUBCATEGORIES = [
    RevenueSubcategoryEnum.VACANCY_LOSS,  # Vacancy losses
    RevenueSubcategoryEnum.CREDIT_LOSS,  # Bad debt losses
    RevenueSubcategoryEnum.ABATEMENT,  # Rental concessions
]

# All revenue components [MIXED AMOUNTS]
ALL_REVENUE_SUBCATEGORIES = GROSS_REVENUE_SUBCATEGORIES + REVENUE_LOSS_SUBCATEGORIES

# Tenant-sourced revenue only [POSITIVE AMOUNTS]
TENANT_REVENUE_SUBCATEGORIES = [
    RevenueSubcategoryEnum.LEASE,  # Base rent
    RevenueSubcategoryEnum.RECOVERY,  # Expense recoveries
]

# === CAPITAL SUBCATEGORY GROUPINGS ===

# Acquisition capital [NEGATIVE AMOUNTS]
ACQUISITION_CAPITAL_SUBCATEGORIES = [
    CapitalSubcategoryEnum.PURCHASE_PRICE,  # Property acquisition
    CapitalSubcategoryEnum.CLOSING_COSTS,  # Closing costs
    CapitalSubcategoryEnum.DUE_DILIGENCE,  # Due diligence
]

# Construction capital [NEGATIVE AMOUNTS]
CONSTRUCTION_CAPITAL_SUBCATEGORIES = [
    CapitalSubcategoryEnum.HARD_COSTS,  # Construction costs
    CapitalSubcategoryEnum.SOFT_COSTS,  # Soft costs
    CapitalSubcategoryEnum.SITE_WORK,  # Site work
]

# Disposition capital [NEGATIVE AMOUNTS]
DISPOSITION_CAPITAL_SUBCATEGORIES = [
    CapitalSubcategoryEnum.TRANSACTION_COSTS,  # Transaction costs
]

# All capital uses [NEGATIVE AMOUNTS]
ALL_CAPITAL_USE_SUBCATEGORIES = (
    ACQUISITION_CAPITAL_SUBCATEGORIES
    + CONSTRUCTION_CAPITAL_SUBCATEGORIES
    + DISPOSITION_CAPITAL_SUBCATEGORIES
    + [CapitalSubcategoryEnum.OTHER]
)

# === EXPENSE SUBCATEGORY GROUPINGS ===

# Operating expenses [NEGATIVE AMOUNTS]
OPERATING_EXPENSE_SUBCATEGORIES = [
    ExpenseSubcategoryEnum.OPEX,  # Operating expenses
]

# Capital expenses [NEGATIVE AMOUNTS]
CAPITAL_EXPENSE_SUBCATEGORIES = [
    ExpenseSubcategoryEnum.CAPEX,  # Capital expenditures
]

# All expenses [NEGATIVE AMOUNTS]
ALL_EXPENSE_SUBCATEGORIES = (
    OPERATING_EXPENSE_SUBCATEGORIES + CAPITAL_EXPENSE_SUBCATEGORIES
)

# === FINANCING FEE SUBCATEGORY GROUPINGS ===

# Financing fees [NEGATIVE AMOUNTS]
FINANCING_FEE_SUBCATEGORIES = [
    FinancingSubcategoryEnum.ORIGINATION_FEE,  # Origination fees
    FinancingSubcategoryEnum.EXIT_FEE,  # Exit fees
    FinancingSubcategoryEnum.PREPAYMENT_PENALTY,  # Prepayment penalties
]

# === VALUATION SUBCATEGORY GROUPINGS ===

# Valuation methods [ZERO CASH FLOW]
ALL_VALUATION_SUBCATEGORIES = [
    ValuationSubcategoryEnum.ASSET_VALUATION,  # Asset appraisals
    ValuationSubcategoryEnum.COMPARABLE_SALES,  # Comparable sales
    ValuationSubcategoryEnum.DCF_VALUATION,  # DCF valuations
    ValuationSubcategoryEnum.DIRECT_CAP_VALUATION,  # Direct cap method
    ValuationSubcategoryEnum.COST_APPROACH,  # Cost approach
    ValuationSubcategoryEnum.BROKER_OPINION,  # Broker opinions
]


################################################################################
# DUCKDB LEDGER QUERIES
################################################################################


class LedgerQueries:  # noqa: PLR0904
    """
    Comprehensive ledger query interface for real estate financial analysis.

    This class provides a complete set of methods to extract standard real estate
    financial metrics from transaction ledgers. It uses optimized SQL queries for
    performance while maintaining complete compatibility with the pandas implementation.

    **Core Financial Metrics:**
    - **Revenue Analysis**: `tenant_revenue()`, `vacancy_loss()`, `credit_loss()`
    - **Operating Expenses**: `opex()`, `property_management()`, `taxes_insurance()`  
    - **Capital Expenditures**: `capex()`, `ti()` (tenant improvements), `lc()` (leasing commissions)
    - **Cash Flow Composition**: `noi()` (Net Operating Income), `operational_cash_flow()`
    - **Project Analysis**: `project_cash_flow()`, `levered_cash_flow()`
    - **Financing**: `debt_service()`, `equity_contributions()`, `distributions()`
    - **Valuations**: `asset_valuations()` (appraisals and market values)

    **Key Features:**
    - All methods return pandas Series with Period index (monthly frequency)
    - Automatic exclusion of non-cash valuation entries from cash flow calculations  
    - Consistent sign conventions following real estate industry standards
    - Built-in data validation and error handling
    - High performance for large transaction datasets

    **Usage Examples:**
    ```python
    # Basic cash flow analysis
    queries = LedgerQueries(ledger)
    
    # Get Net Operating Income time series
    noi_series = queries.noi()
    annual_noi = noi_series.sum()
    
    # Calculate debt service coverage ratio
    debt_payments = queries.debt_service() 
    dscr_series = noi_series / debt_payments.abs()
    
    # Project-level cash flows for IRR calculation
    project_cf = queries.project_cash_flow()
    levered_cf = queries.levered_cash_flow()
    ```

    Args:
        ledger: Ledger instance containing transaction records with the standard
               schema (date, amount, category, subcategory, flow_purpose, etc.)
    """

    def __init__(self, ledger: "Ledger"):
        """
        Initialize with a DuckDB-backed ledger.

        Args:
            ledger: Ledger instance that provides get_query_connection()
        """
        # Require a DuckDB-backed Ledger
        self.con, self.table_name = ledger.get_query_connection()
        self._ledger = ledger
        self._cache_version = ledger.get_version() if hasattr(ledger, "get_version") else -1
        self._series_cache = {}

    @property
    def ledger(self) -> pd.DataFrame:
        """
        Access the ledger materialized as a read-only pandas DataFrame.
        Returned view is intended for ad hoc analysis not covered by
        dedicated query methods.
        
        Returns:
            Complete ledger as a pandas DataFrame
        """
        return self._ledger.to_dataframe()

    def _execute_query_to_series(
        self,
        sql: str,
        date_col: str = "month",
        value_col: str = "total_amount",
        series_name: str = None,
    ) -> pd.Series:
        """
        Execute a SQL query and format the result as a pandas Series.

        This is the core helper method that converts DuckDB query results into
        the pandas Series format expected by existing code. Handles empty results,
        date conversion, and monthly resampling.

        Args:
            sql: SQL query to execute
            date_col: Column name containing date values
            value_col: Column name containing numeric values
            series_name: Name for the resulting Series

        Returns:
            Pandas Series with PeriodIndex (monthly frequency) and float values
        """
        try:
            # Versioned cache: invalidate on ledger version change
            current_version = self._ledger.get_version() if hasattr(self._ledger, "get_version") else -1
            if current_version != self._cache_version:
                self._series_cache.clear()
                self._cache_version = current_version

            cache_key = (sql, date_col, value_col, series_name)
            cached = self._series_cache.get(cache_key)
            if cached is not None:
                return cached.copy()

            reader = self.con.execute(sql).arrow()
            tbl = reader.read_all()
            if tbl.num_rows == 0:
                return pd.Series(dtype="float64", name=series_name)

            # Extract columns directly to pandas without building an intermediate DataFrame
            dates = pd.to_datetime(tbl[date_col].to_pandas(date_as_object=False))
            values = tbl[value_col].to_pandas()

            # Build Series and ensure month aggregation (DATE_TRUNC already monthly)
            series = pd.Series(values.values, index=dates.values)

            # Convert to PeriodIndex for compatibility with existing code expectations
            series.index = pd.PeriodIndex(series.index, freq="M")

            # Reindex to full monthly range between first and last month (fill gaps with zeros)
            if len(series.index) > 0:
                full_range = pd.period_range(series.index.min(), series.index.max(), freq="M")
                series = series.reindex(full_range, fill_value=0.0)

            if series_name:
                series.name = series_name

            # Store in cache and return
            self._series_cache[cache_key] = series
            return series.copy()

        except Exception as e:
            # Return empty series on any error to maintain compatibility
            return pd.Series(dtype="float64", name=series_name)

    def _subcategory_in_clause(self, subcategories: list) -> str:
        """
        Generate SQL IN clause for subcategory filtering.

        Converts enum objects to their string values using enum_to_string()
        to ensure perfect consistency with ledger data.

        Args:
            subcategories: List of subcategory enum objects or strings

        Returns:
            SQL IN clause string
        """
        # Convert enum objects to strings using enum_to_string for consistency
        string_values = [enum_to_string(sub) for sub in subcategories]
        quoted_subcategories = [f"'{sub}'" for sub in string_values]
        return f"({', '.join(quoted_subcategories)})"

    # === Core Operating Metrics ===

    def pgr(self) -> pd.Series:
        """
        Potential Gross Revenue = All revenue at 100% occupancy.

        Calculates total potential revenue before vacancy and credit losses
        using SQL aggregation for performance.

        Returns:
            Time series of potential gross revenue by period
        """
        # Pure SQL implementation - NO PANDAS FALLBACK
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) as period,
                SUM(amount) as total
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
                AND category = 'Revenue'
                AND subcategory IN (
                    '{enum_to_string(RevenueSubcategoryEnum.LEASE)}',
                    '{enum_to_string(RevenueSubcategoryEnum.MISC)}',
                    '{enum_to_string(RevenueSubcategoryEnum.RECOVERY)}'
                )
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Potential Gross Revenue")

    def gpr(self) -> pd.Series:
        """
        Gross Potential Rent = Base rent only at 100% physical occupancy.

        Returns base lease revenue at full occupancy before losses.

        Returns:
            Time series of gross potential rent by period
        """
        # Pure SQL implementation - NO PANDAS
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) as period,
                SUM(amount) as total
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
                AND category = 'Revenue'
                AND subcategory = '{enum_to_string(RevenueSubcategoryEnum.LEASE)}'
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Gross Potential Revenue")

    def tenant_revenue(self) -> pd.Series:
        """
        Tenant Revenue = Rent + Recoveries (excludes non-tenant income).

        Industry standard tenant revenue includes all revenue streams that
        originate from tenant obligations: base rent and expense recoveries.
        Excludes miscellaneous income like parking, antenna revenue, etc.

        Returns:
            Time series of tenant revenue by period
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
                AND category = 'Revenue'
                AND subcategory IN {self._subcategory_in_clause(TENANT_REVENUE_SUBCATEGORIES)}
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Tenant Revenue")

    def vacancy_loss(self) -> pd.Series:
        """
        Vacancy losses from the ledger.

        Returns:
            Time series of vacancy losses by period (typically negative values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = '{enum_to_string(TransactionPurpose.OPERATING)}'
                AND category = '{enum_to_string(CashFlowCategoryEnum.REVENUE)}'
                AND subcategory = '{enum_to_string(RevenueSubcategoryEnum.VACANCY_LOSS)}'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Vacancy Loss")

    def egi(self) -> pd.Series:
        """
        Effective Gross Income = Total operating revenue after vacancy/credit losses.

        Industry standard EGI calculation:
        EGI = Potential Gross Revenue - Vacancy Loss - Credit Loss + Other Income

        Returns:
            Time series of effective gross income by period
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
                AND category = 'Revenue'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Effective Gross Income")

    def opex(self) -> pd.Series:
        """
        Operating Expenses from the ledger.

        Returns:
            Time series of operating expenses by period (negative values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE category = '{enum_to_string(CashFlowCategoryEnum.EXPENSE)}'
                AND subcategory = '{enum_to_string(ExpenseSubcategoryEnum.OPEX)}'
                AND flow_purpose != '{enum_to_string(TransactionPurpose.VALUATION)}'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Operating Expenses")

    def noi(self) -> pd.Series:
        """
        Net Operating Income = Operating revenues - expenses.

        Core property performance metric before financing and capital costs.

        Returns:
            Time series of net operating income by period
        """
        # Pure SQL implementation - NO PANDAS
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) as period,
                SUM(amount) as total
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Net Operating Income")

    def capex(self) -> pd.Series:
        """
        Capital expenditures.

        Pure SQL implementation excluding TI and LC which are tracked separately.
        Includes major repairs and improvements but excludes acquisition/disposition costs.

        Returns:
            Time series of capital expenditures by period (negative values)
        """
        # Pure SQL implementation - NO PANDAS FALLBACKS
        # Tiger Team Pattern: Use regexp_matches() for pattern exclusion
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE (
                category = '{enum_to_string(CashFlowCategoryEnum.CAPITAL)}'
                OR (
                    category = '{enum_to_string(CashFlowCategoryEnum.EXPENSE)}'
                    AND subcategory = '{enum_to_string(ExpenseSubcategoryEnum.CAPEX)}'
                )
            )
            AND NOT regexp_matches(item_name, '^TI\\b|\\bTI\\b|Tenant Improvement|^LC\\b|\\bLC\\b|Leasing Commission', 'i')
            AND subcategory NOT IN ('Purchase Price', 'Closing Costs', 'Transaction Costs', 'Other')
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Capital Expenditures")

    def ti(self) -> pd.Series:
        """
        Tenant improvements.

        Pure SQL implementation identifying TI transactions by item_name pattern matching.
        Includes all capital expenditures for tenant space improvements.

        Returns:
            Time series of tenant improvements by period (negative values)
        """
        # Pure SQL implementation - NO PANDAS FALLBACKS  
        # Tiger Team Pattern: Use regexp_matches() for precise pattern matching
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE regexp_matches(item_name, '^TI\\b|\\bTI\\b|Tenant Improvement', 'i')
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Tenant Improvements")

    def lc(self) -> pd.Series:
        """
        Leasing commissions.

        Pure SQL implementation identifying LC transactions by item_name pattern matching.
        Includes all fees paid to brokers for securing tenants.

        Returns:
            Time series of leasing commissions by period (negative values)
        """
        # Pure SQL implementation - NO PANDAS FALLBACKS
        # Tiger Team Pattern: Use regexp_matches() for precise pattern matching
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE regexp_matches(item_name, '^LC\\b|\\bLC\\b|Leasing Commission', 'i')
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Leasing Commissions")

    # NOTE: No `ucf()` method by design. Use
    # - operational_cash_flow() for NOI − CapEx − TI − LC (operations only)
    # - project_cash_flow() for true unlevered cash flow (pre-debt, includes capex and disposition)

    def total_uses(self) -> pd.Series:
        """
        Total capital uses (outflows) from the ledger.

        Returns:
            Time series of total capital uses by period (negative values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Capital Use'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Total Capital Uses")

    def total_sources(self) -> pd.Series:
        """
        Total capital sources (inflows) from the ledger.

        Returns:
            Time series of total capital sources by period (positive values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Capital Source'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Total Capital Sources")

    def uses_breakdown(self) -> pd.DataFrame:
        """
        Capital uses breakdown by subcategory.

        Returns:
            DataFrame with capital expenditures organized by subcategory and time period
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                subcategory,
                SUM(amount) AS amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Capital Use'
            GROUP BY month, subcategory
            ORDER BY month, subcategory
        """
        
        tbl = self.con.execute(sql).arrow().read_all()
        if tbl.num_rows == 0:
            return pd.DataFrame()

        months = pd.PeriodIndex(pd.to_datetime(tbl["month"].to_pandas(date_as_object=False)), freq="M")
        subcats = tbl["subcategory"].to_pandas()
        amounts = tbl["amount"].to_pandas()

        df = pd.DataFrame({"month": months, "subcategory": subcats, "amount": amounts})
        pivoted = df.pivot(index="month", columns="subcategory", values="amount").fillna(0.0)
        return pivoted

    def sources_breakdown(self) -> pd.DataFrame:
        """
        Capital sources breakdown by subcategory.

        Returns:
            DataFrame with capital funding sources organized by subcategory and time period
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                subcategory,
                SUM(amount) AS amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Capital Source'
            GROUP BY month, subcategory
            ORDER BY month, subcategory
        """
        
        tbl = self.con.execute(sql).arrow().read_all()
        if tbl.num_rows == 0:
            return pd.DataFrame()

        months = pd.PeriodIndex(pd.to_datetime(tbl["month"].to_pandas(date_as_object=False)), freq="M")
        subcats = tbl["subcategory"].to_pandas()
        amounts = tbl["amount"].to_pandas()

        df = pd.DataFrame({"month": months, "subcategory": subcats, "amount": amounts})
        pivoted = df.pivot(index="month", columns="subcategory", values="amount").fillna(0.0)
        return pivoted

    def debt_draws(self) -> pd.Series:
        """
        Debt draws/proceeds from the ledger.

        Returns:
            Time series of debt proceeds by period (positive values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE category = 'Financing'
                AND subcategory IN {self._subcategory_in_clause(DEBT_FUNDING_SUBCATEGORIES)}
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Debt Draws")

    def debt_service(self) -> pd.Series:
        """
        Total debt cash outflows: recurring service + one-time payoffs.

        Includes all cash payments related to debt financing:
        - Recurring service (interest + principal payments)
        - One-time payoffs (refinancing payoffs + prepayments at disposition)
        
        This provides a complete picture of debt-related cash outflows for
        cash flow analysis and levered return calculations.
        
        **Semantic Note:**
        Traditionally, "debt service" means only recurring I+P payments. However,
        for cash flow analysis, we need ALL debt outflows. The code maintains
        semantic clarity by separating:
        - DEBT_SERVICE_SUBCATEGORIES: Recurring I+P only
        - DEBT_PAYOFF_SUBCATEGORIES: One-time payoff events
        - ALL_DEBT_OUTFLOWS_SUBCATEGORIES: Combined (used here)

        Returns:
            Time series of all debt outflows by period (negative values)
            
        See Also:
            - QUERY_DEFINITIONS.md Section 7 for canonical definition
        """
        # Pure SQL implementation - NO PANDAS FALLBACKS
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE category = '{enum_to_string(CashFlowCategoryEnum.FINANCING)}'
              AND subcategory IN {self._subcategory_in_clause(ALL_DEBT_OUTFLOWS_SUBCATEGORIES)}
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Debt Service")

    def recurring_debt_service(self) -> pd.Series:
        """
        Recurring debt service payments (interest + principal only).
        
        Returns only recurring debt service obligations (I+P), excluding one-time
        payoff events like refinancing payoffs and prepayments at disposition.
        
        Use this for partnership distribution calculations where refinancing
        proceeds and payoffs should net separately through Capital Source and
        Financing Service flow_purposes.
        
        **When to use:**
        - Partnership distribution calculations (net cash available)
        - Monthly/annual debt service coverage analysis
        - Operating period cash flow analysis
        
        **When NOT to use:**
        - Total debt outflows for levered cash flow (use debt_service() instead)
        - Complete debt cost analysis (use debt_service() instead)
        
        **Semantic distinction:**
        - This method: DEBT_SERVICE_SUBCATEGORIES (recurring I+P only)
        - debt_service(): ALL_DEBT_OUTFLOWS_SUBCATEGORIES (recurring + payoffs)
        
        Returns:
            Time series of recurring debt service by period (negative values)
            
        See Also:
            - debt_service(): All debt outflows including payoffs
            - QUERY_DEFINITIONS.md Section 7 for canonical definition
            
        Example:
            ```python
            # For partnership distributions
            noi = queries.noi()
            recurring_ds = queries.recurring_debt_service()
            available = noi + recurring_ds  # Refinancing nets separately
            
            # For levered cash flow
            debt_total = queries.debt_service()  # Includes payoffs
            ```
        """
        # Pure SQL implementation - uses DEBT_SERVICE_SUBCATEGORIES only
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE category = '{enum_to_string(CashFlowCategoryEnum.FINANCING)}'
              AND subcategory IN {self._subcategory_in_clause(DEBT_SERVICE_SUBCATEGORIES)}
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Recurring Debt Service")

    def equity_contributions(self) -> pd.Series:
        """
        Equity partner contributions from the ledger.

        Pure SQL implementation for partner capital contributions.

        Returns:
            Time series of equity contributions by period (positive values)
        """
        # Pure SQL implementation - NO PANDAS FALLBACKS
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE category = '{enum_to_string(CashFlowCategoryEnum.FINANCING)}'
              AND subcategory = '{enum_to_string(FinancingSubcategoryEnum.EQUITY_CONTRIBUTION)}'
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Equity Contributions")

    def equity_distributions(self) -> pd.Series:
        """
        Equity partner distributions from the ledger (pure distributions only).

        Pure SQL implementation filtered strictly to Equity Distribution subcategory
        to match historical semantics used in equity_multiple computation.

        Returns:
            Time series of equity distributions by period (negative values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE category = '{enum_to_string(CashFlowCategoryEnum.FINANCING)}'
              AND subcategory = '{enum_to_string(FinancingSubcategoryEnum.EQUITY_DISTRIBUTION)}'
            GROUP BY period
            
        """
        return self._execute_query_to_series(sql, "period", "total", "Equity Distributions")

    # NOTE: Prefetch methods removed for clarity; individual queries are cached per ledger version

    def list_partners(self) -> list[str]:
        """
        List unique partner IDs (entity_id) for GP and LP.

        Returns:
            List of unique entity_id values present with entity_type in ('GP','LP').
        """
        con = self._ledger.get_query_connection()
        sql = f"""
            SELECT DISTINCT entity_id
            FROM {self.table_name}
            WHERE entity_type IN ('GP','LP')
        """
        df = con.execute(sql).arrow().read_all().to_pandas()
        if df.empty:
            return []
        # entity_id is UUID in DuckDB; convert to string for external use
        return [str(x) for x in df["entity_id"].tolist()]

    def list_partner_details(self) -> pd.DataFrame:
        """
        List unique partners with their entity_type (GP/LP).

        Returns:
            pandas DataFrame with columns: entity_id (str), entity_type (str)
        """
        con = self._ledger.get_query_connection()
        sql = f"""
            SELECT DISTINCT entity_id, entity_type
            FROM {self.table_name}
            WHERE entity_type IN ('GP','LP')
        """
        df = con.execute(sql).arrow().read_all().to_pandas()
        if df.empty:
            return pd.DataFrame({"entity_id": [], "entity_type": []})
        df["entity_id"] = df["entity_id"].astype(str)
        df["entity_type"] = df["entity_type"].astype(str)
        return df[["entity_id", "entity_type"]]

    def partner_flows(self, partner_id: UUID) -> pd.Series:
        """
        Cash flows for a specific partner.

        Args:
            partner_id: UUID of the partner to analyze

        Returns:
            Time series of partner cash flows by period
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE entity_id = '{partner_id}'
                AND category = 'Financing'
                AND subcategory IN {self._subcategory_in_clause(EQUITY_PARTNER_SUBCATEGORIES)}
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Partner Flows")

    def gp_distributions(self) -> pd.Series:
        """
        General Partner distributions from the ledger.

        Returns:
            Time series of GP distributions by period (negative values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE category = 'Financing'
                AND subcategory IN ('Equity Distribution', 'Promote')
                AND entity_type = 'GP'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "GP Distributions")

    def lp_distributions(self) -> pd.Series:
        """
        Limited Partner distributions from the ledger.

        Returns:
            Time series of LP distributions by period (negative values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE category = 'Financing'
                AND subcategory IN ('Equity Distribution', 'Preferred Return')
                AND entity_type = 'LP'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "LP Distributions")

    def rental_abatement(self) -> pd.Series:
        """
        Rental abatements/concessions from the ledger.

        Returns:
            Time series of rental abatements by period (negative values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
                AND category = 'Revenue'
                AND subcategory = 'Abatement'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Rental Abatement")

    def credit_loss(self) -> pd.Series:
        """
        Credit losses from the ledger.

        Returns:
            Time series of credit losses by period (negative values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
                AND category = 'Revenue'
                AND subcategory = 'Credit Loss'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Credit Loss")

    def misc_income(self) -> pd.Series:
        """
        Miscellaneous income from the ledger.

        Returns:
            Time series of miscellaneous income by period (positive values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
                AND category = 'Revenue'
                AND subcategory = 'Miscellaneous'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Miscellaneous Income")

    def expense_reimbursements(self) -> pd.Series:
        """
        Expense reimbursements from the ledger.

        Returns:
            Time series of expense reimbursements by period (positive values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
                AND category = 'Revenue'
                AND subcategory = 'Recovery'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Expense Reimbursements")

    def revenue(self) -> pd.Series:
        """
        Total revenue from the ledger.

        Returns:
            Time series of total revenue by period
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Operating'
                AND category = 'Revenue'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Total Revenue")

    # === Complex Analysis Methods ===

    def asset_value_at(self, date: pd.Period) -> float:
        """
        Get asset value at a specific date.

        Args:
            date: Period for which to get the asset value

        Returns:
            Asset value at the specified date
        """
        # Convert Period to date string for SQL
        date_str = date.to_timestamp().strftime("%Y-%m-%d")
        
        sql = f"""
            SELECT amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Valuation'
                AND DATE_TRUNC('month', date) = DATE_TRUNC('month', DATE '{date_str}')
                AND category = 'Valuation'
            ORDER BY date DESC
            LIMIT 1
        """
        
        result = self.con.execute(sql).fetchone()
        return float(result[0]) if result else 0.0

    def asset_valuations(self) -> pd.Series:
        """
        Asset valuations over time from the ledger.

        Returns:
            Time series of asset valuations by period
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                AVG(amount) AS avg_valuation
            FROM {self.table_name}
            WHERE flow_purpose = 'Valuation'
                AND category = 'Valuation'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "avg_valuation", "Asset Valuations")

    def capital_uses_by_category(self, as_of_date: pd.Period = None) -> pd.Series:
        """
        Capital expenditures organized by category.

        Args:
            as_of_date: Optional date filter (if None, includes all dates)

        Returns:
            Series of capital uses by subcategory
        """
        date_filter = ""
        if as_of_date:
            date_str = as_of_date.to_timestamp().strftime("%Y-%m-%d")
            date_filter = f"AND date <= DATE '{date_str}'"

        sql = f"""
            SELECT 
                subcategory,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Capital Use'
                {date_filter}
            GROUP BY subcategory
            
        """
        
        tbl = self.con.execute(sql).arrow().read_all()
        if tbl.num_rows == 0:
            return pd.Series(dtype="float64", name="Capital Uses by Category")

        subs = tbl["subcategory"].to_pandas()
        amounts = tbl["total_amount"].to_pandas()
        return pd.Series(amounts.values, index=subs.values, name="Capital Uses by Category")

    def capital_sources_by_category(self, as_of_date: pd.Period = None) -> pd.Series:
        """
        Capital funding sources organized by category.

        Args:
            as_of_date: Optional date filter (if None, includes all dates)

        Returns:
            Series of capital sources by subcategory
        """
        date_filter = ""
        if as_of_date:
            date_str = as_of_date.to_timestamp().strftime("%Y-%m-%d")
            date_filter = f"AND date <= DATE '{date_str}'"

        sql = f"""
            SELECT 
                subcategory,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE flow_purpose = 'Capital Source'
                {date_filter}
            GROUP BY subcategory
            
        """
        
        tbl = self.con.execute(sql).arrow().read_all()
        if tbl.num_rows == 0:
            return pd.Series(dtype="float64", name="Capital Sources by Category")

        subs = tbl["subcategory"].to_pandas()
        amounts = tbl["total_amount"].to_pandas()
        return pd.Series(amounts.values, index=subs.values, name="Capital Sources by Category")

    def operational_cash_flow(self) -> pd.Series:
        """
        Calculate operational cash flow from property operations.

        Operational cash flow represents the net cash generated from day-to-day
        property operations, including rental income, operating expenses, vacancy
        losses, and recurring capital expenditures necessary for ongoing operations.
        
        **Implementation:**
        Uses `flow_purpose='Operating'` exclusively to ensure mutually exclusive
        categorization with capital deployment (`flow_purpose='Capital Use'`).
        This prevents double-counting that would occur if major capital expenditures
        (acquisition, construction, development) were incorrectly included here.
        
        **Includes:**
        - Rental income (Lease revenue)
        - Miscellaneous income (parking, vending, etc.)
        - Expense recoveries (CAM, tax pass-throughs)
        - Operating expenses (utilities, maintenance, management, taxes, insurance)
        - Vacancy and credit losses (contra-revenue)
        - Recurring capital expenditures (if categorized as Expense/CapEx with flow_purpose='Operating')
        
        **Excludes:**
        - Major capital deployments (acquisition, construction, development)
        - Disposition costs and proceeds
        - Debt service and financing costs
        - Equity contributions and distributions
        
        **Note:** This replaces the previous formula-based approach (NOI - CapEx - TI - LC)
        with a direct query on `flow_purpose='Operating'`. The old approach caused
        double-counting when major capital expenditures (category='Capital', 
        flow_purpose='Capital Use') were incorrectly subtracted here and then also
        included in project_cash_flow() via capital_uses().

        Returns:
            pandas.Series: Monthly operational cash flows with Period index.
                          Positive values indicate net cash generation from operations.

        See Also:
            - FLOW_PURPOSE_RULES.md for complete flow_purpose semantics
            - QUERY_DEFINITIONS.md Section 4 for canonical definition
            
        Example:
            ```python
            queries = LedgerQueries(ledger)
            ocf = queries.operational_cash_flow()
            
            # Annual operational cash flow
            annual_ocf = ocf.sum()
            
            # Average monthly OCF
            avg_monthly_ocf = ocf.mean()
            ```
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE flow_purpose = '{enum_to_string(TransactionPurpose.OPERATING)}'
            GROUP BY period
            ORDER BY period
        """
        return self._execute_query_to_series(
            sql, 
            "period", 
            "total", 
            "Operational Cash Flow"
        )

    def project_cash_flow(self) -> pd.Series:
        """
        Calculate complete project-level cash flows before financing effects.

        Project cash flow represents all cash flows generated or required by the
        real estate project itself, excluding how those cash flows are financed
        (debt vs equity). This is the foundation for calculating levered returns.

        **Components Included:**
        - Operational cash flows (NOI minus CapEx, TI, LC)
        - Capital outflows (acquisition costs, construction costs)
        - Disposition proceeds (sale proceeds when property is sold)

        **Components Excluded:**
        - Loan proceeds and equity contributions (financing sources)
        - Debt service payments (financing costs)
        - Non-cash valuation entries (appraisals)

        **Formula:**
        PCF = Operational Cash Flow + Capital Uses + Disposition Proceeds

        Returns:
            pandas.Series: Monthly project cash flows with Period index.
                          Negative values typically occur during development/acquisition.
                          Positive values occur during operations and at disposition.

        Example:
            ```python
            queries = LedgerQueries(ledger)
            pcf = queries.project_cash_flow()
            
            # Total project cash generation
            total_cash_generated = pcf.sum()
            
            # Cash flow during construction (typically negative)
            construction_cf = pcf.loc['2024-01':'2025-12']
            
            # Cash flow during operations (typically positive)
            operations_cf = pcf.loc['2026-01':'2029-12']
            ```
        """
        # Pure SQL implementation following tiger team pattern
        # Get operational cash flows using corrected SQL methods
        operational_cf = self.operational_cash_flow()
        
        # Get capital uses using pure SQL
        capital_uses_sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE flow_purpose = '{enum_to_string(TransactionPurpose.CAPITAL_USE)}'
            GROUP BY period
            
        """
        capital_uses = self._execute_query_to_series(
            capital_uses_sql, "period", "total", "Capital Uses"
        )
        
        # Get disposition proceeds using pure SQL (exclude financing sources)
        disposition_sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS period,
                SUM(amount) AS total
            FROM {self.table_name}
            WHERE flow_purpose = '{enum_to_string(TransactionPurpose.CAPITAL_SOURCE)}'
              AND subcategory NOT IN (
                  '{enum_to_string(FinancingSubcategoryEnum.LOAN_PROCEEDS)}',
                  '{enum_to_string(FinancingSubcategoryEnum.EQUITY_CONTRIBUTION)}',
                  '{enum_to_string(FinancingSubcategoryEnum.REFINANCING_PROCEEDS)}'
              )
            GROUP BY period
            
        """
        disposition_proceeds = self._execute_query_to_series(
            disposition_sql, "period", "total", "Disposition Proceeds"
        )
        
        # Combine capital flows using pandas arithmetic (tiger team approved)
        capital_flows = capital_uses.add(disposition_proceeds, fill_value=0.0)

        # Handle edge cases and combine flows (tiger team approved pattern)
        if operational_cf.empty and capital_flows.empty:
            return pd.Series(dtype=float, name="Project Cash Flow")
        elif operational_cf.empty:
            capital_flows.name = "Project Cash Flow"
            return capital_flows.sort_index()
        elif capital_flows.empty:
            operational_cf.name = "Project Cash Flow"
            return operational_cf.sort_index()
        
        # Combine operational and capital flows using pandas arithmetic
        project_cf = operational_cf.add(capital_flows, fill_value=0.0)
        project_cf.name = "Project Cash Flow"
        
        return project_cf.sort_index()

    def equity_partner_flows(self) -> pd.Series:
        """
        All cash flows to/from equity partners.

        Includes:
        - EQUITY_CONTRIBUTION: Partner capital contributions (positive inflow)
        - EQUITY_DISTRIBUTION: Distributions to equity partners (negative outflow)
        - PREFERRED_RETURN: Preferred return payments (negative outflow)  
        - PROMOTE: Carried interest/promote payments (negative outflow)
        - Partner-specific flows by entity_type (GP/LP)

        Excludes:
        - Non-cash valuation entries (flow_purpose="Valuation")

        Sign convention (from deal perspective):
        - Contributions are positive (cash into deal)
        - Distributions are negative (cash out of deal)

        Returns:
            Time series of equity partner cash flows by period
        """
        # Filter for equity partner transactions by subcategory
        sql_equity = f"""
            SELECT DATE_TRUNC('month', date) AS month, amount
            FROM {self.table_name}
            WHERE category = '{enum_to_string(CashFlowCategoryEnum.FINANCING)}'
                AND subcategory IN {self._subcategory_in_clause(EQUITY_PARTNER_SUBCATEGORIES)}
                AND flow_purpose != '{enum_to_string(TransactionPurpose.VALUATION)}'
        """
        
        # Also capture partner-specific flows if entity_type indicates GP/LP
        sql_partner = f"""
            SELECT DATE_TRUNC('month', date) AS month, amount  
            FROM {self.table_name}
            WHERE entity_type IN ('GP', 'LP')
                AND flow_purpose = '{enum_to_string(TransactionPurpose.CAPITAL_SOURCE)}'
                AND NOT regexp_matches(item_name, 'Exit Sale Proceeds', 'i')
                AND flow_purpose != '{enum_to_string(TransactionPurpose.VALUATION)}'
        """
        
        # Combine equity subcategory flows and partner-specific flows
        combined_sql = f"""
            WITH combined_flows AS (
                SELECT month, amount FROM ({sql_equity})
                UNION ALL
                SELECT month, amount FROM ({sql_partner})
            )
            SELECT 
                month,
                SUM(amount) AS total_amount
            FROM combined_flows
            GROUP BY month
            ORDER BY month
        """
        
        return self._execute_query_to_series(combined_sql, "month", "total_amount", "Equity Partner Flows")

    def debt_balance(self) -> pd.Series:
        """
        Outstanding debt balance over time.

        Returns:
            Time series of cumulative debt balance by period
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(CASE 
                    WHEN subcategory IN {self._subcategory_in_clause(DEBT_INCREASE_SUBCATEGORIES)} THEN amount
                    WHEN subcategory IN {self._subcategory_in_clause(DEBT_DECREASE_SUBCATEGORIES)} THEN -amount
                    ELSE 0 
                END) AS balance_change
            FROM {self.table_name}
            WHERE category = 'Financing'
            GROUP BY month
            ORDER BY month
        """
        
        tbl = self.con.execute(sql).arrow().read_all()
        if tbl.num_rows == 0:
            return pd.Series(dtype="float64", name="Debt Balance")

        months = pd.PeriodIndex(pd.to_datetime(tbl["month"].to_pandas(date_as_object=False)), freq="M")
        changes = tbl["balance_change"].to_pandas()
        series = pd.Series(changes.values, index=months)
        cumulative = series.cumsum()
        cumulative.name = "Debt Balance"
        return cumulative


    def construction_draws(self) -> pd.Series:
        """
        Construction loan draws from the ledger.

        Returns:
            Time series of construction draws by period (positive values)
        """
        sql = f"""
            SELECT 
                DATE_TRUNC('month', date) AS month,
                SUM(amount) AS total_amount
            FROM {self.table_name}
            WHERE category = 'Financing'
                AND subcategory = 'Construction Draw'
            GROUP BY month
            
        """
        return self._execute_query_to_series(sql, "month", "total_amount", "Construction Draws")

    def cumulative_construction_draws(self) -> pd.Series:
        """
        Cumulative construction draws over time.

        Returns:
            Time series of cumulative construction draws by period
        """
        construction_series = self.construction_draws()
        if construction_series.empty:
            return pd.Series(dtype="float64", name="Cumulative Construction Draws")
            
        cumulative = construction_series.cumsum()
        cumulative.name = "Cumulative Construction Draws"
        return cumulative

    def _get_valuation_transactions(self) -> pd.DataFrame:
        """
        Get valuation transactions for internal use.

        Returns:
            DataFrame of valuation transactions
        """
        sql = f"""
            SELECT *
            FROM {self.table_name}
            WHERE flow_purpose = 'Valuation'
            ORDER BY date
        """
        
        tbl = self.con.execute(sql).arrow().read_all()
        if tbl.num_rows == 0:
            return pd.DataFrame()

        dates = pd.to_datetime(tbl["date"].to_pandas(date_as_object=False))
        df = tbl.to_pandas()
        df["date"] = dates
        return df
