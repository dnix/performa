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
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
    FinancingSubcategoryEnum,
    RevenueSubcategoryEnum,
    TransactionPurpose,
    ValuationSubcategoryEnum,
)


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
        # Store ledger directly - we expect date as a column, not index
        self.ledger = ledger_df

        # Validate schema (basic check)
        required_cols = ["date", "amount", "flow_purpose", "category", "subcategory"]
        missing = [col for col in required_cols if col not in ledger_df.columns]
        if missing:
            raise ValueError(f"Ledger missing required columns: {missing}")

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
            & (
                self.ledger["subcategory"].isin([
                    RevenueSubcategoryEnum.LEASE,
                    RevenueSubcategoryEnum.MISC,
                    RevenueSubcategoryEnum.RECOVERY,
                ])
            )
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
            (self.ledger["flow_purpose"] == "Operating")
            & (self.ledger["category"] == "Revenue")
            & (self.ledger["subcategory"].isin(["Lease", "Recovery"]))
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
        return -vacancy.groupby("date")[
            "amount"
        ].sum()  # Return positive loss amounts (vacancy is stored as negative revenue)

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
            & (
                self.ledger["subcategory"].isin([
                    RevenueSubcategoryEnum.LEASE,  # Stored as positive (+)
                    RevenueSubcategoryEnum.MISC,  # Stored as positive (+)
                    RevenueSubcategoryEnum.RECOVERY,  # Stored as positive (+)
                    RevenueSubcategoryEnum.VACANCY_LOSS,  # Stored as negative (-)
                    RevenueSubcategoryEnum.CREDIT_LOSS,  # Stored as negative (-)
                    RevenueSubcategoryEnum.ABATEMENT,  # Stored as negative (-)
                ])
            )
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
        return -expenses.groupby("date")[
            "amount"
        ].sum()  # Convert negative to positive for display

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
        capex = capital_txns[
            ~capital_txns["item_name"].str.contains(
                r"^TI\b|Tenant Improvement|^LC\b|Leasing Commission",
                case=False,
                na=False,
                regex=True,
            )
        ]

        if capex.empty:
            return pd.Series(dtype=float, name="Capital Expenditures")
        return -capex.groupby("date")[
            "amount"
        ].sum()  # Convert negative to positive for display

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
        return -ti.groupby("date")[
            "amount"
        ].sum()  # Convert negative to positive for display

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
        return -lc.groupby("date")[
            "amount"
        ].sum()  # Convert negative to positive for display

    def ucf(self) -> pd.Series:
        """
        Unlevered Cash Flow = NOI - CapEx - TI - LC.

        Returns:
            Time series of unlevered cash flow by period
        """
        # Get all component series
        noi = self.noi()
        capex = self.capex()
        ti = self.ti()
        lc = self.lc()

        # Create a unified index from all series
        all_dates = set()
        for series in [noi, capex, ti, lc]:
            if not series.empty:
                all_dates.update(series.index)

        if not all_dates:
            return pd.Series(dtype=float, name="Unlevered Cash Flow")

        # Sort dates and create result series
        sorted_dates = sorted(all_dates)
        ucf_values = []

        for date in sorted_dates:
            noi_val = noi.get(date, 0)
            capex_val = capex.get(date, 0)
            ti_val = ti.get(date, 0)
            lc_val = lc.get(date, 0)
            ucf_val = noi_val - capex_val - ti_val - lc_val
            ucf_values.append(ucf_val)

        return pd.Series(ucf_values, index=sorted_dates, name="Unlevered Cash Flow")

    # === Capital Metrics ===

    def total_uses(self) -> pd.Series:
        """
        Total capital uses by period.

        Includes both Capital Use and Financing Service flows.

        Returns:
            Time series of total uses (absolute values) by period
        """
        uses = self.ledger[
            self.ledger["flow_purpose"].isin([
                TransactionPurpose.CAPITAL_USE,
                TransactionPurpose.FINANCING_SERVICE,
            ])
        ]
        if uses.empty:
            return pd.Series(dtype=float, name="Total Uses")
        return -uses.groupby("date")[
            "amount"
        ].sum()  # Convert negative to positive for display

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
        Debt funding by period.

        Returns:
            Time series of debt draws by period
        """
        debt = self.ledger[
            (self.ledger["subcategory"] == FinancingSubcategoryEnum.LOAN_PROCEEDS)
            & (self.ledger["flow_purpose"] == TransactionPurpose.CAPITAL_SOURCE)
        ]
        if debt.empty:
            return pd.Series(dtype=float, name="Debt Draws")
        return debt.groupby("date")["amount"].sum()

    def debt_service(self) -> pd.Series:
        """
        Debt service payments.

        Returns:
            Time series of debt service payments (absolute values) by period
        """
        service = self.ledger[
            (self.ledger["subcategory"] == FinancingSubcategoryEnum.DEBT_SERVICE)
            & (self.ledger["flow_purpose"] == TransactionPurpose.FINANCING_SERVICE)
        ]
        if service.empty:
            return pd.Series(dtype=float, name="Debt Service")
        return -service.groupby("date")[
            "amount"
        ].sum()  # Convert negative to positive for display

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
        return -abatement_txns.groupby("date")[
            "amount"
        ].sum()  # Return positive abatement amounts (stored as negative revenue)

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
        return -credit_txns.groupby("date")[
            "amount"
        ].sum()  # Return positive loss amounts (stored as negative revenue)

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
