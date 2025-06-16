from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import pandas as pd

from ..primitives.cash_flow import CashFlowModel
from ..primitives.enums import ExpenseSubcategoryEnum
from ..primitives.growth_rates import GrowthRate
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1

logger = logging.getLogger(__name__)


class ExpenseItemBase(CashFlowModel):
    """
    Base abstract class for all expense items.
    """

    category: str = "Expense"
    subcategory: ExpenseSubcategoryEnum
    group: Optional[str] = None


class OpExItemBase(ExpenseItemBase):
    """Base class for operating expenses."""

    subcategory: ExpenseSubcategoryEnum = ExpenseSubcategoryEnum.OPEX
    growth_rate: Optional[GrowthRate] = None
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
    value: Union[pd.Series, Dict, List]  # No scalar values allowed for CapEx base 
