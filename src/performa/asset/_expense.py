from datetime import date
from typing import List, Optional

from ..utils._model import Model
from ..utils._types import PositiveFloat
from ._line_item import LineItem


class ExpenseItem(LineItem):
    """Base class for expenses"""

    is_recoverable: bool = False
    parent_item: Optional[str] = None  # For grouping


class OpexItem(ExpenseItem):
    """Operating expenses like utilities"""

    ...


class CapexItem(ExpenseItem):
    """Capital expenditures with timeline"""

    # TODO: handle this as a pandas Series? or date and value and cast to pandas?

    timeline: dict[date, PositiveFloat]  # Detailed spending schedule


class OperatingExpenses(Model):
    """
    Collection of property operating expenses.

    Attributes:
        expense_items: List of operating expenses
    """

    expense_items: List[OpexItem]

    @property
    def total_annual_expenses(self) -> PositiveFloat:
        """Calculate total annual base expenses"""
        return sum(item.amount for item in self.expense_items)

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
