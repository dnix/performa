from typing import Callable, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from ..core._cash_flow import CashFlowModel
from ..core._enums import ExpenseSubcategoryEnum
from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat


class ExpenseItem(CashFlowModel):
    """Base class for all expense items."""
    category: str = "Expense"  # TODO: enum?
    subcategory: ExpenseSubcategoryEnum  # NOTE: instead of expense_kind
    parent_item: Optional[str] = None  # For optional grouping
    # TODO: rename parent_item to group?


class OpExItem(ExpenseItem):
    """Operating expenses like utilities"""
    subcategory: ExpenseSubcategoryEnum = "OpEx"
    growth_rate: Optional[float] = None  # annual growth rate (e.g., 0.02 for 2% growth)
    # TODO: future support lookup of GrowthRates instance
    # TODO: maybe growth rate is passed by orchestration layer too?
    # Occupancy rate will be provided by the orchestration layer via compute_cf parameters.
    variable_ratio: Optional[FloatBetween0And1] = None  # Default is not variable.
    recoverable_ratio: Optional[FloatBetween0And1] = 1.0  # Default is 100% recoverable.
    # FIXME: confirm we want 100% recoverable by default

    @property
    def is_variable(self) -> bool:
        """Check if the expense is variable."""
        return self.variable_ratio is not None

    @property
    def is_recoverable(self) -> bool:
        """Check if the expense is recoverable."""
        return self.recoverable_ratio is not None

    def compute_cf(
        self,
        occupancy_rate: Optional[float] = None,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> pd.Series:
        """
        Compute the cash flow for the operating expense with optional occupancy and growth adjustments.
        
        The base cash flow is computed using the parent's logic where `value`
        represents the annual cost.
        
        - If a growth rate is provided, growth is applied to the cash flow series starting from the first value.
          For each subsequent month, the value is multiplied by:
              (1 + growth_rate/12)^(months_since_start)

        - If an occupancy rate is provided and the expense is variable, the cash flow is adjusted as:
              adjusted_cost = value * [(1 - p) + p * occupancy_rate]
          where p is the fraction of the expense that is variable.
        """
        # Compute the base cash flow using the parent method.
        base_flow = super().compute_cf(lookup_fn)
        
        # Apply growth rate adjustment if provided.
        if self.growth_rate is not None:
            months = np.arange(len(base_flow))
            growth_factors = np.power(1 + (self.growth_rate / 12), months)
            base_flow = base_flow * growth_factors

        # Apply occupancy adjustment if applicable.
        if occupancy_rate is not None and self.is_variable:
            variable_ratio = self.variable_ratio  # e.g., 0.3 for 30% variability
            adjustment_ratio = (1 - variable_ratio) + variable_ratio * occupancy_rate
            base_flow = base_flow * adjustment_ratio
        
        return base_flow


class CapExItem(ExpenseItem):
    """Capital expenditures with timeline"""
    subcategory: ExpenseSubcategoryEnum = "CapEx"

    value: Union[pd.Series, Dict, List]  # no scalar values allowed


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


class Expenses(Model):
    """
    Collection of property operating expenses and capital expenditures.
    """
    operating_expenses: OperatingExpenses
    capital_expenses: CapitalExpenses
