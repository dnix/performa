from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import pandas as pd

from ..primitives.cash_flow import CashFlowModel
from ..primitives.enums import ExpenseSubcategoryEnum, UnitOfMeasureEnum
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext


logger = logging.getLogger(__name__)


class ExpenseItemBase(CashFlowModel):
    """
    Base abstract class for all expense items.
    """

    category: str = "Expense"
    subcategory: ExpenseSubcategoryEnum
    group: Optional[str] = None


class OpExItemBase(ExpenseItemBase):
    """
    Base class for operating expenses.

    This class inherits the powerful `compute_cf` method from `CashFlowModel`,
    which automatically handles value calculation based on `unit_of_measure`,
    dependency resolution via `reference`, and growth rate application.
    Subclasses like `OfficeOpExItem` can then call `super().compute_cf()` and
    apply their own specific adjustments (e.g., for occupancy).
    """

    subcategory: ExpenseSubcategoryEnum = ExpenseSubcategoryEnum.OPEX
    variable_ratio: Optional[FloatBetween0And1] = None
    recoverable_ratio: Optional[FloatBetween0And1] = 0.0

    @property
    def is_variable(self) -> bool:
        return self.variable_ratio is not None

    @property
    def is_recoverable(self) -> bool:
        return self.recoverable_ratio is not None and self.recoverable_ratio > 0


class CapExItemBase(ExpenseItemBase):
    """Base class for capital expenditures."""

    subcategory: ExpenseSubcategoryEnum = ExpenseSubcategoryEnum.CAPEX

    def compute_cf(self, context: AnalysisContext) -> pd.Series:
        """
        Computes the cash flow for a capital expenditure item.

        This method overrides the base `CashFlowModel.compute_cf` to explicitly
        **exclude** the application of growth rates. Capital expenditures are
        typically budgeted as discrete amounts and are not expected to grow
        in the same compounding manner as operational expenses.
        """
        base_value = self.value
        if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
            nra = context.property_data.net_rentable_area
            if nra > 0:
                base_value = self.value * nra
            else:
                base_value = 0.0
        elif self.unit_of_measure == UnitOfMeasureEnum.BY_PERCENT and self.reference:
            dependency_cf = context.resolved_lookups.get(self.reference)
            if dependency_cf is None:
                raise ValueError(f"Unresolved dependency for '{self.name}': {self.reference}")
            base_value = dependency_cf * self.value
        
        monthly_value = self._convert_frequency(base_value)
        base_series = self._cast_to_flow(monthly_value)
        return base_series 