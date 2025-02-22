from typing import List, Optional

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
    initial_annual_cost: PositiveFloat
    growth_rate: float  # or a GrowthRates instance (see project types)
    # FIXME: where is the occupancy rate going to be defined? in orchestration layer...
    variability: Optional[Variability] = None  # default is not variable
    is_recoverable: bool = True

    @property
    def is_variable(self) -> bool:
        """Check if the expense is variable"""
        return self.variability is not None and self.variability.percent_variable is not None


class CapExItem(ExpenseItem):
    """Capital expenditures with timeline"""
    expense_kind: ExpenseSubcategoryEnum = "CapEx"
    # FIXME: pass a dict of date:amount or a pandas Series with index
    # TODO: factory for dict of date:amt to pandas Series


class OperatingExpenses(Model):
    """
    Collection of property operating expenses.

    Attributes:
        expense_items: List of operational expense items.
    """

    expense_items: List[OpExItem]

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

    expense_items: List[CapExItem]

    @property
    def total_capex(self) -> PositiveFloat:
        """Calculate total capital expenditure amount"""
        return sum(item.amount for item in self.capex_items)

class ExpenseCollection(Model):
    """
    Collection of property operating expenses and capital expenditures.
    """

    operating_expenses: OperatingExpenses
    capital_expenses: CapitalExpenses
