# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

import pandas as pd

from ..primitives.cash_flow import CashFlowModel
from ..primitives.enums import RevenueSubcategoryEnum
from ..primitives.growth_rates import PercentageGrowthRate
from ..primitives.types import FloatBetween0And1

logger = logging.getLogger(__name__)


class MiscIncomeBase(CashFlowModel):
    """
    Base class for miscellaneous income items.
    """

    category: str = "Revenue"
    subcategory: RevenueSubcategoryEnum = RevenueSubcategoryEnum.MISC
    variable_ratio: Optional[FloatBetween0And1] = None
    growth_rate: Optional["PercentageGrowthRate"] = None

    @property
    def is_variable(self) -> bool:
        return self.variable_ratio is not None

    def compute_cf(self, **kwargs: Any) -> Union[pd.Series, Dict[str, pd.Series]]:
        """
        Base miscellaneous income calculation. Subclasses should override this.
        """
        if isinstance(self.value, (int, float)):
            monthly_value = self.value
            if self.frequency == "annual":
                monthly_value /= 12.0
            return pd.Series(monthly_value, index=self.timeline.period_index)
        elif isinstance(self.value, pd.Series):
            return self.value.reindex(self.timeline.period_index, fill_value=0.0)
        raise NotImplementedError("Base compute_cf requires override for complex value types.") 