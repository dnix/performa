from typing import Callable, List, Optional, Union

import pandas as pd

from ..core._cash_flow import CashFlowModel
from ..core._enums import ExpenseSubcategoryEnum
from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat


class ExpenseItem(CashFlowModel):
    """Base class for all expense items."""
    expense_kind: ExpenseSubcategoryEnum
    parent_item: Optional[str] = None  # For optional grouping


class Variability(Model):
    """
    Represents the variability of an expense item.
    """
    percent_variable: Optional[FloatBetween0And1] = None
    basis_value: Optional[PositiveFloat] = None  # value of the basis for variability (e.g., occupancy rate)


class OpExItem(ExpenseItem):
    """Operating expenses like utilities"""

    expense_kind: ExpenseSubcategoryEnum = "OpEx"
    growth_rate: float  # or a GrowthRates instance (see project types)
    # Occupancy rate will be provided by the orchestration layer via compute_cash_flow parameters.
    variability: Optional[Variability] = None  # Default is not variable.
    is_recoverable: bool = True

    @property
    def is_variable(self) -> bool:
        """Check if the expense is variable."""
        return self.variability is not None and self.variability.percent_variable is not None

    def compute_cf(
        self,
        occupancy_rate: Optional[float] = None,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> pd.Series:
        """
        Compute the cash flow for the operating expense with an optional occupancy adjustment.
        
        The base cash flow is computed using the parent's logic where `value`
        represents the annual cost. If an occupancy rate is provided and the expense is variable,
        the cash flow is adjusted as:

            adjusted_cost = value * [(1 - p) + p * occupancy_rate]

        where p is the fraction of the expense that is variable.
        """
        # Compute the base cash flow using the parent method.
        base_flow = super().compute_cf(lookup_fn)
        
        # If occupancy context is provided and the expense is variable, adjust the flow.
        if occupancy_rate is not None and self.is_variable:
            percent_variable = self.variability.percent_variable  # e.g., 0.3 for 30% variability
            adjustment_ratio = (1 - percent_variable) + percent_variable * occupancy_rate
            return base_flow * adjustment_ratio
        
        return base_flow


class CapExItem(ExpenseItem):
    """Capital expenditures with timeline"""
    expense_kind: ExpenseSubcategoryEnum = "CapEx"
    # TODO: Future improvements: add logic to convert a dict of date:amount values or a pandas Series into a proper cash flow series.


class OperatingExpenses(Model):
    """
    Collection of property operating expenses.
    
    Attributes:
        expense_items: List of operational expense items.
    """
    expense_items: List[OpExItem]

    @property
    def total_annual_expenses(self) -> PositiveFloat:
        """
        Calculate total annual base expenses by summing the value field of each expense item.
        """
        return sum(item.value for item in self.expense_items)

    @property
    def recoverable_expenses(self) -> List[ExpenseItem]:
        """
        Get list of recoverable expenses.
        """
        return [item for item in self.expense_items if item.is_recoverable]


class CapitalExpenses(Model):
    """
    Collection of capital improvements/investments.
    
    Attributes:
        expense_items: List of capital expenditure items.
    """
    expense_items: List[CapExItem]

    @property
    def total_capex(self) -> PositiveFloat:
        """
        Calculate the total capital expenditure amount by summing the value field of each capex item.
        """
        return sum(item.value for item in self.expense_items)


class ExpenseCollection(Model):
    """
    Collection of property operating expenses and capital expenditures.
    """
    operating_expenses: OperatingExpenses
    capital_expenses: CapitalExpenses
