from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Union
from uuid import UUID

import pandas as pd

from ...common.base import CapExItemBase, OpExItemBase
from ...common.primitives import GrowthRate, Model, Timeline, UnitOfMeasureEnum

logger = logging.getLogger(__name__)

class OfficeOpExItem(OpExItemBase):
    """
    Office-specific operating expense.
    """

    def compute_cf(
        self,
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        **kwargs,
    ) -> pd.Series:
        """
        Compute office operating expense cash flow.
        """
        # Let the base class handle the initial calculation including frequency conversion
        calculated_flow = super().compute_cf(lookup_fn=lookup_fn, **kwargs)

        if self.growth_rate:
            if hasattr(self, "_apply_compounding_growth"):
                calculated_flow = self._apply_compounding_growth(
                    base_series=calculated_flow,
                    growth_rate=self.growth_rate,
                )

        if occupancy_rate is not None and self.is_variable:
            fixed_ratio = 1.0 - (self.variable_ratio or 0.0)
            variable_part = self.variable_ratio or 0.0
            
            if isinstance(occupancy_rate, pd.Series):
                aligned_occupancy = occupancy_rate.reindex(
                    calculated_flow.index, method="ffill"
                ).fillna(1.0)
                adjustment_ratio = fixed_ratio + (variable_part * aligned_occupancy)
            else:
                adjustment_ratio = fixed_ratio + (variable_part * float(occupancy_rate))

            calculated_flow *= adjustment_ratio
            
        return calculated_flow

class OfficeCapExItem(CapExItemBase):
    """
    Office-specific capital expenditure.
    """
    pass

class OfficeExpenses(Model):
    """
    Container for all office-related expenses.
    """
    operating_expenses: List[OfficeOpExItem] = []
    capital_expenses: List[OfficeCapExItem] = [] 