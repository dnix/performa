from typing import List, Literal, Optional

import pandas as pd

from ..utils._model import Model
from ..utils._types import FloatBetween0And1, PositiveFloat
from ._line_item import LineItem


class ExpenseItem(LineItem):
    """
    Class for a generic operational expense line item (rental use case).
    This model is augmented to align with Argus Enterprise/Valuation DCF expense inputs.

    Attributes:
        expense_kind: Identifies the expense as a "Cost" type.
        initial_annual_cost: The base annual expense amount.
        expense_growth_rate: Annual growth rate for the expense.
        is_recoverable: Flag indicating if the expense is recoverable (passed through to tenants).
    """

    expense_kind: Literal["Cost"] = "Cost"
    initial_annual_cost: PositiveFloat
    expense_growth_rate: FloatBetween0And1 = 0.03  # TODO: consider using GrowthRates
    is_recoverable: bool = True
    parent_item: Optional[str] = None  # For grouping


class OpexItem(ExpenseItem):
    """Operating expenses like utilities"""

    ...


class CapexItem(ExpenseItem):
    """Capital expenditures with timeline"""

    timeline: pd.Series  # this is a pandas Series of the timeline with length equal to the active duration of the item


class OperatingExpenses(Model):
    """
    Collection of property operating expenses.

    Attributes:
        expense_items: List of operational expense items.
    """

    expense_items: List[ExpenseItem]

    @property
    def total_annual_expenses(self) -> PositiveFloat:
        """Calculate total annual base expenses"""
        return sum(item.initial_annual_cost for item in self.expense_items)

    @property
    def recoverable_expenses(self) -> List[ExpenseItem]:
        """Get list of recoverable expenses"""
        return [item for item in self.expense_items if item.is_recoverable]


class CapitalExpenses(Model):
    """
    Collection of capital improvements/investments.

    Attributes:
        capex_items: List of capital expenditures
    """

    expense_items: List[CapexItem]

    @property
    def total_capex(self) -> PositiveFloat:
        """Calculate total capital expenditure amount"""
        return sum(item.amount for item in self.capex_items)
