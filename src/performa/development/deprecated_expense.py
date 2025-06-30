from abc import ABC, abstractmethod
from typing import Annotated, Literal, Union

import numpy as np
import pandas as pd
from pydantic import Field

from ..core._enums import (
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
)
from ..core._types import FloatBetween0And1, PositiveFloat
from ._enums import (
    ExpenseKindEnum,
    ProgramUseEnum,
)
from ._model import Model
from ._revenue import Revenue

# %%
###########################
######### EXPENSE #########
###########################


# class ExpenseItem(CashFlowModel):  # NOTE: should this extend CashFlowModel instead of Model?
class ExpenseItem(Model, ABC):
    """
    Abstract base class for a generic expense line item (rental use case) per program use.
    This class defines the common structure and interface for all expense items.
    """

    # GENERAL
    name: str  # "Property Management Fee"
    category: CashFlowCategoryEnum = "Expense"
    subcategory: ExpenseSubcategoryEnum  # OpEx, CapEx

    # PROGRAM
    program_use: (
        ProgramUseEnum  # use of the program (residential, office, retail, etc.)
    )

    # EXPENSE
    expense_kind: ExpenseKindEnum

    # REVENUE
    revenue: Revenue  # all revenue rolled together

    @property
    def revenue_df(self) -> pd.DataFrame:
        """
        Returns the revenue DataFrame from the associated Revenue object.
        This is used to align expense calculations with revenue periods.
        """
        return self.revenue.revenue_df

    @property
    @abstractmethod
    def expense_df(self) -> pd.DataFrame:
        """
        Abstract method to construct cash flow for expense with categories and subcategories.
        This method must be implemented by all concrete subclasses.
        """
        pass


class ExpenseCostItem(ExpenseItem):
    """
    Class for a generic operational expense line item (rental use case).
    This class represents expenses that are based on a fixed cost that grows over time.

    Examples:
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
    expense_kind: Literal["Cost"] = "Cost"
    # COST
    initial_annual_cost: PositiveFloat  # total expense per year
    expense_growth_rate: FloatBetween0And1 = 0.03  # expense growth, simple annual

    @property
    def expense_df(self) -> pd.DataFrame:
        """
        Construct cash flow for expense costs with categories and subcategories.
        This method calculates the expense over time, applying the growth rate annually.
        """
        # Filter revenue data to match this expense's program use
        mask = (
            (self.revenue_df["Category"] == "Revenue")
            & (self.revenue_df["Subcategory"] == "Lease")
            & (self.revenue_df["Use"] == self.program_use)
        )
        # Create a timeline matching the revenue periods
        new_timeline = pd.period_range(
            self.revenue_df.loc[mask].index.min(),
            self.revenue_df.loc[mask].index.max(),
            freq="M",
        )
        # Calculate growth factors (applied annually)
        growth_factors = np.ones(len(new_timeline))
        growth_factors[12::12] = 1 + self.expense_growth_rate
        cumulative_growth = np.cumprod(growth_factors)
        # Calculate monthly expenses with growth applied
        monthly_expenses = self.initial_annual_cost / 12 * cumulative_growth
        # Create DataFrame with calculated expenses
        df = pd.DataFrame(monthly_expenses, index=new_timeline, columns=[0])
        # Add metadata columns
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program_use  # "Residential", "Office", "Retail", etc.
        return df


class ExpenseFactorItem(ExpenseItem):
    """
    Class for a generic expense factor (rental use case), calculated as a percentage of gross revenue.
    This class represents expenses that are directly proportional to revenue.

    Examples:
    ### OpEx
    - Management Fee @ X% of EGR (Effective Gross Revenue)

    ### CapEx
    - Capital account @ X% of EGR
    """

    # GENERAL
    expense_kind: Literal["Factor"] = "Factor"
    # FACTOR
    program_use: ProgramUseEnum  # residential, office, retail, etc.

    expense_factor: FloatBetween0And1  # expense factor as a percentage of *revenue*

    @property
    def expense_df(self) -> pd.DataFrame:
        """
        Construct cash flow for expense factors with categories and subcategories.
        This method calculates the expense as a percentage of the corresponding revenue.
        """
        # Filter revenue data to match this expense's program use
        mask = (
            (self.revenue_df["Category"] == "Revenue")
            & (self.revenue_df["Subcategory"] == "Lease")
            & (self.revenue_df["Use"] == self.program_use)
        )
        # Create a timeline matching the revenue periods
        new_timeline = pd.period_range(
            self.revenue_df.loc[mask].index.min(),
            self.revenue_df.loc[mask].index.max(),
            freq="M",
        )
        # Calculate expense as a factor of revenue
        cf = self.revenue_df.loc[mask][0] * self.expense_factor
        # Create DataFrame with calculated expenses
        df = pd.DataFrame(cf.values, index=new_timeline, columns=[0])
        # Add metadata columns
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program_use
        return df


# Union type for any kind of expense item
AnyExpenseItem = Union[ExpenseCostItem, ExpenseFactorItem]


class Expense(Model):
    """
    Wrapper class for expense items.
    This class aggregates multiple expense items and provides methods to access the combined expense data.
    """

    # EXPENSES ITEMS
    expense_items: list[
        Annotated[AnyExpenseItem, Field(..., discriminator="expense_kind")]
    ]

    @property
    def expense_df(self) -> pd.DataFrame:
        """
        Aggregates all expense items into a single DataFrame.

        Returns:
            pd.DataFrame: Combined DataFrame of all expense items.

        """
        return pd.concat([item.expense_df for item in self.expense_items])
