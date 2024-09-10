from typing import Literal, Union, Annotated

from pydantic import Field

import numpy as np
import pandas as pd

from .model import Model
from .revenue import Revenue
from ..utils.types import PositiveFloat, FloatBetween0And1



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
    program_use: Literal["Residential", "Affordable Residential", "Office", "Retail", "Amenity", "Other"]

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
            (self.revenue_df['Category'] == 'Revenue') &
            (self.revenue_df['Subcategory'] == 'Lease') &
            (self.revenue_df['Use'] == self.program_use)
        )
        new_timeline = pd.period_range(
            self.revenue_df.loc[mask].index.min(),
            self.revenue_df.loc[mask].index.max(),
            freq="M"
        )
        growth_factors = np.ones(mask.sum())
        growth_factors[12::12] = 1 + self.expense_growth_rate  # Apply growth factor at the beginning of each year after the first year
        cumulative_growth = np.cumprod(growth_factors)
        monthly_expenses = self.initial_annual_cost / 12 * cumulative_growth
        cf = pd.Series(
            monthly_expenses,
            index=new_timeline
        )
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df['Name'] = self.name
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
    program_use: Literal["Residential", "Affordable Residential", "Office", "Retail", "Amenity", "Other"]
    expense_factor: FloatBetween0And1  # expense factor as a percentage of *revenue*

    @property
    def expense_df(self) -> pd.DataFrame:
        """Construct cash flow for expense factors with categories and subcategories"""
        mask = (
            (self.revenue_df['Category'] == 'Revenue') &
            (self.revenue_df['Subcategory'] == 'Lease') &
            (self.revenue_df['Use'] == self.program_use)
        )
        new_timeline = pd.period_range(
            self.revenue_df.loc[mask].index.min(),
            self.revenue_df.loc[mask].index.max(),
            freq="M"
        )
        cf = pd.Series(
            self.revenue_df.loc[mask][0] * self.expense_factor, 
            index=new_timeline
        )
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df['Name'] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program_use
        return df


AnyExpenseItem = Union[ExpenseCostItem, ExpenseFactorItem]



class Expense(Model):
    """Wrapper class for expense items"""
    # EXPENSES ITEMS
    expense_items: list[Annotated[AnyExpenseItem, Field(..., discriminator='expense_kind')]]

    # need to disagregate by opex/capex and program use

    # FIXME: aggregate all expense dfs into a master df

    # TODO: summary statistics on expenses (opex, capex)

    @property
    def expense_df(self) -> pd.DataFrame:
        return pd.concat([item.expense_df for item in self.expense_items])
        # TODO: just use a list for performance? (pd.concat copies data...)

