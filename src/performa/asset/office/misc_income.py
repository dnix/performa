from __future__ import annotations

import logging
from typing import Callable, Optional, Union

import pandas as pd

from ...common.base import MiscIncomeBase

logger = logging.getLogger(__name__)


class OfficeMiscIncome(MiscIncomeBase):
    """
    Office-specific miscellaneous income.
    """

    def compute_cf(
        self,
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        **kwargs,
    ) -> pd.Series:
        """
        Compute miscellaneous income cash flow, applying growth and occupancy adjustments.
        """
        # Base calculation is inherited from CashFlowModel via MiscIncomeBase
        calculated_flow = super().compute_cf(**kwargs)

        # Apply growth if applicable
        if self.growth_rate:
            if hasattr(self, "_apply_compounding_growth"):
                # Assuming growth starts at the beginning of the item's timeline
                growth_start_date = self.timeline.start_date.to_timestamp().date()
                calculated_flow = self._apply_compounding_growth(
                    base_series=calculated_flow,
                    growth_profile=self.growth_rate,
                    growth_start_date=growth_start_date,
                )
        
        # Apply occupancy adjustment if income is variable
        if occupancy_rate is not None and self.is_variable:
            fixed_ratio = 1.0 - (self.variable_ratio or 0.0)
            variable_part = (self.variable_ratio or 0.0)
            
            if isinstance(occupancy_rate, pd.Series):
                aligned_occupancy = occupancy_rate.reindex(
                    calculated_flow.index, method="ffill"
                ).fillna(1.0)
                adjustment_ratio = fixed_ratio + (variable_part * aligned_occupancy)
            else: # float
                adjustment_ratio = fixed_ratio + (variable_part * float(occupancy_rate))

            calculated_flow *= adjustment_ratio
            
        return calculated_flow 