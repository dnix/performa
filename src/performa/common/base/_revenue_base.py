from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

import pandas as pd

from ..primitives._cash_flow import CashFlowModel
from ..primitives._enums import RevenueSubcategoryEnum
from ..primitives._growth_rates import GrowthRate
from ..primitives._types import FloatBetween0And1

logger = logging.getLogger(__name__)


class MiscIncomeBase(CashFlowModel):
    """
    Base class for miscellaneous income items.
    """

    category: str = "Revenue"
    subcategory: RevenueSubcategoryEnum = RevenueSubcategoryEnum.MISC
    variable_ratio: Optional[FloatBetween0And1] = None
    growth_rate: Optional["GrowthRate"] = None

    @property
    def is_variable(self) -> bool:
        return self.variable_ratio is not None

    def compute_cf(self, **kwargs: Any) -> Union[pd.Series, Dict[str, pd.Series]]:
        """
        Base miscellaneous income calculation. Subclasses should override this.
        """
        if isinstance(self.value, (int, float)):
            return pd.Series(self.value, index=self.timeline.period_index)
        elif isinstance(self.value, pd.Series):
            return self.value.reindex(self.timeline.period_index, fill_value=0.0)
        raise NotImplementedError("Base compute_cf requires override for complex value types.") 