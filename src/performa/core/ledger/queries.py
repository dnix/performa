# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Clean semantic queries on the ledger DataFrame.

This module provides the LedgerQueries class that replaces complex aggregation
logic with simple pandas operations on the transactional ledger. Each query
method corresponds to a standard real estate financial metric.

The approach follows the principle: "Reporting becomes an exercise in querying,
not re-calculating." All queries are straightforward pandas operations that
leverage the ledger's flow_purpose classification.
"""

from uuid import UUID

import pandas as pd

from performa.core.primitives.enums import (
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
    FinancingSubcategoryEnum,
    RevenueSubcategoryEnum,
    TransactionPurpose,
    ValuationSubcategoryEnum,
)

################################################################################
# SUBCATEGORY GROUPINGS
################################################################################

# === FINANCING SUBCATEGORY GROUPINGS ===

# Debt service payments using disaggregated I&P approach [NEGATIVE AMOUNTS]
DEBT_SERVICE_SUBCATEGORIES = [
    FinancingSubcategoryEnum.INTEREST_PAYMENT,    # Interest payments
    FinancingSubcategoryEnum.PRINCIPAL_PAYMENT,   # Principal payments
]

# Debt funding sources [POSITIVE AMOUNTS]
DEBT_FUNDING_SUBCATEGORIES = [
    FinancingSubcategoryEnum.LOAN_PROCEEDS,        # Initial loan funding
    FinancingSubcategoryEnum.REFINANCING_PROCEEDS,  # Refinancing proceeds
]

# Debt payoff methods [NEGATIVE AMOUNTS]
DEBT_PAYOFF_SUBCATEGORIES = [
    FinancingSubcategoryEnum.PREPAYMENT,          # Loan payoff at disposition
    FinancingSubcategoryEnum.REFINANCING_PAYOFF,  # Refinancing payoff
]

# Equity partner flows [MIXED AMOUNTS]
EQUITY_PARTNER_SUBCATEGORIES = [
    FinancingSubcategoryEnum.EQUITY_CONTRIBUTION,  # Partner contributions (+)
    FinancingSubcategoryEnum.EQUITY_DISTRIBUTION,  # Distributions (-)
    FinancingSubcategoryEnum.PREFERRED_RETURN,     # Preferred returns (-)
    FinancingSubcategoryEnum.PROMOTE,              # Promote payments (-)
]

# Debt balance tracking
DEBT_INCREASE_SUBCATEGORIES = DEBT_FUNDING_SUBCATEGORIES  # [POSITIVE AMOUNTS]
DEBT_DECREASE_SUBCATEGORIES = [  # [NEGATIVE AMOUNTS]
    FinancingSubcategoryEnum.PRINCIPAL_PAYMENT,   # Principal reduces balance
    FinancingSubcategoryEnum.PREPAYMENT,          # Full payoff
    FinancingSubcategoryEnum.REFINANCING_PAYOFF,  # Refinancing payoff
]

# === REVENUE SUBCATEGORY GROUPINGS ===

# Gross revenue sources [POSITIVE AMOUNTS]
GROSS_REVENUE_SUBCATEGORIES = [
    RevenueSubcategoryEnum.LEASE,     # Base rent revenue
    RevenueSubcategoryEnum.MISC,      # Miscellaneous income
    RevenueSubcategoryEnum.RECOVERY,  # Expense recoveries
]

# Revenue adjustments [NEGATIVE AMOUNTS]
REVENUE_LOSS_SUBCATEGORIES = [
    RevenueSubcategoryEnum.VACANCY_LOSS,  # Vacancy losses
    RevenueSubcategoryEnum.CREDIT_LOSS,   # Bad debt losses
    RevenueSubcategoryEnum.ABATEMENT,     # Rental concessions
]

# All revenue components [MIXED AMOUNTS]
ALL_REVENUE_SUBCATEGORIES = GROSS_REVENUE_SUBCATEGORIES + REVENUE_LOSS_SUBCATEGORIES

# Tenant-sourced revenue only [POSITIVE AMOUNTS]
TENANT_REVENUE_SUBCATEGORIES = [
    RevenueSubcategoryEnum.LEASE,     # Base rent
    RevenueSubcategoryEnum.RECOVERY,  # Expense recoveries
]

# === CAPITAL SUBCATEGORY GROUPINGS ===

# Acquisition capital [NEGATIVE AMOUNTS]
ACQUISITION_CAPITAL_SUBCATEGORIES = [
    CapitalSubcategoryEnum.PURCHASE_PRICE,  # Property acquisition
    CapitalSubcategoryEnum.CLOSING_COSTS,   # Closing costs
    CapitalSubcategoryEnum.DUE_DILIGENCE,   # Due diligence
]

# Construction capital [NEGATIVE AMOUNTS] 
CONSTRUCTION_CAPITAL_SUBCATEGORIES = [
    CapitalSubcategoryEnum.HARD_COSTS,  # Construction costs
    CapitalSubcategoryEnum.SOFT_COSTS,  # Soft costs
    CapitalSubcategoryEnum.SITE_WORK,   # Site work
]

# Disposition capital [NEGATIVE AMOUNTS]
DISPOSITION_CAPITAL_SUBCATEGORIES = [
    CapitalSubcategoryEnum.TRANSACTION_COSTS,  # Transaction costs
]

# All capital uses [NEGATIVE AMOUNTS]
ALL_CAPITAL_USE_SUBCATEGORIES = (
    ACQUISITION_CAPITAL_SUBCATEGORIES + 
    CONSTRUCTION_CAPITAL_SUBCATEGORIES + 
    DISPOSITION_CAPITAL_SUBCATEGORIES +
    [CapitalSubcategoryEnum.OTHER]
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
ALL_EXPENSE_SUBCATEGORIES = OPERATING_EXPENSE_SUBCATEGORIES + CAPITAL_EXPENSE_SUBCATEGORIES

# === FINANCING FEE SUBCATEGORY GROUPINGS ===

# Financing fees [NEGATIVE AMOUNTS]
FINANCING_FEE_SUBCATEGORIES = [
    FinancingSubcategoryEnum.ORIGINATION_FEE,     # Origination fees
    FinancingSubcategoryEnum.EXIT_FEE,            # Exit fees
    FinancingSubcategoryEnum.PREPAYMENT_PENALTY,  # Prepayment penalties
]

# === VALUATION SUBCATEGORY GROUPINGS ===

# Valuation methods [ZERO CASH FLOW]
ALL_VALUATION_SUBCATEGORIES = [
    ValuationSubcategoryEnum.ASSET_VALUATION,     # Asset appraisals
    ValuationSubcategoryEnum.COMPARABLE_SALES,    # Comparable sales
    ValuationSubcategoryEnum.DCF_VALUATION,       # DCF valuations
    ValuationSubcategoryEnum.DIRECT_CAP_VALUATION,  # Direct cap method
    ValuationSubcategoryEnum.COST_APPROACH,       # Cost approach
    ValuationSubcategoryEnum.BROKER_OPINION,      # Broker opinions
]


################################################################################
# LEDGER QUERIES
################################################################################


class LedgerQueries:  # noqa: PLR0904 (ignore too many public methods)
    """
    Simple query methods that replace complex aggregation logic.

    Each method performs clean pandas operations on the ledger DataFrame
    to extract standard real estate financial metrics. The flow_purpose
    column provides the primary filtering mechanism.

    Args:
        ledger: DataFrame with transaction records following the standard schema
    """

    def __init__(self, ledger_df: pd.DataFrame):
        """Initialize with ledger DataFrame."""
        # Validate schema first (basic check)
        required_cols = ["date", "amount", "flow_purpose", "category", "subcategory"]
        missing = [col for col in required_cols if col not in ledger_df.columns]
        if missing:
            raise ValueError(f"Ledger missing required columns: {missing}")
            
        # Convert date column to Period for consistent indexing
        # This solves the index mismatch problem at the source!
        ledger_df = ledger_df.copy()
        ledger_df["date"] = pd.PeriodIndex(ledger_df["date"], freq='M')
        
        # Store ledger with Period dates
        self.ledger = ledger_df

    def _create_unified_index(self, *series: pd.Series) -> pd.PeriodIndex:
        """
        Efficiently create a unified index from multiple series.
        
        All series should already have PeriodIndex since the ledger date column
        is converted to Period in __init__.
        
        Args:
            *series: Variable number of pandas Series with PeriodIndex
            
        Returns:
            Unified, sorted PeriodIndex from all non-empty series
        """
        non_empty_series = [s for s in series if not s.empty]
        
        if not non_empty_series:
            return pd.PeriodIndex([], freq='M')
        
        # Start with first series index
        unified_index = non_empty_series[0].index
        
        # Union with remaining series (sort=False for performance)
        for s in non_empty_series[1:]:
            unified_index = unified_index.union(s.index, sort=False)
        
        # Sort once at the end
        return unified_index.sort_values()

    # === Core Operating Metrics ===

    def pgr(self) -> pd.Series:
        """
        Potential Gross Revenue = All revenue at 100% occupancy.

        Industry standard PGR includes all revenue sources:
        - Base rent (Lease)
        - Miscellaneous income (parking, laundry, etc.)
        - Expense recoveries (Recovery)

        Returns:
            Time series of potential gross revenue by period
        """
        revenue = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (self.ledger["category"] == CashFlowCategoryEnum.REVENUE)
            & (self.ledger["subcategory"].isin(GROSS_REVENUE_SUBCATEGORIES))
        ]
        if revenue.empty:
            return pd.Series(dtype=float, name="Potential Gross Revenue")
        return revenue.groupby("date")["amount"].sum()

    def gpr(self) -> pd.Series:
        """
        Gross Potential Rent = Base rent only at 100% physical occupancy.

        Industry standard GPR includes only base rent and scheduled escalations,
        excluding recoveries and other income sources.

        Returns:
            Time series of gross potential rent by period
        """
        lease_revenue = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (self.ledger["category"] == CashFlowCategoryEnum.REVENUE)
            & (self.ledger["subcategory"] == RevenueSubcategoryEnum.LEASE)
        ]
        if lease_revenue.empty:
            return pd.Series(dtype=float, name="Gross Potential Rent")
        return lease_revenue.groupby("date")["amount"].sum()

    def tenant_revenue(self) -> pd.Series:
        """
        Tenant Revenue = Rent + Recoveries (excludes non-tenant income).

        Industry standard tenant revenue includes all revenue streams that
        originate from tenant obligations: base rent and expense recoveries.
        Excludes miscellaneous income like parking, antenna revenue, etc.

        Returns:
            Time series of tenant revenue by period
        """
        tenant_revenue = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (self.ledger["category"] == CashFlowCategoryEnum.REVENUE)
            & (self.ledger["subcategory"].isin(TENANT_REVENUE_SUBCATEGORIES))
        ]
        if tenant_revenue.empty:
            return pd.Series(dtype=float, name="Tenant Revenue")
        return tenant_revenue.groupby("date")["amount"].sum()

    def vacancy_loss(self) -> pd.Series:
        """
        Vacancy losses from the ledger.

        Returns:
            Time series of vacancy losses (absolute values) by period
        """
        vacancy = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (self.ledger["subcategory"] == RevenueSubcategoryEnum.VACANCY_LOSS)
        ]
        if vacancy.empty:
            return pd.Series(dtype=float, name="Vacancy Loss")
        return -vacancy.groupby("date")["amount"].sum()  # Return positive loss amounts (vacancy is stored as negative revenue)

    def egi(self) -> pd.Series:
        """
        Effective Gross Income per industry standards.

        EGI = Lease Revenue + Miscellaneous + Recovery
              - Vacancy Loss - Credit Loss - Abatement

        Returns:
            Time series of effective gross income by period
        """
        egi_components = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (self.ledger["category"] == CashFlowCategoryEnum.REVENUE)
            & (self.ledger["subcategory"].isin(ALL_REVENUE_SUBCATEGORIES))
        ]
        if egi_components.empty:
            return pd.Series(dtype=float, name="Effective Gross Income")
        return egi_components.groupby("date")["amount"].sum()

    def opex(self) -> pd.Series:
        """
        Total operating expenses.

        Returns:
            Time series of operating expenses (absolute values) by period
        """
        expenses = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (self.ledger["category"] == CashFlowCategoryEnum.EXPENSE)
            & (self.ledger["subcategory"] == ExpenseSubcategoryEnum.OPEX)
        ]
        if expenses.empty:
            return pd.Series(dtype=float, name="Operating Expenses")
        return -expenses.groupby("date")["amount"].sum()  # Convert negative to positive for display

    def noi(self) -> pd.Series:
        """
        Net Operating Income = Operating revenues - expenses.

        Returns:
            Time series of net operating income by period
        """
        operating_flows = self.ledger[
            self.ledger["flow_purpose"] == TransactionPurpose.OPERATING
        ]
        if operating_flows.empty:
            return pd.Series(dtype=float, name="Net Operating Income")
        # Sum all operating flows: +Revenue -Expense (expenses stored as negative)
        return operating_flows.groupby("date")["amount"].sum()

    def capex(self) -> pd.Series:
        """
        Capital expenditures.

        Includes Capital category items but excludes TI and LC which are tracked separately.

        Returns:
            Time series of capital expenditures (absolute values) by period
        """
        # Get all capital transactions
        capital_txns = self.ledger[
            (self.ledger["category"] == CashFlowCategoryEnum.CAPITAL)
            | (
                (self.ledger["category"] == CashFlowCategoryEnum.EXPENSE)
                & (self.ledger["subcategory"] == ExpenseSubcategoryEnum.CAPEX)
            )
        ]

        # Exclude TI and LC (they have their own methods) - use same patterns as ti() and lc()
        # Also exclude acquisition/disposition subcategories from operational CapEx
        capex = capital_txns[
            ~capital_txns["item_name"].str.contains(
                r"^TI\b|Tenant Improvement|^LC\b|Leasing Commission",
                case=False,
                na=False,
                regex=True,
            ) &
            ~capital_txns["subcategory"].isin([
                "Purchase Price", "Closing Costs", "Transaction Costs",
                "Other"  # Often used for disposition proceeds
            ])
        ]

        if capex.empty:
            return pd.Series(dtype=float, name="Capital Expenditures")
        return -capex.groupby("date")["amount"].sum()  # Convert negative to positive for display

    def ti(self) -> pd.Series:
        """
        Tenant improvements.

        Identifies TI transactions by item_name pattern matching.

        Returns:
            Time series of tenant improvements (absolute values) by period
        """
        # More precise pattern matching for TI - must start with TI or contain "Tenant Improvement"
        ti = self.ledger[
            self.ledger["item_name"].str.contains(
                r"^TI\b|Tenant Improvement", case=False, na=False, regex=True
            )
        ]
        if ti.empty:
            return pd.Series(dtype=float, name="Tenant Improvements")
        return -ti.groupby("date")["amount"].sum()  # Convert negative to positive for display

    def lc(self) -> pd.Series:
        """
        Leasing commissions.

        Identifies LC transactions by item_name pattern matching.

        Returns:
            Time series of leasing commissions (absolute values) by period
        """
        # More precise pattern matching for LC - must start with LC or contain "Leasing Commission"
        lc = self.ledger[
            self.ledger["item_name"].str.contains(
                r"^LC\b|Leasing Commission", case=False, na=False, regex=True
            )
        ]
        if lc.empty:
            return pd.Series(dtype=float, name="Leasing Commissions")
        return -lc.groupby("date")["amount"].sum()  # Convert negative to positive for display

    def ucf(self) -> pd.Series:
        """
        Unlevered Cash Flow = NOI - CapEx - TI - LC.
        
        Legacy method maintained for backward compatibility.
        For new code, prefer operational_cash_flow() which has the same
        calculation but enhanced implementation.

        Returns:
            Time series of unlevered cash flow by period
        """
        # This is equivalent to operational_cash_flow() - just return that
        result = self.operational_cash_flow()
        result.name = "Unlevered Cash Flow"  # Keep original naming
        return result

    # === Capital Metrics ===

    def total_uses(self) -> pd.Series:
        """
        Total capital uses by period.

        Only includes actual capital expenditures (CAPITAL_USE).
        Excludes financing activities like debt service, distributions, 
        and refinancing which are classified as FINANCING_SERVICE.

        Returns:
            Time series of total capital uses (absolute values) by period
        """
        uses = self.ledger[
            self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_USE
        ]
        if uses.empty:
            return pd.Series(dtype=float, name="Total Uses")
        return -uses.groupby("date")["amount"].sum()  # Convert negative to positive for display

    def total_sources(self) -> pd.Series:
        """
        Total capital sources by period.

        Returns:
            Time series of total sources by period
        """
        sources = self.ledger[
            self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE
        ]
        if sources.empty:
            return pd.Series(dtype=float, name="Total Sources")
        return sources.groupby("date")["amount"].sum()

    def uses_breakdown(self) -> pd.DataFrame:
        """
        Detailed uses by subcategory.

        Returns:
            DataFrame with uses broken down by subcategory and period
        """
        uses = self.ledger[
            self.ledger["flow_purpose"].isin([
                TransactionPurpose.CAPITAL_USE,
                TransactionPurpose.FINANCING_SERVICE,
            ])
        ]
        if uses.empty:
            return pd.DataFrame()

        breakdown = uses.pivot_table(
            index="date",
            columns="subcategory",
            values="amount",
            aggfunc="sum",
            fill_value=0,
            observed=False,  # Suppress future warning
        )
        return -breakdown  # Convert negative uses to positive for display

    def sources_breakdown(self) -> pd.DataFrame:
        """
        Detailed sources by subcategory.

        Returns:
            DataFrame with sources broken down by subcategory and period
        """
        sources = self.ledger[
            self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE
        ]
        if sources.empty:
            return pd.DataFrame()

        return sources.pivot_table(
            index="date",
            columns="subcategory",
            values="amount",
            aggfunc="sum",
            fill_value=0,
            observed=False,  # Suppress future warning
        )

    # === Debt Metrics ===

    def debt_draws(self) -> pd.Series:
        """
        Debt funding from all sources by period.
        
        Includes all forms of debt funding using comprehensive subcategory
        matching to capture initial loan proceeds and refinancing proceeds.
        
        Includes:
        - LOAN_PROCEEDS: Initial loan funding at origination
        - REFINANCING_PROCEEDS: New loan funding in refinancing transactions
        
        Returns:
            Time series of debt draws by period
            
        Note:
            Uses DEBT_FUNDING_SUBCATEGORIES constant for comprehensive coverage.
        """
        debt = self.ledger[
            (self.ledger["subcategory"].isin(DEBT_FUNDING_SUBCATEGORIES))
            & (self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE)
        ]
        if debt.empty:
            return pd.Series(dtype=float, name="Debt Draws")
        return debt.groupby("date")["amount"].sum()

    def debt_service(self) -> pd.Series:
        """
        Debt service payments from all debt facilities.
        
        Aggregates interest and principal payments using the disaggregated
        approach implemented across all facility types.
        
        Returns:
            Time series of debt service payments (absolute values) by period
        """
        service = self.ledger[
            (self.ledger["subcategory"].isin(DEBT_SERVICE_SUBCATEGORIES))
            & (self.ledger["flow_purpose"] == TransactionPurpose.FINANCING_SERVICE)
        ]
        if service.empty:
            return pd.Series(dtype=float, name="Debt Service")
        return -service.groupby("date")["amount"].sum()  # Convert negative to positive for display

    def equity_contributions(self) -> pd.Series:
        """
        Equity contributions by period.

        Returns:
            Time series of equity contributions by period
        """
        equity = self.ledger[
            (self.ledger["subcategory"] == FinancingSubcategoryEnum.EQUITY_CONTRIBUTION)
            & (self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE)
        ]
        if equity.empty:
            return pd.Series(dtype=float, name="Equity Contributions")
        return equity.groupby("date")["amount"].sum()

    # === Partner Metrics ===

    def partner_flows(self, partner_id: UUID) -> pd.Series:
        """
        All flows for a specific partner.

        Args:
            partner_id: UUID of the partner entity

        Returns:
            Time series of all flows for the specified partner
        """
        partner_txns = self.ledger[self.ledger["entity_id"] == partner_id]
        if partner_txns.empty:
            return pd.Series(dtype=float, name=f"Partner {partner_id} Flows")
        return partner_txns.groupby("date")["amount"].sum()

    def gp_distributions(self) -> pd.Series:
        """
        Total GP distributions.

        Returns:
            Time series of GP distributions by period
        """
        gp_txns = self.ledger[
            (self.ledger["entity_type"] == "GP")
            & (self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE)
        ]
        if gp_txns.empty:
            return pd.Series(dtype=float, name="GP Distributions")
        return gp_txns.groupby("date")["amount"].sum()

    def lp_distributions(self) -> pd.Series:
        """
        Total LP distributions.

        Returns:
            Time series of LP distributions by period
        """
        lp_txns = self.ledger[
            (self.ledger["entity_type"] == "LP")
            & (self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE)
        ]
        if lp_txns.empty:
            return pd.Series(dtype=float, name="LP Distributions")
        return lp_txns.groupby("date")["amount"].sum()

    def rental_abatement(self) -> pd.Series:
        """
        Rental abatement/concessions from the ledger.

        Returns:
            Time series of rental abatement amounts by period
        """
        abatement_txns = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (self.ledger["subcategory"] == RevenueSubcategoryEnum.ABATEMENT)
        ]
        if abatement_txns.empty:
            return pd.Series(dtype=float, name="Rental Abatement")
        return -abatement_txns.groupby("date")["amount"].sum()  # Return positive abatement amounts (stored as negative revenue)

    def credit_loss(self) -> pd.Series:
        """
        Credit losses from the ledger.

        Returns:
            Time series of credit loss amounts by period
        """
        credit_txns = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (self.ledger["subcategory"] == RevenueSubcategoryEnum.CREDIT_LOSS)
        ]
        if credit_txns.empty:
            return pd.Series(dtype=float, name="Credit Loss")
        return -credit_txns.groupby("date")["amount"].sum()  # Return positive loss amounts (stored as negative revenue)

    def misc_income(self) -> pd.Series:
        """
        Miscellaneous income from the ledger.

        Returns:
            Time series of miscellaneous income amounts by period
        """
        misc_txns = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (
                self.ledger["subcategory"] == RevenueSubcategoryEnum.MISC
            )  # Fixed: use correct enum value
        ]
        if misc_txns.empty:
            return pd.Series(dtype=float, name="Miscellaneous Income")
        return misc_txns.groupby("date")["amount"].sum()

    def expense_reimbursements(self) -> pd.Series:
        """
        Expense reimbursements/recoveries from the ledger.

        Returns:
            Time series of expense reimbursement amounts by period
        """
        reimburse_txns = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.OPERATING)
            & (
                self.ledger["subcategory"] == RevenueSubcategoryEnum.RECOVERY
            )  # Updated to match RevenueSubcategoryEnum.RECOVERY
        ]
        if reimburse_txns.empty:
            return pd.Series(dtype=float, name="Expense Reimbursements")
        return reimburse_txns.groupby("date")["amount"].sum()

    # === Asset Valuation Queries ===

    def asset_value(self) -> float:
        """
        Get asset value from explicit valuation transactions only.

        Phase 1: Requires explicit AssetValuation transaction in ledger
        Phase 2: May support calculated fallbacks from cap rates

        Returns:
            Most recent asset valuation amount

        Raises:
            ValueError: If no asset valuation found in ledger

        Example:
            queries = LedgerQueries(ledger_df)
            current_value = queries.asset_value()  # e.g., 12_000_000.0
        """
        valuation_txns = self.ledger[
            (self.ledger["category"] == CashFlowCategoryEnum.VALUATION)
            & (self.ledger["subcategory"] == ValuationSubcategoryEnum.ASSET_VALUATION)
        ]

        if valuation_txns.empty:
            raise ValueError(
                "No asset valuation found in ledger. "
                "Asset value must be explicitly set via an AssetValuation transaction. "
                "Use AssetValuation.from_cap_rate() or AssetValuation.add_to_ledger() "
                "to provide explicit asset valuations."
            )

        # Return most recent valuation
        return valuation_txns.sort_values("date")["amount"].iloc[-1]

    # === Financing Queries ===

    def financing_flows(
        self, subcategory: str, start_date: pd.Period = None, end_date: pd.Period = None
    ) -> pd.Series:
        """
        Get financing flows by subcategory within date range.

        Args:
            subcategory: Financing subcategory (e.g., 'Loan Proceeds', 'Debt Service')
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Time series of financing flows matching criteria

        Example:
            queries = LedgerQueries(ledger_df)
            loan_proceeds = queries.financing_flows('Loan Proceeds')
            debt_service = queries.financing_flows('Debt Service')
        """
        # Filter for financing category and specific subcategory
        # Handle both enum objects and string values for category
        financing_txns = self.ledger[
            (self.ledger["category"].astype(str).str.contains("FINANCING"))
            & (self.ledger["subcategory"].astype(str).str.contains(subcategory))
        ]

        # Apply date filters if provided
        if start_date is not None:
            financing_txns = financing_txns[financing_txns["date"] >= start_date]
        if end_date is not None:
            financing_txns = financing_txns[financing_txns["date"] <= end_date]

        if financing_txns.empty:
            return pd.Series(dtype=float, name=f"{subcategory} Flows")

        return financing_txns.groupby("date")["amount"].sum()

    # === Capital Flow Queries ===

    def capital_uses_by_category(self, as_of_date: pd.Period = None) -> pd.Series:
        """
        Get capital uses broken down by subcategory.

        Raw data extraction for use by reporting modules.

        Args:
            as_of_date: Optional date filter

        Returns:
            Series with subcategory as index and absolute amounts as values
        """
        ledger_to_use = self.ledger.copy()

        if as_of_date is not None:
            ledger_to_use = ledger_to_use[ledger_to_use["date"] <= as_of_date]

        uses = ledger_to_use[
            ledger_to_use["flow_purpose"] == TransactionPurpose.CAPITAL_USE
        ]
        if uses.empty:
            return pd.Series(dtype=float, name="Capital Uses")

        return uses.groupby("subcategory")["amount"].sum().abs()

    def capital_sources_by_category(self, as_of_date: pd.Period = None) -> pd.Series:
        """
        Get capital sources broken down by subcategory.

        Raw data extraction for use by reporting modules.

        Args:
            as_of_date: Optional date filter

        Returns:
            Series with subcategory as index and amounts as values
        """
        ledger_to_use = self.ledger.copy()

        if as_of_date is not None:
            ledger_to_use = ledger_to_use[ledger_to_use["date"] <= as_of_date]

        sources = ledger_to_use[
            ledger_to_use["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE
        ]
        if sources.empty:
            return pd.Series(dtype=float, name="Capital Sources")

        return sources.groupby("subcategory")["amount"].sum()

    # === Enhanced Cash Flow Queries for DealResults Architecture ===

    def operational_cash_flow(self) -> pd.Series:
        """
        Pure operational cash flow: NOI - CapEx - TI - LC.
        
        This represents the ongoing cash generation of the asset from 
        operations only, excluding all capital events (acquisition, 
        construction, disposition).
        
        Industry standard formula:
        OCF = Net Operating Income - Capital Expenditures 
              - Tenant Improvements - Leasing Commissions
        
        Returns:
            Time series of operational cash flows by period
            
        Note:
            This is equivalent to the existing ucf() method but with
            enhanced vectorized implementation for performance.
        """
        # Get component series using existing optimized methods
        noi_series = self.noi()
        capex_series = self.capex() 
        ti_series = self.ti()
        lc_series = self.lc()
        
        # Use helper method for efficient index unification
        unified_index = self._create_unified_index(noi_series, capex_series, ti_series, lc_series)
        
        if len(unified_index) == 0:
            return pd.Series(dtype=float, name="Operational Cash Flow")
        
        # Vectorized calculation with proper reindexing
        noi_aligned = noi_series.reindex(unified_index, fill_value=0.0)
        capex_aligned = capex_series.reindex(unified_index, fill_value=0.0)
        ti_aligned = ti_series.reindex(unified_index, fill_value=0.0) 
        lc_aligned = lc_series.reindex(unified_index, fill_value=0.0)
        
        # Calculate operational cash flow
        ocf = noi_aligned - capex_aligned - ti_aligned - lc_aligned
        ocf.name = "Operational Cash Flow"
        
        # Already Period index from _create_unified_index
        return ocf.sort_index()

    def project_cash_flow(self) -> pd.Series:
        """
        Complete project-level cash flow including all capital events.
        
        This is the universal formula that works for any deal type:
        - Operational cash flows (NOI - CapEx - TI - LC)
        - Acquisition costs (negative outflow)
        - Construction/renovation costs (negative outflow) 
        - Disposition proceeds (positive inflow)
        
        Industry standard formula:
        PCF = Operational Cash Flow + Capital Sources - Capital Uses
        
        Returns:
            Time series of complete project cash flows by period
            
        Example:
            For stabilized deals: Includes acquisition cost in Period 1
            For development deals: Includes construction costs throughout
            For all deals: Includes disposition proceeds at exit
        """
        # Start with operational cash flows
        operational_cf = self.operational_cash_flow()
        
        # Get all capital transactions  
        capital_transactions = self.ledger[
            self.ledger["flow_purpose"].isin([
                TransactionPurpose.CAPITAL_USE,      # Acquisition, construction, etc. (negative)
                TransactionPurpose.CAPITAL_SOURCE    # Disposition proceeds (positive)
            ])
        ]
        
        if capital_transactions.empty:
            # No capital events - return just operational flows
            return operational_cf
            
        # Aggregate capital flows by date
        capital_flows = capital_transactions.groupby("date")["amount"].sum()
        
        # Create unified timeline using helper method
        if operational_cf.empty:
            if capital_flows.empty:
                return pd.Series(dtype=float, name="Project Cash Flow")
            else:
                unified_index = capital_flows.index
                operational_aligned = pd.Series(0.0, index=unified_index)
                capital_aligned = capital_flows
        elif capital_flows.empty:
            return operational_cf
        else:
            # Use helper method for efficient unification
            unified_index = self._create_unified_index(operational_cf, capital_flows)
            operational_aligned = operational_cf.reindex(unified_index, fill_value=0.0)
            capital_aligned = capital_flows.reindex(unified_index, fill_value=0.0)
        
        # Combine operational and capital flows
        project_cf = operational_aligned + capital_aligned
        project_cf.name = "Project Cash Flow"
        
        # Already Period index from operations above
        return project_cf.sort_index()

    def equity_partner_flows(self) -> pd.Series:
        """
        All cash flows to/from equity partners.
        
        Captures comprehensive equity partner cash flows using standardized
        subcategory groupings to prevent blind spots.
        
        Includes:
        - EQUITY_CONTRIBUTION: Partner capital contributions (positive inflow)
        - EQUITY_DISTRIBUTION: Distributions to equity partners (negative outflow)  
        - PREFERRED_RETURN: Preferred return payments (negative outflow)
        - PROMOTE: Carried interest/promote payments (negative outflow)
        
        Sign convention (from deal perspective):
        - Contributions are positive (cash into deal)
        - Distributions are negative (cash out of deal)
        
        Returns:
            Time series of equity partner cash flows by period
            
        Note:
            Uses EQUITY_PARTNER_SUBCATEGORIES constant for comprehensive coverage.
            For IRR calculations, flip the sign to get partner perspective:
            partner_cf = -1 * equity_partner_flows()
        """        
        # Filter for equity partner transactions by subcategory
        equity_flows = self.ledger[
            (self.ledger["category"] == CashFlowCategoryEnum.FINANCING) &
            (self.ledger["subcategory"].isin(EQUITY_PARTNER_SUBCATEGORIES))
        ]
        
        # Also capture partner-specific flows if entity_type indicates GP/LP
        partner_flows = self.ledger[
            (self.ledger["entity_type"].isin(["GP", "LP"])) &
            (self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE)
        ]
        
        # Combine equity subcategory flows and partner-specific flows
        all_equity_flows = pd.concat([equity_flows, partner_flows]).drop_duplicates()
        
        if all_equity_flows.empty:
            return pd.Series(dtype=float, name="Equity Partner Flows")
        
        # Aggregate by date
        return all_equity_flows.groupby("date")["amount"].sum().sort_index()

    def debt_balance(self) -> pd.Series:
        """
        Outstanding debt balance over time.
        
        Tracks the cumulative outstanding balance of all debt facilities across
        different facility types and subcategory patterns:
        
        Balance increases from:
        - LOAN_PROCEEDS: Initial loan funding  
        - REFINANCING_PROCEEDS: New loan funding in refinancing
        
        Balance decreases from:
        - PRINCIPAL_PAYMENT: Principal portion of all debt facilities
        - PREPAYMENT: Full loan payoffs at disposition
        - REFINANCING_PAYOFF: Old loan payoffs in refinancing
        
        Formula:
        Balance[t] = Balance[t-1] + Funding[t] - Principal Payments[t] - Payoffs[t]
        
        Returns:
            Time series of outstanding debt balance by period
            
        Note:
            Uses helper constants to prevent blind spots across different 
            facility subcategory patterns. All facilities use disaggregated
            INTEREST_PAYMENT and PRINCIPAL_PAYMENT for accurate balance tracking.
        """
        # Get transactions that increase debt balance
        debt_increases = self.ledger[
            (self.ledger["subcategory"].isin(DEBT_INCREASE_SUBCATEGORIES)) &
            (self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE)
        ]
        
        # Get transactions that decrease debt balance  
        # Post-architectural fix: All facilities use disaggregated I&P approach
        # 1. Principal payments (exact balance reduction)
        principal_payments = self.ledger[
            (self.ledger["subcategory"] == FinancingSubcategoryEnum.PRINCIPAL_PAYMENT) &
            (self.ledger["flow_purpose"] == TransactionPurpose.FINANCING_SERVICE)
        ]
        
        # 2. Full loan payoffs
        debt_payoffs = self.ledger[
            (self.ledger["subcategory"].isin(DEBT_PAYOFF_SUBCATEGORIES)) &
            (self.ledger["flow_purpose"] == TransactionPurpose.FINANCING_SERVICE)
        ]
        
        # DEBT_SERVICE fully deprecated - all facilities now use disaggregated I&P approach
        
        # Start with balance increases (positive impact)
        balance_impacts = []
        
        if not debt_increases.empty:
            increases_df = debt_increases.copy()
            increases_df["balance_impact"] = increases_df["amount"]  # Positive for increases
            balance_impacts.append(increases_df)
        
        # Add balance decreases (negative impact) 
        if not principal_payments.empty:
            principal_df = principal_payments.copy()  
            principal_df["balance_impact"] = principal_df["amount"]  # Already negative, reduces balance
            balance_impacts.append(principal_df)
            
        if not debt_payoffs.empty:
            payoffs_df = debt_payoffs.copy()
            payoffs_df["balance_impact"] = payoffs_df["amount"]  # Already negative, reduces balance
            balance_impacts.append(payoffs_df)
            
        # All debt service now uses disaggregated principal payments - no legacy handling needed
        
        # Combine all balance-affecting transactions
        if not balance_impacts:
            return pd.Series(dtype=float, name="Debt Balance")
        
        all_balance_changes = pd.concat(balance_impacts, ignore_index=True)
        
        # Aggregate by date and calculate cumulative balance
        daily_changes = all_balance_changes.groupby("date")["balance_impact"].sum()
        cumulative_balance = daily_changes.cumsum()
        cumulative_balance.name = "Debt Balance"
        
        return cumulative_balance.sort_index()

    def construction_draws(self) -> pd.Series:
        """
        Construction draw schedule for development deals.
        
        Identifies construction-related capital expenditures by subcategory
        and item patterns. Returns zero series for non-development deals.
        
        Includes:
        - Hard costs (direct construction)
        - Soft costs (architectural, engineering, permits, etc.)
        - Construction loan draws
        
        Returns:
            Time series of construction draws by period (absolute values)
            
        Example:
            Development deals: Shows monthly construction expenditures
            Stabilized deals: Returns all zeros
        """
        # Define construction-related subcategories and patterns
        construction_subcategories = [
            # Direct subcategory matches (if they exist in enum)
            "Hard Costs",
            "Soft Costs", 
            "Construction",
        ]
        
        # Get capital use transactions that match construction patterns
        construction_flows = self.ledger[
            (self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_USE) &
            (
                # Match by subcategory
                (self.ledger["subcategory"].astype(str).str.contains("|".join(construction_subcategories), case=False, na=False)) |
                # Match by item name patterns
                (self.ledger["item_name"].str.contains(
                    r"Construction|Building|Hard Cost|Soft Cost|GC Payment", 
                    case=False, na=False, regex=True
                ))
            )
        ]
        
        if construction_flows.empty:
            return pd.Series(dtype=float, name="Construction Draws")
        
        # Return absolute values (construction costs stored as negative)
        draws_series = -construction_flows.groupby("date")["amount"].sum()
        draws_series.name = "Construction Draws"
        
        return draws_series.sort_index()

    def cumulative_construction_draws(self) -> pd.Series:
        """
        Cumulative construction spending over time.
        
        Running total of all construction draws from project start.
        Useful for tracking construction progress and budget utilization.
        
        Returns:
            Time series of cumulative construction spending by period
            
        Example:
            Month 1: $100,000
            Month 2: $250,000 (cumulative)  
            Month 3: $425,000 (cumulative)
        """
        construction_draws = self.construction_draws()
        
        if construction_draws.empty:
            return pd.Series(dtype=float, name="Construction To Date")
        
        cumulative = construction_draws.cumsum()
        cumulative.name = "Construction To Date"
        
        return cumulative

    def revenue(self) -> pd.Series:
        """
        Total revenue from all sources.
        
        Comprehensive revenue including:
        - Lease revenue (base rent)
        - Miscellaneous income  
        - Expense recoveries
        - Less: vacancy, credit losses, abatements
        
        Returns:
            Time series of total revenue by period
            
        Note:
            This is equivalent to egi() but with clearer naming for DealResults
        """
        return self.egi()  # Leverage existing optimized implementation

    # TODO: add a net cash flow (noi minus debt service) -- do we have this already?
