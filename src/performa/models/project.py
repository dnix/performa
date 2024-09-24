from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from pydantic import field_validator, model_validator
from pyxirr import pmt  # , npv, xnpv, irr, xirr, mirr, fv

from ..utils.types import FloatBetween0And1, PositiveInt, PositiveIntGt1
from .budget import Budget
from .expense import Expense
from .financing import ConstructionFinancing, PermanentFinancing
from .model import Model
from .program import ProgramUseEnum
from .revenue import Revenue

# %%
###########################
######### PROJECT #########
###########################


class CapRates(Model):
    """Class for a generic cap rate model"""

    name: str  # "Residential Cap Rates"
    program_use: ProgramUseEnum  # program use for the cap rate model
    development_cap_rate: FloatBetween0And1  # cap rate at development
    refinance_cap_rate: FloatBetween0And1  # cap rate at refinance
    sale_cap_rate: FloatBetween0And1  # cap rate at sale


class Project(Model):
    """Class for a generic project"""

    # GENERAL INFO
    # name: str  # "La Tour Eiffel"
    debt_to_equity: FloatBetween0And1

    # TIMELINE
    project_start_date: pd.Period = pd.Period.now(freq="M")  # month zero of project

    # COSTS
    budget: Budget

    # CONSTRUCTION FINANCING
    construction_financing: ConstructionFinancing  # TODO: make optional (?)
    # financing_interest_rate: FloatBetween0And1
    # financing_fee_rate: FloatBetween0And1
    # financing_ltc: FloatBetween0And1
    # TODO: mezzanine rollover

    # REVENUES
    revenue: Revenue

    # EXPENSES
    expenses: Optional[Expense]  # opex and capex expenses, as applicable (rental only)
    # TODO: maybe not optional if incorporate post-sales expenses?

    # PERMANENT FINANCING
    permanent_financing: PermanentFinancing  # TODO: make optional (?)
    stabilization_year: PositiveInt  # year of stabilization for permanent financing  # TODO: replace this with lease-up logic!?

    # DISPOSITION
    # -> rental:
    cap_rates: list[CapRates] | float  # market cap rates FOR EACH PROGRAM USE
    hold_duration: Optional[
        PositiveIntGt1
    ]  # years to hold before disposition (required for rental revenues only)
    # -> sales and rental:
    cost_of_sale: FloatBetween0And1 = 0.03  # cost of sale as a percentage of sale price (broker fees, closing costs, etc.)

    # FIXME: validator to ensure a cap rate for each program use!

    # PROPERTIES  for important cash flows

    @property
    def _budget_table(self) -> pd.DataFrame:
        """
        Pivot table of budget costs over time.

        Returns:
            pd.DataFrame: A DataFrame with a multi-index of Category, Subcategory, and Name.
        
        """
        shifted = self.shift_ordinal_to_project_timeline(self.budget.budget_df)
        return shifted.pivot_table(
            values=0,
            index=shifted.index,
            columns=["Category", "Subcategory", "Name"],
            aggfunc="sum",
        ).fillna(0)

    @property
    def _revenue_table(self) -> pd.DataFrame:
        """
        Pivot table of revenue sources over time.

        Returns:
            pd.DataFrame: A DataFrame with a multi-index of Category, Subcategory, Use, and Name.

        Example:
                                                Revenue
        Category Subcategory Use    Name
        2023-01  Lease       Office Kodak       100000.0
                             Retail Blockbuster 50000.0
        2023-02  Lease       Office Kodak       102000.0
                             Retail Blockbuster 51000.0
        """
        shifted = self.shift_ordinal_to_project_timeline(self.revenue.revenue_df)
        return shifted.pivot_table(
            values=0,
            index=shifted.index,
            columns=["Category", "Subcategory", "Use", "Name"],
            aggfunc="sum",
        ).fillna(0)

    @property
    def _structural_losses_table(self) -> pd.DataFrame:
        shifted = self.shift_ordinal_to_project_timeline(
            self.revenue.structural_losses_df
        )
        return shifted.pivot_table(
            values=0,
            index=shifted.index,
            columns=["Category", "Subcategory", "Use", "Name"],
            aggfunc="sum",
        ).fillna(0)

    @property
    def _expense_table(self) -> pd.DataFrame:
        shifted = self.shift_ordinal_to_project_timeline(self.expenses.expense_df)
        return shifted.pivot_table(
            values=0,
            index=shifted.index,
            columns=["Category", "Subcategory", "Use", "Name"],
            aggfunc="sum",
        ).fillna(0)

    #####################
    # DEVELOPMENT FLOWS #
    #####################

    @property
    def construction_before_financing_cf(self) -> pd.DataFrame:
        """
        Pivot table of budget costs before financing.

        Returns:
            pd.DataFrame: A DataFrame with a multi-index of Category, Subcategory, and Name.

        Example:
                                        Hard Costs  Soft Costs
        Category Subcategory  Name
        2023-01  Construction Land      1000000.0   0.0
                              Building  0.0         50000.0
        2023-02  Construction Building  500000.0    0.0
                 Fees         Architect 0.0         25000.0
        """
        return self._budget_table

    @property
    def construction_financing_cf(self) -> pd.DataFrame:
        """
        Compute construction financing cash flow with debt and equity draws, fees, and interest reserve.

        Returns:
            pd.DataFrame: A DataFrame with columns for financing components.

        Example:
                 Total Costs  Cumulative  Equity     Debt    Financing  Interest
                 Before       Costs       Draw       Draw    Fees       Reserve
                 Financing
        2023-01  1050000.0    1050000.0   1050000.0  0.0     0.0        0.0
        2023-02  525000.0     1575000.0   0.0        525000.0 26250.0   2625.0
        """
        total_project_cost = self._budget_table.sum().sum()
        debt_portion = (
            total_project_cost * self.debt_to_equity
        )  # debt pre-interest reserve
        equity_portion = total_project_cost * (1 - self.debt_to_equity)

        # sum up budget costs to get total costs before financing
        df = (
            self._budget_table.sum(axis=1)
            .to_frame("Budget")
            .reindex(self.project_timeline, fill_value=0)
        )

        # rename 'Budget' column to 'Total Costs Before Financing'
        df.rename(columns={"Budget": "Total Costs Before Financing"}, inplace=True)

        # calculate cumulative costs to decide draws
        df["Cumulative Costs"] = df["Total Costs Before Financing"].cumsum()

        # equity and debt draw calculations
        df["Equity Draw"] = np.minimum(
            df["Total Costs Before Financing"],
            np.maximum(
                equity_portion - df["Cumulative Costs"].shift(1, fill_value=0), 0
            ),
        )

        # applying financing fee only once when crossing the threshold from equity to debt
        df["Financing Fees"] = np.where(
            (df["Cumulative Costs"].shift(1, fill_value=0) < equity_portion)
            & (df["Cumulative Costs"] >= equity_portion),
            debt_portion * self.construction_financing.fee_rate,
            0,
        )

        # debt draw calculations
        # NOTE: fees are included in the debt draw
        df["Debt Draw"] = (
            df["Total Costs Before Financing"]
            - df["Equity Draw"]
            + df["Financing Fees"]
        )

        # calculate cumulative debt and interest
        df["Cumulative Debt Drawn"] = df["Debt Draw"].cumsum()
        df["Interest Reserve"] = 0
        cumulative_interest = 0

        # update debt and interest calculation with recursion for accurate compounding
        for i in range(len(df)):
            if i > 0:
                previous_balance = (
                    df.loc[df.index[i - 1], "Cumulative Debt Drawn"]
                    + cumulative_interest
                )
                interest_for_this_month = previous_balance * (
                    self.construction_financing.interest_rate / 12
                )
                cumulative_interest += interest_for_this_month
            else:
                interest_for_this_month = 0

            df.at[df.index[i], "Interest Reserve"] = interest_for_this_month
            df.at[df.index[i], "Cumulative Debt Drawn"] += interest_for_this_month

        return df

    @property
    def equity_cf(self) -> pd.DataFrame:
        """
        Compute equity cash flow.

        Returns:
            pd.DataFrame: A DataFrame with a single column 'Equity'.

        Example:
                 Equity
        2023-01  1050000.0
        2023-02  0.0
        """
        return self.construction_financing_cf["Equity Draw"].to_frame("Equity")

    ##################
    # RENTAL REVENUE #
    ##################

    @property
    def total_potential_income_cf(self) -> pd.DataFrame:
        """
        Construct cash flow for total potential income by program use.

        Returns:
            pd.DataFrame: A DataFrame with columns for each program use.

        Example:
                 Office    Retail
        2023-01  100000.0  50000.0
        2023-02  102000.0  51000.0
        """
        # TODO: rental only?
        return (
            self._revenue_table.loc[:, ("Revenue", "Lease", slice(None), slice(None))]
            .groupby(level=2, axis=1)
            .sum()
        )
        # to get all revenue per period, use sum(axis=1)

    @property
    def losses_cf(self) -> pd.DataFrame:
        """
        Construct cash flow for structural losses by program use.

        Returns:
            pd.DataFrame: A DataFrame with columns for each program use.

        Example:
                 Office   Retail
        2023-01  5000.0   2500.0
        2023-02  5100.0   2550.0
        """
        # rental only
        return (
            self._structural_losses_table.loc[
                :, ("Losses", "Lease", slice(None), slice(None))
            ]
            .groupby(level=2, axis=1)
            .sum()
        )

    @property
    def effective_gross_revenue_cf(self) -> pd.DataFrame:
        """
        Construct cash flow for effective gross revenue by program use.

        Returns:
            pd.DataFrame: A DataFrame with columns for each program use.

        Example:
                 Office    Retail
        2023-01  95000.0   47500.0
        2023-02  96900.0   48450.0
        """
        return self.total_potential_income_cf - self.losses_cf

    @property
    def opex_cf(self) -> pd.DataFrame:
        """
        Compute operating expenses cash flow.

        Returns:
            pd.DataFrame: A DataFrame with columns for each program use.

        Example:
                 Office   Retail
        2023-01  20000.0  10000.0
        2023-02  20400.0  10200.0
        """
        return (
            self._expense_table.loc[:, ("Expense", "OpEx", slice(None), slice(None))]
            .groupby(level=2, axis=1)
            .sum()
        )

    @property
    def net_operating_income_cf(self) -> pd.DataFrame:
        """
        Compute net operating income cash flow.

        Returns:
            pd.DataFrame: A DataFrame with columns for each program use.

        Example:
                 Office   Retail
        2023-01  75000.0  37500.0
        2023-02  76500.0  38250.0
        """
        return self.effective_gross_revenue_cf - self.opex_cf

    @property
    def capex_cf(self) -> pd.DataFrame:
        """
        Compute capital expenditure cash flow.

        Returns:
            pd.DataFrame: A DataFrame with columns for each program use.

        Example:
                 Office  Retail
        2023-01  5000.0  2500.0
        2023-02  5100.0  2550.0
        """
        return (
            self._expense_table.loc[:, ("Expense", "CapEx", slice(None), slice(None))]
            .groupby(level=2, axis=1)
            .sum()
        )

    @property
    def cash_flow_from_operations_cf(self) -> pd.DataFrame:
        """
        Compute cash flow from operations.

        Returns:
            pd.DataFrame: A DataFrame with columns for each program use.

        Example:
                 Office   Retail
        2023-01  70000.0  35000.0
        2023-02  71400.0  35700.0
        """
        return (
            (self.net_operating_income_cf - self.capex_cf)
            .reindex(self.project_timeline)
            .fillna(0)
        )

    @property
    def _cap_rates_table(self) -> pd.DataFrame:
        """
        Compute cap rates table.

        Returns:
            pd.DataFrame: A DataFrame with cap rates for each program use.

        Example:
                Development  Refinance  Sale
                Cap Rate     Cap Rate   Cap Rate
        Office  0.05         0.045      0.04
        Retail  0.06         0.055      0.05
        """
        df = pd.DataFrame(
            [
                {
                    "Use": cap_rate.program_use,
                    "Development Cap Rate": cap_rate.development_cap_rate,
                    "Refinance Cap Rate": cap_rate.refinance_cap_rate,
                    "Sale Cap Rate": cap_rate.sale_cap_rate,
                }
                for cap_rate in self.cap_rates
            ]
        )
        df.set_index("Use", inplace=True)  # lookups by program use
        return df

    @property
    def stabilization_date(self) -> pd.Period:
        """
        Compute the stabilization date.

        Returns:
            pd.Period: The stabilization date.

        Example:
            pd.Period('2026-01', freq='M')
        """
        # FIXME: this should use lease-up logic(?)
        # return self.project_start_date + self.stabilization_year * 12
        return (
            self._revenue_table.loc[
                :, ("Revenue", "Lease", slice(None), slice(None))
            ].index.min()
            + self.stabilization_year * 12
        )

    @property
    def refinance_value(self) -> float:
        """
        Compute the refinance value.

        Returns:
            float: The refinance value.

        Example:
            50000000.0
        """
        return (
            self.net_operating_income_cf.loc[
                self.stabilization_date : (self.stabilization_date + 11)
            ]
            / self._cap_rates_table["Refinance Cap Rate"]
        ).sum()
        # FIXME: check this math/shape

    @property
    def construction_loan_repayment_cf(self) -> pd.DataFrame:
        """
        Compute the construction loan repayment cash flow.

        Returns:
            pd.DataFrame: A DataFrame with a single column 'Construction Loan Repayment'.

        Example:
                             Construction Loan Repayment
        2026-01              20000000.0
        """
        # TODO: refactor this more cleanly
        repayment_flow = self.construction_financing_cf["Cumulative Debt Drawn"]
        repayment_at_stabilization = repayment_flow.loc[self.stabilization_date]
        return pd.DataFrame(
            {
                "Construction Loan Repayment": repayment_at_stabilization,
            },
            index=[self.stabilization_date],
        )

    @property
    def refinance_amount(self) -> float:
        """
        Compute the refinance amount.

        Returns:
            float: The refinance amount.

        Example:
            35000000.0
        """
        return self.refinance_value * self.permanent_financing.ltv_ratio

    @property
    def refinance_infusion_cf(self) -> pd.DataFrame:
        """
        Compute the refinance infusion cash flow.

        Returns:
            pd.DataFrame: A DataFrame with a single column 'Refinance Infusion'.

        Example:
                             Refinance Infusion
        2026-01              35000000.0
        """
        return pd.DataFrame(
            {
                "Refinance Infusion": (
                    self.refinance_value * self.permanent_financing.ltv_ratio
                )[0],
            },
            index=[self.stabilization_date],
        )

    @property
    def permanent_financing_cf(self) -> pd.DataFrame:
        """
        Compute the permanent financing cash flow.

        Returns:
            pd.DataFrame: A DataFrame with columns for payment components.

        Example:
                 Payment    Interest   Principal  End Balance
        2026-01  200000.0   145833.33  54166.67   34945833.33
        2026-02  200000.0   145607.64  54392.36   34891440.97
        """
        # amortize the loan
        # FIXME: add refinancing fees!
        df, _ = Project.amortize_loan(
            loan_amount=self.refinance_amount,
            term=self.permanent_financing.amortization,
            interest_rate=self.permanent_financing.interest_rate,
            start_date=self.stabilization_date,
        )
        return df

    @property
    def permanent_financing_repayment_cf(self) -> pd.DataFrame:
        """
        Compute the permanent financing repayment cash flow.

        Returns:
            pd.DataFrame: A DataFrame with a single column 'Permanent Financing Repayment'.

        Example:
                             Permanent Financing Repayment
        2036-01              30000000.0
        """
        repayment_flow = self.permanent_financing_cf["End Balance"]
        repayment_at_end = repayment_flow.loc[self.project_end_date]
        return pd.DataFrame(
            {
                "Permanent Financing Repayment": repayment_at_end,
            },
            index=[self.project_end_date],
        )

    @property
    def cash_flow_after_financing_cf(self) -> pd.DataFrame:
        """
        Compute cash flow after financing.

        Returns:
            pd.DataFrame: A DataFrame with a single column 'Cash Flow After Financing'.

        Example:
                 Cash Flow After Financing
        2026-01  105000.0
        2026-02  107100.0
        """
        # flatten noi by summing across program uses and subtract financing_cf payment column
        return (
            (
                self.cash_flow_from_operations_cf.sum(axis=1)
                - self.permanent_financing_cf["Payment"]
            )
            .to_frame("Cash Flow After Financing")
            .reindex(self.project_timeline)
            .fillna(0)
        )

    @property
    def dscr(self) -> pd.DataFrame:
        """
        Compute the debt service coverage ratio over time.

        Returns:
            pd.DataFrame: A DataFrame with DSCR for each program use.

        Example:
                 Office  Retail
        2026-01  1.5     1.2
        2026-02  1.53    1.22
        """
        return (
            self.net_operating_income_cf
            / self.permanent_financing_cf["Payment"].iloc[0]
        )

    @property
    def sale_value(self) -> float:
        """
        Compute the sale value.

        Returns:
            float: The sale value.

        Example:
            75000000.0
        """
        return (
            self.net_operating_income_cf.loc[
                self.project_end_date : (self.project_end_date + 11)
            ].sum()
            / self._cap_rates_table["Sale Cap Rate"]
        ).sum()
        # FIXME: check this math/shape with multiple program uses

    @property
    def disposition_cf(self) -> pd.DataFrame:
        """
        Compute the sale infusion cash flow.

        Returns:
            pd.DataFrame: A DataFrame with a single column 'Disposition'.

        Example:
                 Disposition
        2036-01  75000000.0
        """
        # create df with project timeline and assign sale value to the project end date
        df = pd.DataFrame(
            {
                "Disposition": self.sale_value,
            },
            index=[self.project_end_date],
        )
        return df.reindex(self.project_timeline).fillna(0)

    #################
    # SALES REVENUE #
    #################

    @property
    def total_sales_revenue_cf(self) -> pd.DataFrame:
        """
        Construct cash flow for total sales revenue by program use.

        Returns:
            pd.DataFrame: A DataFrame with columns for each program use.

        Example:
                 Condos    Retail
        2024-01  5000000.0 2000000.0
        2024-02  5100000.0 2040000.0
        """
        if not self.is_sales_project:
            return pd.Series(0, index=self.project_timeline)
        return (
            self._revenue_table.loc[:, ("Revenue", "Sale", slice(None), slice(None))]
            .groupby(level=2, axis=1)
            .sum()
            .reindex(self.project_timeline)
        )
        # to get all revenue per period, use sum(axis=1)

    @property
    def sale_proceeds_cf(self) -> pd.DataFrame:
        """
        Compute the sale proceeds cash flow.

        Returns:
            pd.DataFrame: A DataFrame with columns for sale proceeds and cost of sale.

        Example:
                 Sale Proceeds  Cost of Sale
        2036-01  75000000.0    -2250000.0
        """
        df = pd.DataFrame(index=self.project_timeline)
        df["Sale Proceeds"] = 0  # initialize
        df["Sale Proceeds"] += (
            self.total_sales_revenue_cf.sum(axis=1) if self.is_sales_project else 0
        )  # add sales revenue
        df["Sale Proceeds"] += (
            self.disposition_cf["Disposition"] if self.is_rental_project else 0
        )  # add rental disposition
        df["Cost of Sale"] = (
            df["Sale Proceeds"] * self.cost_of_sale * -1
        )  # add cost of sale/commissions
        return df

    ########################
    # AGGREGATE CASH FLOWS #
    ########################

    @property
    def unlevered_cash_flow(self) -> pd.DataFrame:
        """
        Compute unlevered cash flow.

        Returns:
            pd.DataFrame: A DataFrame with a single column 'Unlevered Cash Flow'.

        Example:
                 Unlevered Cash Flow
        2023-01  -1050000.0
        2023-02  -525000.0
        ...
        2036-01  72750000.0
        """
        # TODO: revisit performance of using concat
        return (
            pd.concat(
                [
                    self.construction_before_financing_cf.sum(axis=1)
                    * -1,  # start with construction costs
                    self.cash_flow_from_operations_cf.sum(
                        axis=1
                    ),  # add rental cash flow (or zero if not rental project)
                    self.sale_proceeds_cf.sum(
                        axis=1
                    ),  # add sales proceeds, accounting for commissions
                ],
                axis=1,
            )
            .sum(axis=1)
            .to_frame("Unlevered Cash Flow")
            .reindex(self.project_timeline)
            .fillna(0)
        )

    @property
    def levered_cash_flow(self) -> pd.DataFrame:
        """
        Compute levered cash flow.

        Returns:
            pd.DataFrame: A DataFrame with a single column 'Levered Cash Flow'.

        Example:
                 Levered Cash Flow
        2023-01  -1050000.0
        2023-02  0.0
        ...
        2036-01  42750000.0
        """
        # PERF: revisit performance of using concat
        return (
            pd.concat(
                [
                    self.equity_cf * -1,
                    self.construction_loan_repayment_cf * -1,
                    self.refinance_infusion_cf,
                    self.cash_flow_after_financing_cf,
                    self.sale_proceeds_cf,
                    self.permanent_financing_repayment_cf * -1,
                ],
                axis=1,
            )
            .sum(axis=1)
            .to_frame("Levered Cash Flow")
            .reindex(self.project_timeline)
            .fillna(0)
        )

    ##############
    # STATISTICS #
    ##############

    def summary_metrics(self, period: Optional[pd.Period] = None) -> dict:
        """Roll up summary metrics for the project"""
        # FIXME: implement

        # return dict of:
        # - levered cash flow
        # - unlevered cash flow
        # - irr
        # - npv
        # - dscr
        # - equity multiple
        # - development spreads (untrended, trended, reversion/sale)

    #####################
    # HELPERS/UTILITIES #
    #####################

    @property
    def project_timeline(self) -> pd.PeriodIndex:
        return pd.period_range(self.project_start_date, self.project_end_date, freq="M")

    @property
    def development_timeline(self) -> pd.PeriodIndex:
        """Compute the development timeline from the project start date to the end of development budget costs/draws"""
        return pd.period_range(
            self.project_start_date, self.development_end_date, freq="M"
        )

    @property
    def stabilization_timeline(self) -> pd.PeriodIndex:
        """Compute the stabilization timeline from the end of budget costs to the stabilization date"""
        return pd.period_range(
            self.development_end_date, self.stabilization_date, freq="M"
        )
        # FIXME: what about non-rental case? raise error?

    @property
    def hold_timeline(self) -> pd.PeriodIndex:
        return pd.period_range(self.stabilization_date, self.project_end_date, freq="M")

    @property
    def is_rental_project(self) -> bool:
        """Check if the project has rental revenues"""
        return any(
            "Lease" in column
            for column in self._revenue_table.columns.get_level_values(1)
        )

    @property
    def is_sales_project(self) -> bool:
        """Check if the project has sales revenues"""
        return any(
            "Sale" in column
            for column in self._revenue_table.columns.get_level_values(1)
        )

    @property
    def project_end_date(self) -> pd.Period:
        """Compute the project end date using min of active rental plus hold duration or max of sales revenues"""
        rental_end_date = (
            self._revenue_table.loc[
                :, ("Revenue", "Lease", slice(None), slice(None))
            ].index.min()
            + (self.hold_duration * 12)
            if self.is_rental_project
            else None
        )
        sales_end_date = (
            self._revenue_table.loc[
                :, ("Revenue", "Sale", slice(None), slice(None))
            ].index.max()
            if self.is_sales_project
            else None
        )
        return (
            max(rental_end_date, sales_end_date)
            if rental_end_date and sales_end_date
            else rental_end_date or sales_end_date
        )

    @property
    def development_end_date(self) -> pd.Period:
        """Compute the development end date using the end of budget costs/draws"""
        return self._budget_table.index.max()

    @field_validator("project_start_date", mode="before")
    def to_period(value) -> pd.Period:
        """Cast as a pandas period"""
        return pd.Period(value, freq="M")

    @staticmethod
    def convert_to_annual(df: pd.DataFrame) -> pd.DataFrame:
        """Convert a dataframe to annual periods"""
        # TODO: use anchored offsets?
        return df.resample("Y").sum()

    @staticmethod
    def amortize_loan(
        loan_amount,  # initial loan amount
        term: PositiveInt,  # in years
        interest_rate: FloatBetween0And1,  # annual interest rate
        start_date: pd.Period = pd.Period(date.today(), freq="M"),
    ) -> tuple[pd.DataFrame]:
        """
        Amortize a loan with a fixed interest rate over a fixed term.

        Parameters:
        - loan_amount: Initial loan amount.
        - term: Loan term in years.
        - interest_rate: Annual interest rate as a decimal between 0 and 1.
        - start_date: Start date of the loan amortization schedule. Defaults to the current date.

        Returns:
        - df: DataFrame containing the loan amortization schedule.
        - summary: Summary statistics of the loan amortization.

        Example usage:
        >>> loan_amount = 100000
        >>> term = 5
        >>> interest_rate = 0.05
        >>> start_date = pd.Period('2022-01', freq='M')
        >>> df, summary = amortize_loan(loan_amount, term, interest_rate, start_date)
        """
        monthly_rate = interest_rate / 12
        total_payments = term * 12
        payment = pmt(monthly_rate, total_payments, loan_amount) * -1

        # Time array for the payment schedule
        months = pd.period_range(start_date, periods=total_payments, freq="M")

        # Payments are constant, just repeat the fixed payment
        payments = np.full(shape=(total_payments,), fill_value=payment)

        # Calculate interest for each period
        interest_paid = np.empty(shape=(total_payments,))
        balances = np.empty(shape=(total_payments,))

        balances[0] = loan_amount
        for i in range(total_payments):
            interest_paid[i] = balances[i] * monthly_rate
            principal_paid = payments[i] - interest_paid[i]
            if i < total_payments - 1:
                balances[i + 1] = balances[i] - principal_paid

        # The final balance is zero
        balances[-1] = 0

        # Create DataFrame
        df = pd.DataFrame(
            {
                "Period": np.arange(1, total_payments + 1),
                "Month": months,
                "Begin Balance": np.roll(balances, 1),
                "Payment": payments,
                "Interest": interest_paid,
                "Principal": payments - interest_paid,
                "End Balance": balances,
            }
        )
        df.iloc[0, df.columns.get_loc("Begin Balance")] = (
            loan_amount  # Fix the first beginning balance
        )

        # Set 'Month' as the index
        df.set_index("Month", inplace=True)

        # Summary statistics
        summary = pd.Series(
            {
                "Payoff Date": df.index[-1],
                "Total Payments": df["Payment"].sum(),
                "Total Principal Paid": df["Principal"].sum(),
                "Total Interest Paid": df["Interest"].sum(),
                "Last Payment Amount": df["Payment"].iloc[-1],
            }
        )

        return df, summary

    def shift_ordinal_to_project_timeline(self, df: pd.DataFrame) -> pd.DataFrame:
        """Shift a dataframe to the project start date from ordinal time (1970)"""
        df_start_date = pd.Period(ordinal=0, freq="M")
        difference = self.project_start_date - df_start_date
        return df.shift(difference.n, freq="M")

    @model_validator(mode="before")
    def validate_cap_rates(cls, values):
        cap_rates = values.get("cap_rates")
        if isinstance(cap_rates, float):
            # Convert single float to a list of CapRates objects with the same rate for all uses
            values["cap_rates"] = [
                CapRates(
                    name=f"{use} Cap Rate",
                    program_use=use,
                    development_cap_rate=cap_rates,
                    refinance_cap_rate=cap_rates,
                    sale_cap_rate=cap_rates,
                )
                for use in ProgramUseEnum
            ]
        return values
