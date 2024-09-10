# %%
from datetime import date
from enum import Enum

import matplotlib.pyplot as plt

# # NOTE: to silence pandas FutureWarning https://stackoverflow.com/a/15778297/4581314
# import warnings
# warnings.simplefilter(action='ignore', category=FutureWarning)
import numpy as np
import pandas as pd

# from dateutil.relativedelta import *
from pydantic import BaseModel, Field, field_validator
from pyobsplot import Obsplot, Plot, js
from pyxirr import pmt, xirr
from scipy.stats import norm
from typing_extensions import Annotated, Literal, Optional, Union

pd.set_option("display.precision", 2)
pd.options.display.float_format = "{:.2f}".format
# pd.set_option('display.max_rows', 999)
# pd.set_option('display.max_columns', 999)
# pd.set_option('display.width', 999)

# constrained types
PositiveInt = Annotated[int, Field(strict=True, ge=0)]
PositiveIntGt1 = Annotated[int, Field(strict=True, gt=1)]
PositiveFloat = Annotated[float, Field(strict=True, ge=0)]
FloatBetween0And1 = Annotated[float, Field(strict=True, ge=0, le=1)]


# %%


def amortize_loan(
    loan_amount,  # initial loan amount
    term: PositiveInt,  # in years
    interest_rate: FloatBetween0And1,  # annual interest rate
    start_date: pd.Period = pd.Period(date.today(), freq="M"),
):
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


# Example usage
loan_df, loan_summary = amortize_loan(
    loan_amount=100000, term=30, interest_rate=0.05, start_date="2024-01-01"
)
loan_df
# loan_summary
# loan_df.plot(y=['Principal', 'Interest'], figsize=(12, 6), title='Loan Amortization')


# %%


class Model(BaseModel):
    class Config:
        arbitrary_types_allowed = True


########################
######### TIME #########
########################


class CashFlowItem(Model):
    """Class for a generic cash flow line item"""

    # GENERAL
    name: str  # "Construction Cost"
    category: str  # category of the item (budget, revenue, expense, etc.)
    subcategory: str  # subcategory of the item (land, hard costs, soft costs, condo sales, apartment rental, etc.)
    notes: Optional[str] = None  # optional notes on the item

    # TIMELINE
    start_date: pd.Period = pd.Period(
        ordinal=0, freq="M"
    )  # month zero (need to shift to project start date)  # TODO: move to property? because not user-defined anymore
    periods_until_start: PositiveInt  # months, from global start date of project
    active_duration: PositiveInt  # months

    @property
    def total_duration(self) -> PositiveInt:
        """Total duration (number of periods) in months from global start date, including delay until start"""
        return self.periods_until_start + self.active_duration

    @property
    def timeline_total(self) -> pd.PeriodIndex:
        """Construct a timeline period index for total duration, including delay until start"""
        return pd.period_range(self.start_date, periods=self.total_duration, freq="M")

    @property
    def timeline_active(self) -> pd.PeriodIndex:
        """Construct a timeline period index for *active* duration only"""
        return pd.period_range(
            self.start_date + self.periods_until_start,
            periods=self.active_duration,
            freq="M",
        )

    @field_validator("start_date", mode="before")
    def to_period(value) -> pd.Period:
        """Cast as a pandas period"""
        return pd.Period(value, freq="M")


# %%
##########################
######### BUDGET #########
##########################


class BudgetItem(CashFlowItem):
    """Class for a generic cost line item"""

    # TODO: subclass for specific budget line items (Developer, A&E, Soft Costs, FF&E, Other)
    # TODO: add optional details list for more granular budgeting (i.e., rolling-up to a parent budget item)
    # GENERAL
    category: Literal["Budget"] = "Budget"
    subcategory: Literal["Land", "Hard Costs", "Soft Costs", "Other"]
    # subcategory: Optional[BudgetSubcategoryEnum] = None

    # COST
    cost_total: PositiveFloat  # 1_000_000.00
    # DRAW SCHEDULE
    draw_sched_kind: Literal[
        "s-curve", "uniform", "manual"
    ]  # TODO: use enum? add triang? others?
    draw_sched_sigma: Optional[PositiveFloat]  # more info for s-curve (and others?)
    # draw_sched_manual: Optional[np.ndarray]  # full cash flow manual input

    @property
    def budget_df(self) -> pd.DataFrame:
        """Construct cash flow for budget costs with categories and subcategories"""
        if self.draw_sched_kind == "s-curve":
            timeline_int = np.arange(0, self.active_duration)
            cf = pd.Series(
                (
                    norm.cdf(
                        timeline_int + 1,
                        self.active_duration / 2,
                        self.draw_sched_sigma,
                    )
                    - norm.cdf(
                        timeline_int, self.active_duration / 2, self.draw_sched_sigma
                    )
                )
                / (1 - 2 * norm.cdf(0, self.active_duration / 2, self.draw_sched_sigma))
                * self.cost_total,
                index=self.timeline_active,
            )
        elif self.draw_sched_kind == "uniform":
            cf = pd.Series(
                np.ones(self.active_duration) * self.cost_total / self.active_duration,
                index=self.timeline_active,
            )
        # elif self.draw_sched_kind == "manual":
        #     cf = pd.Series(self.draw_sched_manual,
        #                    index=self.timeline)
        # TODO: curve shaping of draws https://www.adventuresincre.com/draw-schedule-custom-cash-flows/
        # create a dataframe with the cash flow and add category and subcategory for downstream analysis
        df = pd.DataFrame(cf)
        # add name, category and subcategory
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        return df

    # CONSTRUCTORS
    @classmethod
    def from_unitized(
        cls,
        name: str,
        # category: Literal["Budget"],
        subcategory: Literal["Land", "Hard Costs", "Soft Costs", "Other"],
        unitized_cost: PositiveFloat,  # by GSF, NSF/SSF/RSF, unit, etc. as desired
        unit_count: PositiveInt,  # number of units or area
        periods_until_start: PositiveInt,
        active_duration: PositiveInt,
        draw_sched_kind: Literal["s-curve", "uniform", "manual"],
        # start_date: Optional[pd.Period] = None,
        notes: Optional[str] = None,
        draw_sched_sigma: Optional[PositiveFloat] = None,
    ) -> "BudgetItem":
        """Construct a budget item from unitized cost and count"""
        cost_total = unitized_cost * unit_count
        return cls(
            name=name,
            # category=category,
            subcategory=subcategory,
            notes=notes,
            cost_total=cost_total,
            # start_date=start_date,
            periods_until_start=periods_until_start,
            active_duration=active_duration,
            draw_sched_kind=draw_sched_kind,
            draw_sched_sigma=draw_sched_sigma,
        )

    @classmethod
    def from_reference_items(
        cls,
        name: str,
        # category: Literal["Budget"],
        subcategory: Literal["Land", "Hard Costs", "Soft Costs", "Other"],
        reference_budget_items: list["BudgetItem"],
        reference_kind: Literal["sum", "passthrough"],
        reference_percentage: PositiveFloat,
        periods_until_start: PositiveInt,
        active_duration: PositiveInt,
        draw_sched_kind: Literal["s-curve", "uniform", "manual"],
        # start_date: Optional[pd.Period] = None,
        notes: Optional[str] = None,
        draw_sched_sigma: Optional[PositiveFloat] = None,
    ) -> "BudgetItem":
        """Construct a budget item as a percentage of another budget item or multiple items"""
        if reference_kind == "sum":
            cost_total = (
                sum([item.cost_total for item in reference_budget_items])
                * reference_percentage
            )
        elif reference_kind == "passthrough":
            cost_total = reference_budget_items[0].cost_total * reference_percentage
        return cls(
            name=name,
            # category=category,
            subcategory=subcategory,
            notes=notes,
            cost_total=cost_total,
            # start_date=start_date,
            periods_until_start=periods_until_start,
            active_duration=active_duration,
            draw_sched_kind=draw_sched_kind,
            draw_sched_sigma=draw_sched_sigma,
        )

    # TODO: just consider a factor-like approach a la opex items below


class Budget(Model):
    budget_items: list[BudgetItem]

    @property
    def budget_df(self) -> pd.DataFrame:
        return pd.concat([item.budget_df for item in self.budget_items])
        # TODO: just use a list for performance? (pd.concat copies data...)

    # TODO: individual cash flow items for each budget item?

    # TODO: add methods to sum up budget items by category and subcategory after shifting to project start date


# %%
###########################
######### PROGRAM #########
###########################


class ProgramUseEnum(str, Enum):
    """Enum for program uses"""

    residential = "Residential"
    affordable_residential = "Affordable Residential"
    office = "Office"
    retail = "Retail"
    amenity = "Amenity"
    other = "Other"


class Program(Model):  # CashFlowItem???
    """Class for a generic sellable/rentable program"""

    # PROGRAM BASICS
    name: str  # "Studio Apartments"
    # use: ProgramUseEnum  # use of the program (residential, office, retail, etc.)
    use: Literal[
        "Residential", "Affordable Residential", "Office", "Retail", "Amenity", "Other"
    ]

    # UNITS/AREA
    gross_area: Optional[PositiveFloat]  # gross area in square feet
    net_area: PositiveFloat  # net sellable/rentable area in square feet
    unit_count: PositiveInt  # number of income-generating units/spaces
    # program_multiplier: PositiveInt = 1  # if modeling more than one of the same program


###########################
######### REVENUE #########
###########################


class RevenueCategoryEnum(str, Enum):
    """Enum for revenue categories"""

    sale = "Sale"
    lease = "Lease"
    # TODO: make category models with subcategories built-in (and maybe a hierarchy)


class RevenueSubcategoryEnum(str, Enum):
    """Enum for revenue subcategories"""

    # TODO: develop more subcategories


class RevenueMultiplicandEnum(str, Enum):
    """Enum for program unit kinds (what is being multiplied against)"""

    whole = "Whole Unit"
    rsf = "RSF"  # rentable square feet
    parking_space = "Parking Space"
    other = "Other"


class RevenueItem(CashFlowItem):  # use abstract class?
    """Class for a generic revenue line item"""

    # GENERAL
    category: Literal["Revenue"] = "Revenue"
    subcategory: Literal["Sale", "Lease"]  # "Sale" or "Lease"
    # subcategory: Optional[str] = None  # TBD use, maybe: unit type, use, etc.

    # PROGRAM
    program: Program  # program generating the revenue

    # REVENUE
    # revenue_multiplicand: RevenueMultiplicandEnum  # whole unit, rsf, parking space, etc.
    revenue_multiplicand: Literal["Whole Unit", "RSF", "Parking Space", "Other"]
    revenue_multiplier: (
        PositiveFloat  # sales: $/{unit,space}; rental: $/{unit,rsf,space}/mo
    )


class SalesRevenueItem(RevenueItem):
    """Class for a sales revenue line item"""

    # GENERAL
    subcategory: Literal["Sale"]
    # REVENUE/SALES SCHEDULE
    revenue_sched_kind: Literal["s-curve", "uniform", "manual"]
    revenue_sched_sigma: Optional[PositiveFloat]
    # revenue_sched_manual: Optional[np.ndarray]  # full cash flow manual input

    # TODO: if Program uses units, then revenue CF is a function of unit count and price
    # thus the revenue schedule is a function of the program timeline and unit count
    # if Program uses area, then revenue CF is a function of area and price

    # TODO: revisit pre-sales logic

    @property
    def revenue_total(self) -> PositiveFloat:
        # compute multiplier based on multiplicand
        if self.revenue_multiplicand in ("Whole Unit", "Parking Space"):
            return self.revenue_multiplier * self.program.unit_count
        elif self.revenue_multiplicand == "RSF":
            return self.revenue_multiplier * self.program.net_area
        else:  # "Other" TODO: revisit this logic
            return self.revenue_multiplier * 1.0

    @property
    def revenue_df(self) -> pd.DataFrame:
        """Construct cash flow for sales revenue with categories and subcategories"""
        # TODO: curve shaping
        # TODO: schedule by unit if applicable (discrete distribution function), not just dollars
        # uniform sales, for now:
        cf = pd.Series(
            np.ones(self.active_duration) * self.revenue_total / self.active_duration,
            index=self.timeline_active,
        )
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program.use  # "Residential", "Office", "Retail", etc.
        return df


class RentalRevenueItem(RevenueItem):
    """Class for a rental revenue line item"""

    # FIXME: revisit pre-lease, lease-up pace logic
    # TODO: full lease config (lease-up, rollover, downtime, LC, TI, etc.)

    # GENERAL
    subcategory: Literal["Lease"]
    # TIMING
    active_duration: PositiveInt = (
        30 * 12
    )  # default 30 years (in months) - effectively infinite
    # RENTAL GROWTH
    revenue_growth_rate: FloatBetween0And1 = 0.03  # rental growth, simple annual
    # STRUCTURAL LOSSES
    vacancy_rate: FloatBetween0And1 = 0.05  # 5% vacancy/credit loss rate

    @property
    def initial_rent_rate(self) -> PositiveFloat:
        # compute multiplier based on multiplicand
        if self.revenue_multiplicand in ("Whole Unit", "Parking Space"):
            return (
                self.revenue_multiplier * self.program.unit_count
            )  # $/unit/mo -> $/mo
        elif self.revenue_multiplicand == "RSF":
            return self.revenue_multiplier * self.program.net_area  # $/sf/mo -> $/mo
        else:  # "Other" TODO: revisit this logic
            return self.revenue_multiplier * 1.0  # $/mo

    @property
    def revenue_df(self) -> pd.DataFrame:
        """Construct cash flow for rental revenue, with growth, with categories and subcategories"""
        # build rental cash flow from initial rent and growth rate
        growth_factors = np.ones(self.active_duration)
        growth_factors[12::12] = (
            1 + self.revenue_growth_rate
        )  # Apply growth factor at the beginning of each year after the first year
        cumulative_growth = np.cumprod(growth_factors)
        monthly_rents = self.initial_rent_rate * cumulative_growth
        cf = pd.Series(monthly_rents, index=self.timeline_active)
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program.use  # "Residential", "Office", "Retail", etc.
        return df
        # FIXME: concatenate a vacancy/credit loss schedule df, if applicable

    # THIS IS TOTAL POTENTIAL INCOME

    @property
    def structural_losses_df(self) -> pd.Series:
        """Construct cash flow for vacancy/credit losses"""
        cf = self.revenue_df[0] * self.vacancy_rate
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df["Name"] = self.name
        df["Category"] = "Losses"
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program.use  # "Residential", "Office", "Retail", etc.
        return df

    # THIS IS (THE DELTA FOR) EFFECTIVE GROSS REVENUE


AnyRevenueItem = Union[SalesRevenueItem, RentalRevenueItem]


class Revenue(Model):
    """Wrapper class for revenue items"""

    # REVENUE
    revenue_items: list[
        Annotated[AnyRevenueItem, Field(..., discriminator="subcategory")]
    ]

    # TODO: apply sales commissions at Project level (disposition cost of sales too)

    @property
    def revenue_df(self) -> pd.DataFrame:
        return pd.concat([item.revenue_df for item in self.revenue_items])
        # TODO: just use a list for performance? (pd.concat copies data...)

    @property
    def structural_losses_df(self) -> pd.Series:
        return pd.concat(
            [
                item.structural_losses_df
                for item in self.revenue_items
                if hasattr(item, "structural_losses_df")
            ]
        )

    # TODO: relationships between revenue and program (e.g., revenue per unit, sf, etc.)

    @property
    def program_summary(self) -> pd.DataFrame:
        """Summarize programs in the revenue items"""
        programs = list(
            set([item.program for item in self.revenue_items])
        )  # unique programs
        return pd.DataFrame(
            [
                {
                    "Use": program.use,
                    "Gross Area": program.gross_area,
                    "Net Area": program.net_area,
                    "Unit Count": program.unit_count,
                }
                for program in programs
            ]
        )

    # TODO: trended vs untrended revenue metrics (parameterize year?)
    # method to get summary metrics with time (toward getting  trended vs untrended)


# %%
###########################
######### EXPENSE #########
###########################


# class ExpenseItem(CashFlowItem):  # FIXME: should be this not Model!?
class ExpenseItem(Model):
    """Class for a generic expense line item (rental use case) per program use"""

    # GENERAL
    name: str  # "Property Management Fee"
    category: Literal["Expense"] = "Expense"
    subcategory: Literal["OpEx", "CapEx"]  # operating expense vs capital expense
    # subcategory: Optional[str]  # TBD use

    # PROGRAM
    # program_use: ProgramUseEnum  # use of the program (residential, office, retail, etc.)
    program_use: Literal[
        "Residential", "Affordable Residential", "Office", "Retail", "Amenity", "Other"
    ]

    # EXPENSE
    expense_kind: Literal["cost", "factor"]  # FIXME: create an enum for kind?

    # REVENUE
    revenue: Revenue  # all revenue rolled together

    @property
    def revenue_df(self) -> pd.DataFrame:
        return self.revenue.revenue_df

    # @property
    # def expense_df(self) -> pd.DataFrame:
    #     # FIXME: implement and/or make abstract method
    #     raise NotImplementedError


class ExpenseCostItem(ExpenseItem):
    """
    Class for a generic operational expense line item (rental use case). Examples:

    ### OpEx
    - Repairs and Maintenance
    - Payroll
    - General & Administrative
    - Marketing
    - Utilities
    - Contract Services
    - Capital Reserves
    - Insurance
    - Taxes @ millage * assessment (external calculation)

    """

    # GENERAL
    expense_kind: Literal["cost"] = "cost"
    # COST
    initial_annual_cost: PositiveFloat  # total expense per year
    expense_growth_rate: FloatBetween0And1 = 0.03  # expense growth, simple annual

    @property
    def expense_df(self) -> pd.DataFrame:
        """Construct cash flow for expense costs with categories and subcategories"""
        mask = (
            (self.revenue_df["Category"] == "Revenue")
            & (self.revenue_df["Subcategory"] == "Lease")
            & (self.revenue_df["Use"] == self.program_use)
        )
        new_timeline = pd.period_range(
            self.revenue_df.loc[mask].index.min(),
            self.revenue_df.loc[mask].index.max(),
            freq="M",
        )
        growth_factors = np.ones(mask.sum())
        growth_factors[12::12] = (
            1 + self.expense_growth_rate
        )  # Apply growth factor at the beginning of each year after the first year
        cumulative_growth = np.cumprod(growth_factors)
        monthly_expenses = self.initial_annual_cost / 12 * cumulative_growth
        cf = pd.Series(monthly_expenses, index=new_timeline)
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program_use  # "Residential", "Office", "Retail", etc.
        return df


class ExpenseFactorItem(ExpenseItem):
    """

    Class for a generic expense factor (rental use case), of gross revenue. Examples:

    ### OpEx
    - Management Fee @ X% of EGR

    ### OpEx
    - Capital account @ X% of EGR?

    """

    # GENERAL
    expense_kind: Literal["factor"] = "factor"
    # FACTOR
    # program_use: ProgramUseEnum  # use of the program (residential, office, retail, etc.)
    program_use: Literal[
        "Residential", "Affordable Residential", "Office", "Retail", "Amenity", "Other"
    ]
    expense_factor: FloatBetween0And1  # expense factor as a percentage of *revenue*

    @property
    def expense_df(self) -> pd.DataFrame:
        """Construct cash flow for expense factors with categories and subcategories"""
        mask = (
            (self.revenue_df["Category"] == "Revenue")
            & (self.revenue_df["Subcategory"] == "Lease")
            & (self.revenue_df["Use"] == self.program_use)
        )
        new_timeline = pd.period_range(
            self.revenue_df.loc[mask].index.min(),
            self.revenue_df.loc[mask].index.max(),
            freq="M",
        )
        cf = pd.Series(
            self.revenue_df.loc[mask][0] * self.expense_factor, index=new_timeline
        )
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program_use
        return df


AnyExpenseItem = Union[ExpenseCostItem, ExpenseFactorItem]


class Expense(Model):
    """Wrapper class for expense items"""

    # EXPENSES ITEMS
    expense_items: list[
        Annotated[AnyExpenseItem, Field(..., discriminator="expense_kind")]
    ]

    # need to disagregate by opex/capex and program use

    # FIXME: aggregate all expense dfs into a master df

    # TODO: summary statistics on expenses (opex, capex)

    @property
    def expense_df(self) -> pd.DataFrame:
        return pd.concat([item.expense_df for item in self.expense_items])
        # TODO: just use a list for performance? (pd.concat copies data...)


# %%
#############################
######### FINANCING #########
#############################


class ConstructionFinancing(Model):
    """Class for a generic financing line item"""

    # TODO: consider multiple financing types and interactions (construction, mezzanine, permanent, etc.)
    # TODO: construction: pass target LTC for traditional construction loan with LTC cap, have fallover mezzanine loan

    # FIXME: fixed rate vs floating rate options

    interest_rate: FloatBetween0And1
    fee_rate: FloatBetween0And1  # TODO: should this be a dollar amount?
    # ltc_ratio: FloatBetween0And1  # FIXME: use a loan-to-cost ratio in debt sizing and mezzanine rollover; loan + mezz ltc = debt-to-equity ratio


class PermanentFinancing(Model):
    interest_rate: FloatBetween0And1
    fee_rate: FloatBetween0And1  # TODO: should this be a dollar amount?
    ltv_ratio: FloatBetween0And1 = 0.75  # TODO: add warnings for DSCR
    amortization: PositiveInt = 30  # term in years


# %%
###########################
######### PROJECT #########
###########################


class CapRates(Model):
    """Class for a generic cap rate model"""

    name: str  # "Residential Cap Rates"
    # program_use: ProgramUseEnum  # program use for the cap rate model
    program_use: Literal[
        "Residential", "Affordable Residential", "Office", "Retail", "Amenity", "Other"
    ]
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
    cap_rates: list[CapRates]  # market cap rates FOR EACH PROGRAM USE
    hold_duration: Optional[
        PositiveIntGt1
    ]  # years to hold before disposition (required for rental revenues only)
    # -> sales and rental:
    cost_of_sale: FloatBetween0And1 = 0.03  # cost of sale as a percentage of sale price (broker fees, closing costs, etc.)

    # FIXME: validator to ensure a cap rate for each program use!

    # PROPERTIES  for important cash flows

    @property
    def _budget_table(self) -> pd.DataFrame:
        shifted = self.shift_ordinal_to_project_timeline(self.budget.budget_df)
        return shifted.pivot_table(
            values=0,
            index=shifted.index,
            columns=["Category", "Subcategory", "Name"],
            aggfunc="sum",
        ).fillna(0)

    @property
    def _revenue_table(self) -> pd.DataFrame:
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
        Pivot table of budget costs before financing

        Returns a dataframe with a multi-index of Category, Subcategory, and Name, and the following structure:
        - Index: Project timeline
        - Columns: Category, Subcategory, Name
        - Values: Total costs before financing

        """
        return self._budget_table

    @property
    def construction_financing_cf(self) -> pd.DataFrame:
        """
        Compute construction financing cash flow with debt and equity draws, fees, and interest reserve (interest/fees accrued)

        Financing fees, if applicable, are based on the total pre-interest reserve debt and are drawn in the period where debt draws begin

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
        return self.construction_financing_cf["Equity Draw"].to_frame("Equity")

    ##################
    # RENTAL REVENUE #
    ##################

    @property
    def total_potential_income_cf(self) -> pd.DataFrame:
        """Construct cash flow for total potential income by program use

        Use      Office    Residential
        1972-01  30000.00  21000.00
        1972-02  30000.00  21000.00
        ...      ...       ...

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
        """Construct cash flow for structural losses by program use"""
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
        """Construct cash flow for effective gross revenue by program use"""
        return self.total_potential_income_cf - self.losses_cf

    @property
    def opex_cf(self) -> pd.DataFrame:
        return (
            self._expense_table.loc[:, ("Expense", "OpEx", slice(None), slice(None))]
            .groupby(level=2, axis=1)
            .sum()
        )

    @property
    def net_operating_income_cf(self) -> pd.DataFrame:
        return self.effective_gross_revenue_cf - self.opex_cf

    @property
    def capex_cf(self) -> pd.DataFrame:
        return (
            self._expense_table.loc[:, ("Expense", "CapEx", slice(None), slice(None))]
            .groupby(level=2, axis=1)
            .sum()
        )

    @property
    def cash_flow_from_operations_cf(self) -> pd.DataFrame:
        return (
            (self.net_operating_income_cf - self.capex_cf)
            .reindex(self.project_timeline)
            .fillna(0)
        )

    @property
    def _cap_rates_table(self) -> pd.DataFrame:
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
        """Compute the refinance value by program use and combine into a single value"""
        return (
            self.net_operating_income_cf.loc[
                self.stabilization_date : (self.stabilization_date + 11)
            ]
            / self._cap_rates_table["Refinance Cap Rate"]
        ).sum()
        # FIXME: check this math/shape

    @property
    def construction_loan_repayment_cf(self) -> pd.DataFrame:
        """Compute the construction loan repayment (cumulative draw + interest) at stabilization"""
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
        """Compute the refinance amount by program use and combine into a single value"""
        return self.refinance_value * self.permanent_financing.ltv_ratio

    @property
    def refinance_infusion_cf(self) -> pd.DataFrame:
        """Compute the refinance infusion cash flow"""
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
        """Compute the permanent financing cash flow"""
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
        """Compute the permanent financing repayment cash flow"""
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
        """Compute cash flow after financing"""
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
        """Compute the debt service coverage ratio over time"""
        return (
            self.net_operating_income_cf
            / self.permanent_financing_cf["Payment"].iloc[0]
        )

    @property
    def sale_value(self) -> float:
        """Compute the sale value by program use and combine into a single value"""
        return (
            self.net_operating_income_cf.loc[
                self.project_end_date : (self.project_end_date + 11)
            ].sum()
            / self._cap_rates_table["Sale Cap Rate"]
        ).sum()
        # FIXME: check this math/shape with multiple program uses

    @property
    def disposition_cf(self) -> pd.DataFrame:
        """Compute the sale infusion cash flow"""
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
        """Construct cash flow for total sales revenue by program use"""
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
        """Compute the sale proceeds cash flow"""
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
        """Compute unlevered cash flow"""
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
        """Compute levered cash flow"""
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


########################
######### DEAL #########
########################


class Model(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class Partner(Model):
    name: str
    kind: Literal["GP", "LP"]
    share: FloatBetween0And1  # percentage of total equity


class Promote(Model):
    # different kinds of promotes:
    # - none (pari passu, no GP promote)
    # - waterfall (tiered promotes)
    # - carry (e.g., simple 20% after pref)
    kind: Literal["waterfall", "carry"]


class WaterfallTier(Model):
    """Class for a waterfall tier"""

    tier_hurdle_rate: PositiveFloat  # tier irr or em hurdle rate
    metric: Literal["IRR", "EM"]  # metric for the promote
    promote_rate: FloatBetween0And1  # promote as a percentage of total profits


class WaterfallPromote(Promote):
    """Class for a waterfall promote"""

    kind: Literal["waterfall"]
    pref_hurdle_rate: (
        PositiveFloat  # minimum IRR or EM to trigger promote (tier 1); the 'pref'
    )
    tiers: list[WaterfallTier]
    final_promote_rate: FloatBetween0And1  # final tier, how remainder is split after all tiers (usually 50/50)


class CarryPromote(Promote):
    """Class for a GP carry promote"""

    kind: Literal["carry"]
    pref_hurdle_rate: PositiveFloat  # minimum IRR or EM to trigger promote; the 'pref'
    promote_rate: FloatBetween0And1  # promote as a percentage of total profits
    # TODO: consider clawbacks and other carry structures


class Deal(Model):
    """Class for a generic deal"""

    project: Project
    partners: list[Partner]
    promote: Optional[
        WaterfallPromote | CarryPromote
    ]  # there can also be no GP promote, just pari passu
    # param for running calculations on monthly or annual basis
    time_basis: Literal["monthly", "annual"] = "monthly"

    # TODO: add property-level GP fees (mgmt/deal fees, acquisition/disposition fees, etc.)

    @property
    def project_net_cf(self) -> pd.Series:
        """Compute project net cash flow"""
        # TODO: correct for property-level GP fees
        # get unlevered cash flow df from project
        project_df = self.project.levered_cash_flow
        # if time_basis is annual, convert to annual
        if self.time_basis == "annual":
            project_df = Project.convert_to_annual(project_df)
        # set index to timestamp for pyxirr
        project_df.set_index(project_df.index.to_timestamp(), inplace=True)
        # get net cash flow column as Series
        project_net_cf = project_df["Levered Cash Flow"]
        return project_net_cf

    @property
    def project_equity_cf(self) -> pd.Series:
        """Compute project equity cash flow"""
        return (
            self.project_net_cf[self.project_net_cf < 0]
            .reindex(self.project.project_timeline)
            .fillna(0)
        )

    @property
    def project_irr(self) -> float:
        """Compute project IRR"""
        return xirr(self.project_net_cf)

    @property
    def partner_irrs(self) -> dict[str, float]:
        """Compute partner IRRs"""
        partner_df = self.calculate_distributions()
        partner_irrs = {
            partner: xirr(partner_df[partner]) for partner in partner_df.columns
        }
        return partner_irrs

    @property
    def project_equity_multiple(self) -> float:
        """Compute project equity multiple"""
        return Deal.equity_multiple(self.project_net_cf)

    @property
    def partner_equity_multiples(self) -> dict[str, float]:
        """Compute partner Equity Multiples"""
        partner_df = self.calculate_distributions()
        partner_equity_multiples = {
            partner: Deal.equity_multiple(partner_df[partner])
            for partner in partner_df.columns
        }
        return partner_equity_multiples

    @property
    def distributions(self) -> pd.DataFrame:
        """Calculate and return distributions based on the promote structure."""
        if self.promote.kind == "carry":
            return self._distribute_carry_promote()
        elif self.promote.kind == "waterfall":
            distributions_df, _ = self._distribute_waterfall_promote()
            # TODO: handle partner tiers return gracefully (maybe in another details method?)
            return distributions_df
        else:
            return self._distribute_pari_passu()

    def _distribute_carry_promote(self) -> pd.DataFrame:
        """Distribute cash flows with carry promote structure."""
        equity_cf = self.project_equity_cf
        lp_share = sum(p.share for p in self.partners if p.kind == "LP")
        gp_share = 1 - lp_share
        promote_rate = self.promote.promote_rate
        pref_rate = self.promote.pref_hurdle_rate

        # Calculate accrued preferred return interest
        pref_accrued = self._accrue_interest(equity_cf, pref_rate, self.time_basis)
        pref_distribution = pref_accrued.clip(upper=self.project_net_cf)

        # Distribute preferred return first
        remaining_cf = self.project_net_cf - pref_distribution.sum(axis=1)

        # Initialize distributions for each partner
        distributions = {
            partner.name: pd.Series(0, index=self.project_net_cf.index)
            for partner in self.partners
        }

        # Allocate preferred distributions
        for partner in self.partners:
            if partner.kind == "LP":
                distributions[partner.name] += pref_distribution * partner.share
            else:
                distributions[partner.name] += pref_distribution * gp_share

        # Distribute remaining cash flows
        lp_remaining_cf = remaining_cf * lp_share
        gp_carry = remaining_cf * promote_rate
        gp_remaining_cf = remaining_cf * gp_share + gp_carry
        lp_remaining_cf -= gp_carry

        # Allocate remaining cash flows
        for partner in self.partners:
            if partner.kind == "LP":
                distributions[partner.name] += lp_remaining_cf * partner.share
            else:
                distributions[partner.name] += gp_remaining_cf

        # Return distributions
        distributions_df = pd.DataFrame(distributions)
        return distributions_df

    # TODO: this is a european waterfall, how would an american style work? support both? https://www.adventuresincre.com/watch-me-build-american-style-real-estate-equity-waterfall/
    # TODO: catchup provision in (european) waterfall
    # TODO: lookback/clawback provision in (american) waterfall
    # TODO: if both IRR and EMx are used, manage this

    # FIXME: disaggregate GP coinvestment return from promote return

    def _distribute_waterfall_promote(self) -> pd.DataFrame:
        """Distribute cash flows with waterfall promote structure."""
        equity_cf = self.project_equity_cf
        net_cf = self.project_net_cf
        lp_share = sum(p.share for p in self.partners if p.kind == "LP")
        gp_share = 1 - lp_share
        remaining_cf = net_cf.copy()
        distributions = {
            partner.name: pd.Series(0, index=net_cf.index) for partner in self.partners
        }
        tier_distributions = {
            f"{partner.name}_Tier_{i+1}": pd.Series(0, index=net_cf.index)
            for i in range(len(self.promote.tiers) + 1)
            for partner in self.partners
        }

        # PREF (Tier 1)
        pref_rate = self.promote.pref_hurdle_rate
        # Calculate the accrued preferred return interest
        pref_accrued = self._accrue_interest(equity_cf, pref_rate, self.time_basis)
        # Distribute preferred return based on the accrued interest
        pref_distribution = pref_accrued.clip(upper=remaining_cf)
        for partner in self.partners:
            share = partner.share if partner.kind == "LP" else gp_share
            # Allocate the preferred distribution to each partner
            tier_distributions[f"{partner.name}_Tier_1"] = pref_distribution * share
            distributions[partner.name] += pref_distribution * share
        remaining_cf -= pref_distribution.sum(axis=1)

        # SUBSEQUENT TIERS
        for i, tier in enumerate(self.promote.tiers):
            tier_rate = tier.tier_hurdle_rate
            promote_rate = tier.promote_rate
            # Calculate the accrued return for the current tier
            accrued_return = self._accrue_interest(
                equity_cf, tier_rate, self.time_basis
            )
            required_return = accrued_return - pref_accrued
            # Distribute the return required for the current tier
            tier_distribution = required_return.clip(upper=remaining_cf)
            lp_share_after_promote = lp_share * (1 - promote_rate)
            gp_share_after_promote = 1 - lp_share_after_promote
            for partner in self.partners:
                if partner.kind == "LP":
                    # Allocate the tier distribution to each LP partner
                    tier_distributions[f"{partner.name}_Tier_{i+2}"] = (
                        tier_distribution * lp_share_after_promote
                    )
                    distributions[partner.name] += (
                        tier_distribution * lp_share_after_promote
                    )
                else:
                    # Allocate the tier distribution to the GP partner
                    tier_distributions[f"{partner.name}_Tier_{i+2}"] = (
                        tier_distribution * gp_share_after_promote
                    )
                    distributions[partner.name] += (
                        tier_distribution * gp_share_after_promote
                    )
            remaining_cf -= tier_distribution.sum(axis=1)
            pref_accrued += tier_distribution

        # FINAL PROMOTE
        final_promote_rate = self.promote.final_promote_rate
        for partner in self.partners:
            if partner.kind == "LP":
                # Allocate the final promote distribution to each LP partner
                tier_distributions[f"{partner.name}_Final"] = (
                    remaining_cf * lp_share * (1 - final_promote_rate)
                )
                distributions[partner.name] += (
                    remaining_cf * lp_share * (1 - final_promote_rate)
                )
            else:
                # Allocate the final promote distribution to the GP partner
                tier_distributions[f"{partner.name}_Final"] = remaining_cf * (
                    1 - lp_share * (1 - final_promote_rate)
                )
                distributions[partner.name] += remaining_cf * (
                    1 - lp_share * (1 - final_promote_rate)
                )

        # RETURN DISTRIBUTIONS
        distributions_df = pd.DataFrame(distributions)
        tier_distributions_df = pd.DataFrame(tier_distributions)
        return distributions_df, tier_distributions_df

    def _distribute_pari_passu(self) -> pd.DataFrame:
        """
        Assigns equity and distributes returns pari passu, without any promotes.
        """
        distributions = {
            partner.name: self.project_net_cf * partner.share
            for partner in self.partners
        }
        distributions_df = pd.DataFrame(distributions)
        return distributions_df

    @staticmethod
    def _accrue_interest(
        equity_cf: pd.Series, rate: float, time_basis: str
    ) -> pd.Series:
        """Accrue interest on equity cash flows using capital account logic."""
        periods = 12 if time_basis == "monthly" else 1
        accrued = pd.Series(0, index=equity_cf.index)
        capital_account = pd.Series(0, index=equity_cf.index)
        # Loop through each period to adjust capital account and compute interest
        for i in range(1, len(equity_cf)):
            # Adjust capital account based on previous balance, equity contribution, and distribution
            capital_account.iloc[i] = capital_account.iloc[i - 1] + equity_cf.iloc[i]
            # Calculate accrued interest on adjusted capital account balance
            accrued.iloc[i] = capital_account.iloc[i] * (
                (1 + rate / periods) ** (1 / periods) - 1
            )
        return accrued

    #####################
    # HELPERS/UTILITIES #
    #####################

    @staticmethod
    def equity_multiple(cash_flows: pd.Series) -> float:
        """Compute equity multiple from cash flows"""
        return cash_flows[cash_flows > 0].sum() / abs(cash_flows[cash_flows < 0].sum())

    # FIXME: bring back validators updating to new fields
    # @model_validator(mode="before")
    # def validate_partners(self):
    #     """Validate the partner structure"""
    #     # check that there is at least one GP and one LP
    #     if len([partner for partner in self.partners if partner.kind == "GP"]) != 1:
    #         raise ValueError("At least one (and only one) GP partner is required")
    #     if not any(partner.kind == "LP" for partner in self.partners):
    #         raise ValueError("At least one LP partner is required")
    #     # check that partner shares sum to 1.0
    #     if sum(partner.share for partner in self.partners) != 1.0:
    #         raise ValueError("Partner shares must sum to 1.0")
    #     return self

    # @model_validator(mode="before")
    # def validate_promote(self):
    #     """Validate the promote structure"""
    #     if self.promote.kind == "waterfall":
    #         # check that only metric is consistent across tiers (only IRR or EM)
    #         if any(tier.metric != self.promote.tiers[0].metric for tier in self.promote.tiers):
    #             raise ValueError("All tiers must use the same metric (IRR or EM)")
    #         # check that all tiers are higher than the hurdle
    #         if any(tier.tier_hurdle < self.promote.hurdle for tier in self.promote.tiers):
    #             raise ValueError("All tiers must be higher than the hurdle")
    #     return self


# %%

###################################
###################################
############ INSTANCES ############
###################################
###################################

# # INSTANTIATE A DCF ANALYSIS
# project_start_date = "2020-01"

# # residential
# program_residential = Program(
#     name="Example Residential",
#     program_start_date=project_start_date,
#     floor_area_gross=5000.0,
#     area_efficiency=1.0,
#     unit_count=1,
#     constr_cost_unitized=300.0,
#     constr_cost_units="area",
#     constr_cost_dist_type="s-curve",
#     constr_draw_sched_sigma=2.0,
#     constr_periods_until_start=8,
#     constr_duration=18,
#     sales_start=24,
#     sales_duration=8,
#     sales_price_unitized=3000000.0
# )
# program_residential2 = Program(
#     name="Example Residential 2",
#     program_start_date=project_start_date,
#     floor_area_gross=3000.0,
#     area_efficiency=1.0,
#     unit_count=1,
#     constr_cost_unitized=300.0,
#     constr_cost_units="area",
#     constr_cost_dist_type="s-curve",
#     constr_draw_sched_sigma=2.0,
#     constr_periods_until_start=2,
#     constr_duration=12,
#     sales_start=14,
#     sales_duration=4,
#     sales_price_unitized=1200000.0
# )

# # project
# my_project = Project(
#     name="Le Jules Verne",
#     project_start_date=project_start_date,
#     programs=[program_residential, program_residential2],
#     soft_costs_factor=0.2,
#     debt_to_equity=0.4,
#     land_costs=1_000_000.0
# )


# %%
# from A.CRE s-curve cost distribution https://www.adventuresincre.com/development-budget-distributing-cash-flows-using-the-s-curve-method/
# see also their reference https://www.mrexcel.com/board/threads/cost-distribution-based-on-bell-shaped-curve.340723/post-3724269
# TODO: use pd Series shift() for second term
# s-curve:
# (norm.cdf(NOW_MONTHS + 1, 9.5, 2) - norm.cdf(NOW_MONTHS, 9.5, 2)) / (1 - 2 * norm.cdf(0, 9.5, 2)) * COST
# triangular(?):
# (triang.cdf(hi+1,1,scale=12) - triang.cdf(hi,1,scale=12)) * COST


# %%
# create working datasets

# TIME
# start_date = pd.Period(ordinal=0, freq="M")
# active_duration = 12
# periods_until_start = 4
# total_duration = periods_until_start + active_duration
# timeline_total = pd.period_range(start_date, periods=total_duration, freq="M")
# timeline_active = pd.period_range(start_date + periods_until_start, periods=active_duration, freq="M")

# BUDGET
land = BudgetItem(
    name="Land",
    subcategory="Land",
    cost_total=1_000_000.0,
    periods_until_start=0,
    active_duration=1,
    draw_sched_kind="uniform",
    draw_sched_sigma=None,
)
constr_costs = BudgetItem(
    name="Construction Costs",
    subcategory="Hard Costs",
    cost_total=3_000_000.0,
    periods_until_start=6,
    active_duration=18,
    draw_sched_kind="s-curve",
    draw_sched_sigma=3.0,
)
demo_costs = BudgetItem(
    name="Demolition",
    subcategory="Hard Costs",
    cost_total=500_000.0,
    periods_until_start=3,
    active_duration=3,
    draw_sched_kind="s-curve",
    draw_sched_sigma=1.0,
)
soft_costs = BudgetItem.from_reference_items(
    name="Total Soft Costs",
    subcategory="Soft Costs",
    reference_budget_items=[constr_costs, demo_costs],
    reference_kind="passthrough",
    reference_percentage=0.3,  # 30% of hard costs
    periods_until_start=1,
    active_duration=31,
    draw_sched_kind="uniform",
    draw_sched_sigma=None,
)
land_df = land.budget_df
hc_df = constr_costs.budget_df
demo_df = demo_costs.budget_df
sc_df = soft_costs.budget_df
# all_dfs = [land_df, hc_df, demo_df, sc_df]
# concat_df = pd.concat(all_dfs)

budget = Budget(budget_items=[land, constr_costs, demo_costs, soft_costs])
concat_df = budget.budget_df

# create a new timeline with all dataframes reindexed
min_index = concat_df.index.min()
max_index = concat_df.index.max()
new_timeline = pd.period_range(min_index, max_index, freq="M")
concat_pt = concat_df.pivot_table(
    values=0,
    index=concat_df.index,
    columns=["Category", "Subcategory", "Name"],
    aggfunc="sum",
).fillna(0)
# reindex to full extent timeline
concat_pt = concat_pt.reindex(new_timeline, fill_value=0)
concat_pt

# sum by category (budget)
concat_pt.groupby(level=0, axis=1).sum()
# sum by subcategory (hard costs, soft costs, etc.)
concat_pt.groupby(level=1, axis=1).sum()
# display only hard costs
concat_pt.loc[:, ("Budget", "Hard Costs", slice(None))]
# create a new column for financing
# concat_pt.loc[:,("Financing", "Construction", "Interest Reserve")] = 1.

# plot with colors for categories
concat_pt.plot(kind="bar", stacked=True)


# %%
# # REVENUE
# # residential
# program_residential_condos = Program(
#     name="Residential Condos",
#     use="Residential",
#     gross_area=5000.0,
#     net_area=3000.0,
#     unit_count=6,
#     development_cap_rate=0.05,
#     stabilization_cap_rate=0.05,
#     sale_cap_rate=0.05,
# )
# program_residential_apts = Program(
#     name="Residential Apartments",
#     use="Residential",
#     gross_area=5000.0,
#     net_area=3000.0,
#     unit_count=6,
#     development_cap_rate=0.05,
#     stabilization_cap_rate=0.05,
#     sale_cap_rate=0.05,
# )
# # sales revenue
# sales_revenue = SalesRevenueItem(
#     name="2bd Condos",
#     subcategory="Sale",
#     periods_until_start=24,
#     active_duration=8,
#     program=program_residential_condos,
#     revenue_multiplicand="Whole Unit",
#     revenue_multiplier=1_000_000.0,
#     revenue_sched_kind="uniform",
#     revenue_sched_sigma=None
# )
# sales_revenue2 = SalesRevenueItem(
#     name="3bd Condos",
#     subcategory="Sale",
#     periods_until_start=24,
#     active_duration=6,
#     program=program_residential_condos,
#     revenue_multiplicand="Whole Unit",
#     revenue_multiplier=2_000_000.0,
#     revenue_sched_kind="uniform",
#     revenue_sched_sigma=None
# )
# # # rental revenue
# rental_revenue = RentalRevenueItem(
#     name="Example Residential Lease",
#     subcategory="Lease",
#     periods_until_start=24,
#     program=program_residential_apts,
#     revenue_multiplicand="Whole Unit",
#     revenue_multiplier=3_500.0,
#     revenue_sched_kind="uniform",
#     revenue_sched_sigma=None
# )
# # example office lease
# program_office = Program(
#     name="Office",
#     use="Office",
#     gross_area=5000.0,
#     net_area=3000.0,
#     unit_count=6
# )
# office_revenue = RentalRevenueItem(
#     name="Example Office Lease",
#     subcategory="Lease",
#     periods_until_start=24,
#     program=program_office,
#     revenue_multiplicand="Whole Unit",
#     revenue_multiplier=5_000.0,
#     revenue_sched_kind="uniform",
#     revenue_sched_sigma=None
# )
# # aggregate revenue
# revenue = Revenue(revenue_items=[
#     # sales_revenue,
#     # sales_revenue2,
#     rental_revenue,
#     # office_revenue,
# ])

# # rental expenses
# management_fee = ExpenseFactorItem(
#     name="Management Fee",
#     subcategory="OpEx",
#     program_use="Residential",
#     expense_factor=0.03,
#     revenue=revenue,
# )
# repairs_maintenance = ExpenseCostItem(
#     name="Repairs and Maintenance",
#     subcategory="OpEx",
#     program_use="Residential",
#     initial_annual_cost=5000.0,
#     expense_growth_rate=0.03,
#     revenue=revenue,
# )
# capital_improvements = ExpenseFactorItem(
#     name="Capital Improvements",
#     subcategory="CapEx",
#     program_use="Residential",
#     expense_factor=0.05,
#     revenue=revenue,
# )


# # aggregate expenses
# expense = Expense(expense_items=[
#     management_fee,
#     repairs_maintenance,
# ])


# # revenue calcs
# rents_df = rental_revenue.revenue_df
# sales_df = sales_revenue.revenue_df
# # all_dfs = [land_df, hc_df, demo_df, sc_df, rents_df]
# all_dfs = [land_df, hc_df, demo_df, sc_df, sales_df]
# concat_df = pd.concat(all_dfs)
# min_index = concat_df.index.min()
# max_index = concat_df.index.max()
# new_timeline = pd.period_range(min_index, max_index, freq="M")
# concat_pt = concat_df.pivot_table(values=0, index=concat_df.index, columns=['Category', 'Subcategory','Name'], aggfunc='sum').fillna(0)
# # reindex to full extent timeline
# concat_pt = concat_pt.reindex(new_timeline, fill_value=0)
# concat_pt
# concat_pt.plot(kind="bar", stacked=True)


# %%
# # get an index of all revenue items where the category is "Revenue" and the subcategory is "Lease", and the Use is "Residential"
# mask = (rents_df['Category'] == 'Revenue') & (rents_df['Subcategory'] == 'Lease') & (rents_df['Use'] == 'Residential')

# # timeline using min and max of rental revenue
# new_timeline = pd.period_range(
#     rents_df.loc[mask].index.min(),
#     rents_df.loc[mask].index.max(),
#     freq="M"
# )

# # create new expense cost cf based on rental revenue timeline
# growth_rate = 0.03
# initial_annual_cost = 5_000.

# growth_factors = np.ones(mask.sum())  # initialize growth factors with length of mask
# growth_factors[12::12] = 1 + growth_rate
# cumulative_growth = np.cumprod(growth_factors)
# monthly_expenses = (initial_annual_cost / 12) * cumulative_growth
# cf = pd.Series(monthly_expenses, index=new_timeline)
# df = pd.DataFrame(cf)
# # add name, category and subcategory columns
# df['Name'] = 'Repairs'
# df["Category"] = 'Expenses'
# df["Subcategory"] = 'OpEx'
# df["Use"] = 'Residential'  # "Residential", "Office",

# %%

# def compute_construction_financing(project_pt, debt_to_equity, financing_interest_rate, financing_fee_rate=0.02):
#     budget_cf = project_pt.groupby(level=0, axis=1).sum()['Budget']
#     total_project_cost = budget_cf.sum()
#     debt_portion = total_project_cost * debt_to_equity
#     equity_portion = total_project_cost * (1 - debt_to_equity)
#     df = pd.DataFrame(budget_cf)
#     # increase the timeline
#     df = df.reindex(pd.period_range(df.index.min(), df.index.max()+10, freq="M"), fill_value=0)
#     df.rename(columns={'Budget': 'Total Costs Before Financing'}, inplace=True)
#     df['Cumulative Costs'] = df['Total Costs Before Financing'].cumsum()
#     df['Equity Draw'] = np.where(
#         df['Cumulative Costs'] <= equity_portion,
#         df['Total Costs Before Financing'],
#         np.where(
#             df['Cumulative Costs'].shift(1) < equity_portion,
#             equity_portion - df['Cumulative Costs'].shift(1, fill_value=0),
#             0
#         )
#     )
#     df['Financing Fees'] = np.where(
#         (df['Cumulative Costs'] > equity_portion) & (df['Cumulative Costs'].shift(1) <= equity_portion),  # if cumulative costs are greater than equity portion and previous cumulative costs are less than or equal to equity portion
#         debt_portion * financing_fee_rate,  # calculate the financing fees
#         0  # otherwise, no fees
#     )
#     df['Debt Draw'] = df['Total Costs Before Financing'] - df['Equity Draw'] + df['Financing Fees']
#     df['Cumulative Debt Drawn'] = df['Debt Draw'].cumsum()
#     df['Interest Reserve'] = (df['Cumulative Debt Drawn'].shift(1, fill_value=0) * financing_interest_rate / 12)
#     df['Cumulative Debt Drawn'] += df['Interest Reserve'].cumsum()
#     return df

# debt = compute_construction_financing(
#     concat_pt,
#     0.65,
#     0.09
# )
# debt


def compute_construction_financing(
    project_pt, debt_to_equity, financing_interest_rate, financing_fee_rate=0.02
):
    budget_cf = project_pt.groupby(level=0, axis=1).sum()["Budget"]
    total_project_cost = budget_cf.sum()
    debt_portion = total_project_cost * debt_to_equity
    equity_portion = total_project_cost * (1 - debt_to_equity)

    # Prepare DataFrame for calculations
    df = pd.DataFrame(budget_cf)
    df = df.reindex(
        pd.period_range(df.index.min(), df.index.max() + 10, freq="M"), fill_value=0
    )
    df.rename(columns={"Budget": "Total Costs Before Financing"}, inplace=True)

    # Calculate cumulative costs to decide draws
    df["Cumulative Costs"] = df["Total Costs Before Financing"].cumsum()

    # Equity and debt draw calculations
    df["Equity Draw"] = np.minimum(
        df["Total Costs Before Financing"],
        np.maximum(equity_portion - df["Cumulative Costs"].shift(1, fill_value=0), 0),
    )

    # Applying financing fee only once when crossing the threshold from equity to debt
    df["Financing Fees"] = np.where(
        (df["Cumulative Costs"].shift(1, fill_value=0) < equity_portion)
        & (
            df["Cumulative Costs"] >= equity_portion
        ),  # if crossing the threshold from equity to debt
        debt_portion * financing_fee_rate,  # calculate the financing fees
        0,  # otherwise, no fees
    )

    df["Debt Draw"] = (
        df["Total Costs Before Financing"] - df["Equity Draw"] + df["Financing Fees"]
    )

    # Calculate cumulative debt and interest
    df["Cumulative Debt Drawn"] = df["Debt Draw"].cumsum()
    df["Interest Reserve"] = 0
    cumulative_interest = 0

    # Update debt and interest calculation with recursion for accurate compounding
    for i in range(len(df)):
        if i > 0:
            previous_balance = (
                df.loc[df.index[i - 1], "Cumulative Debt Drawn"] + cumulative_interest
            )
            interest_for_this_month = previous_balance * (financing_interest_rate / 12)
            cumulative_interest += interest_for_this_month
        else:
            interest_for_this_month = 0

        df.at[df.index[i], "Interest Reserve"] = interest_for_this_month
        df.at[df.index[i], "Cumulative Debt Drawn"] += interest_for_this_month

    return df


debt = compute_construction_financing(concat_pt, 0.65, 0.25)

# plot columns that make sense together
# debt[['Total Costs Before Financing', 'Equity Draw', 'Debt Draw', 'Interest Reserve']].plot(kind="bar", stacked=True)
# make total costs negative
debt["Total Costs Before Financing"] *= -1
debt
# plot again
debt[
    ["Total Costs Before Financing", "Equity Draw", "Debt Draw", "Interest Reserve"]
].plot(kind="bar", stacked=True)


# %%

# concat_df = pd.concat([revenue.revenue_df, revenue.structural_losses_df, expense.expense_df])
# concat_pt = concat_df.pivot_table(values=0, index=concat_df.index, columns=['Category', 'Subcategory', 'Use', 'Name'], aggfunc='sum').fillna(0)
# # concat_pt.resample("Y").sum().plot(kind="bar", stacked=True)
# # concat_pt[:20].plot(kind="bar", stacked=True)

# # slice revenue and sum by subcategory
# concat_pt.loc[:, ("Revenue", slice(None), slice(None), slice(None))].groupby(level=1, axis=1).sum()
# # slice lease revenue and sum by period
# concat_pt.loc[:, ("Revenue", "Lease", slice(None), slice(None))].groupby(level=0, axis=1).sum()
# # slice lease revenue and sum by period and rename columns to Hello
# concat_pt.loc[:, ("Revenue", "Lease", slice(None), slice(None))].groupby(level=0, axis=1).sum().rename(columns=lambda x: f"Hello {x}")
# # slice lease and sum by use
# concat_pt.loc[:, ("Revenue", "Lease", slice(None), slice(None))].groupby(level=2, axis=1).sum()
# # slice lease losses and sum by use
# concat_pt.loc[:, ("Losses", "Lease", slice(None), slice(None))].groupby(level=2, axis=1).sum()

# # slice sales and sum by use
# concat_pt.loc[:, ("Revenue", "Sale", slice(None), slice(None))].groupby(level=2, axis=1).sum()

# # slide expenses and sum by use
# concat_pt.loc[:, ("Expense", "OpEx", slice(None), slice(None))].groupby(level=2, axis=1).sum()

# # check if 'Lease' is a column in the multi-index
# any('Lease' in column for column in concat_pt.columns)

# # get the min index in the multi-index df where the subcategory is "Lease"
# concat_pt.loc[:, ("Revenue", "Lease", slice(None), slice(None))].index.min()

# # how can i check if a specific column "Sale" exists in the pivot table?
# any('Sale' in column for column in concat_pt.columns)

# %%

# PROJECT
project_start_date = "2020-01"

# BUDGET
land = BudgetItem(
    name="Land",
    subcategory="Land",
    cost_total=4_000_000.0,
    periods_until_start=0,
    active_duration=1,
    draw_sched_kind="uniform",
    draw_sched_sigma=None,
)
constr_costs = BudgetItem(
    name="Construction Costs",
    subcategory="Hard Costs",
    cost_total=12_000_000.0,
    periods_until_start=6,
    active_duration=18,
    draw_sched_kind="s-curve",
    draw_sched_sigma=4.0,
)
demo_costs = BudgetItem(
    name="Demolition",
    subcategory="Hard Costs",
    cost_total=550_000.0,
    periods_until_start=3,
    active_duration=3,
    draw_sched_kind="s-curve",
    draw_sched_sigma=1.0,
)
soft_costs = BudgetItem.from_reference_items(
    name="Total Soft Costs",
    subcategory="Soft Costs",
    reference_budget_items=[constr_costs, demo_costs],
    reference_kind="passthrough",
    reference_percentage=0.2,
    periods_until_start=1,
    active_duration=31,
    draw_sched_kind="uniform",
    draw_sched_sigma=None,
)
budget = Budget(budget_items=[land, constr_costs, demo_costs, soft_costs])

# REVENUES
apt_rental = RentalRevenueItem(
    name="Residential Apartments",
    subcategory="Lease",
    periods_until_start=30,
    program=Program(
        name="Residential Apartments",
        use="Residential",
        gross_area=1500.0,
        net_area=1000.0,
        unit_count=32,
    ),
    revenue_multiplicand="Whole Unit",
    revenue_multiplier=3_500.0,
    revenue_growth_rate=0.05,
)

revenue = Revenue(
    revenue_items=[
        apt_rental,
    ]
)

# EXPENSES
management_fee = ExpenseFactorItem(
    name="Management Fee",
    subcategory="OpEx",
    program_use="Residential",
    expense_factor=0.02,
    revenue=revenue,
)
repairs_maintenance = ExpenseCostItem(
    name="Repairs and Maintenance",
    subcategory="OpEx",
    program_use="Residential",
    initial_annual_cost=5000.0,
    expense_growth_rate=0.03,
    revenue=revenue,
)
capital_improvements = ExpenseFactorItem(
    name="Capital Improvements",
    subcategory="CapEx",
    program_use="Residential",
    expense_factor=0.03,
    revenue=revenue,
)

expenses = Expense(
    expense_items=[
        management_fee,
        repairs_maintenance,
        capital_improvements,
    ]
)


my_project = Project(
    name="Le Jules Verne",
    project_start_date=project_start_date,
    debt_to_equity=0.6,
    budget=budget,
    revenue=revenue,
    expenses=expenses,
    construction_financing=ConstructionFinancing(
        interest_rate=0.095,
        fee_rate=0.00,
    ),
    permanent_financing=PermanentFinancing(
        interest_rate=0.07,
        fee_rate=0.01,
        ltv_ratio=0.5,
        amortization=30,
    ),
    cap_rates=[
        CapRates(
            name="Residential Cap Rates",
            program_use="Residential",
            development_cap_rate=0.05,
            refinance_cap_rate=0.05,
            sale_cap_rate=0.05,
        ),
    ],
    stabilization_year=2,
    hold_duration=7,
)
# time the next call
my_project.unlevered_cash_flow
# %timeit my_project.unlevered_cash_flow

partners = [
    Partner(name="GP", kind="GP", share=0.1),
    Partner(name="LP1", kind="LP", share=0.45),
    Partner(name="LP2", kind="LP", share=0.45),
]
tiers = [
    WaterfallTier(tier_hurdle_rate=0.1, metric="IRR", promote_rate=0.2),
    WaterfallTier(tier_hurdle_rate=0.125, metric="IRR", promote_rate=0.35),
]
promote = WaterfallPromote(
    kind="waterfall", pref_hurdle_rate=0.08, tiers=tiers, final_promote_rate=0.5
)
deal = Deal(project=my_project, partners=partners, promote=promote)


# %%
# plot a gantt chart of the project timelines (development, stabilization, hold)
phases = {
    "Hold": (my_project.hold_timeline.min(), my_project.hold_timeline.max()),
    "Stabilization": (
        my_project.stabilization_timeline.min(),
        my_project.stabilization_timeline.max(),
    ),
    "Development": (
        my_project.development_timeline.min(),
        my_project.development_timeline.max(),
    ),
}


# Convert start and end months to numerical values
def month_to_number(month):
    return (month - my_project.project_timeline.min()).n + 1


# Create list of tuples for plotting
time_blocks = []
colors = ["tab:blue", "tab:orange", "tab:green"]
for i, (phase, (start, end)) in enumerate(phases.items()):
    start_num = month_to_number(start)
    end_num = month_to_number(end)
    time_blocks.append((phase, [(start_num, end_num - start_num, colors[i])]))

# Plotting
fig, ax = plt.subplots(figsize=(10, 2))
for i, (phase, periods) in enumerate(time_blocks):
    for start, duration, color in periods:
        ax.broken_barh(
            [(start, duration)], (i - 0.3, 0.8), facecolors=(color), edgecolor="none"
        )  # Removed edgecolor
ax.set_yticks(range(len(time_blocks)))
ax.set_yticklabels([phase for phase, _ in time_blocks])
ax.set_xlabel("Months since Start of 2024")
ax.set_title("Project Gantt Chart")
plt.show()


# PLOT COSTS
my_project.construction_before_financing_cf.plot(
    kind="bar", stacked=True, title="Development Uses Cash Flow"
)

# PLOT CUMULATIVE COSTS
my_project.construction_before_financing_cf.cumsum().plot(
    kind="bar", stacked=True, title="Development Cumulative Uses Cash Flow"
)


# PLOT CONSTRUCTION FINANCING
my_project.construction_financing_cf[["Equity Draw", "Debt Draw", "Interest Reserve"]][
    0:32
].plot(kind="bar", stacked=True, title="Development Sources Cash Flow")
plt.show()  # Add this line to display the plot

# CONSTRUCTION SOURCES PIE CHART
my_project.construction_financing_cf[["Equity Draw", "Debt Draw", "Interest Reserve"]][
    0:32
].sum().plot(kind="pie", title="Development Sources")
plt.show()  # Add this line to display the plot


# my_project._revenue_table[0:32].plot(kind="bar", stacked=True, title="Revenue")

# # my_project.unlevered_cash_flow.resample("Y").sum().T
my_project.unlevered_cash_flow.resample("Y").sum().plot(
    kind="bar", stacked=True, title="Unlevered Annual Cash Flow"
)

# running xirr on unlevered cash flow
foo = my_project.unlevered_cash_flow
foo.set_index(foo.index.to_timestamp(), inplace=True)
f"IRR: {xirr(foo['Unlevered Cash Flow'])*100:.2f}%"

# my_project.levered_cash_flow.resample("Y").sum().T
my_project.levered_cash_flow.resample("Y").sum().plot(
    kind="bar", stacked=True, title="Levered Annual Cash Flow", color="purple"
)

# running xirr on levered cash flow
bar = my_project.levered_cash_flow
bar.set_index(bar.index.to_timestamp(), inplace=True)
f"IRR: {xirr(bar['Levered Cash Flow'])*100:.2f}%"

# my_project.dscr.plot(kind="bar", title="Debt Service Coverage Ratio")

# my_project.dscr
# my_project.dscr.loc[my_project.stabilization_date:my_project.stabilization_date+11]


# %%
# using pyobsplot
op = Obsplot()
# data = my_project.construction_before_financing_cf.loc[:, ("Budget", slice(None), slice(None), slice(None))].groupby(level=2, axis=1).sum()

# # long format data!
# data = my_project.budget.budget_df
# data.index.rename("Date", inplace=True)
# data.set_index(data.index.to_timestamp(), inplace=True)
# # rename column 0 to Cost
# data.rename(columns={0: "Cost"}, inplace=True)
# # op(Plot.auto(my_project._budget_table, {"x": "Date"}))
# Plot.plot({
#     "color": {"legend": True},
#     "marks": [
#         # bar chart of cumulative costs
#         Plot.barY(data, {"x": "Date", "y": "Cost", "fill": "Subcategory"}),
#         Plot.ruleY([0]),
#     ]
# })

# my_project.construction_before_financing_cf.stack(level=1).reset_index(1).rename(columns={''})


# a function to take a multi-index dataframe and return a long format dataframe
def reshape_dataframe(df):
    """Reshape a multi-index dataframe to long format"""
    # FIXME: add param for column names/mapping
    # Stack the inner-most level of the column index (level=-1 will stack the last level)
    df_long = df.stack(level=[0, 1, 2])
    # Reset the index to turn them into columns
    df_long = df_long.reset_index()
    # Rename columns to the desired names
    # TODO (in case of revenue, there is a Use column to be added)
    df_long.columns = ["Date", "Category", "Subcategory", "Name", "Amount"]
    # Set the Date column as the index and convert to datetime
    df_long.set_index(df_long["Date"], inplace=True)
    df_long.drop(columns=["Date"], inplace=True)
    df_long.set_index(df_long.index.to_timestamp(), inplace=True)
    # Return the reshaped dataframe
    return df_long


# Reshape the construction before financing cash flow
construction_before_financing_cf_long = reshape_dataframe(
    my_project.construction_before_financing_cf
)
construction_before_financing_cf_long_cumsum = reshape_dataframe(
    my_project.construction_before_financing_cf.cumsum()
)
construction_before_financing_cf_long_annual = reshape_dataframe(
    my_project.construction_before_financing_cf.resample("Y").sum()
)

# long format data!
data = construction_before_financing_cf_long_cumsum
# set index to Date column and remove the column
# data.set_index(data['Date'], inplace=True)
# data.drop(columns=['Date'], inplace=True)
# data.set_index(data.index.to_timestamp(), inplace=True)
Plot.plot(
    {
        # "grid": True,
        # "margin": 10,
        "x": {
            # "insetLeft": 12
        },
        "y": {
            "transform": js("(d) => d / 1000000"),
        },
        "color": {"legend": True},
        "marks": [
            # bar chart of cumulative costs
            Plot.axisX({"ticks": "3 months"}),
            Plot.axisY(
                {
                    "label": "Amount ($m)",
                    # "dx": 12,
                }
            ),
            Plot.barY(
                data,
                {
                    "x": "Date",
                    "y": "Amount",
                    "fill": "Subcategory",
                    "tip": True,
                },
            ),
            Plot.ruleY([0]),  # add a baseline at 0
        ],
    }
)
