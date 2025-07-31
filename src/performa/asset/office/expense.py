# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union
from uuid import UUID

import pandas as pd
from pydantic import Field

from ...core.base import CapExItemBase, OpExItemBase
from ...core.primitives import GrowthRate, Model, Timeline

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext

logger = logging.getLogger(__name__)

class OfficeOpExItem(OpExItemBase):
    """
    Office-specific operating expense.
    """

    def compute_cf(self, context: AnalysisContext) -> pd.Series:
        """
        Compute office operating expense cash flow.

        This method follows a clean two-step process:
        1. It calls `super().compute_cf(context)` to get the fully calculated,
           growth-adjusted base cash flow series from `OpExItemBase`.
        2. It then applies office-specific adjustments for occupancy if the
           expense is defined as variable.
        """
        # Get the base cash flow (already includes growth, etc.)
        base_cf = super().compute_cf(context=context)

        # Apply occupancy adjustment if this expense is variable
        if self.is_variable and context.occupancy_rate_series is not None:
            fixed_ratio = 1.0 - (self.variable_ratio or 0.0)
            variable_part = self.variable_ratio or 0.0
            
            occupancy_rate = context.occupancy_rate_series
            if isinstance(occupancy_rate, pd.Series):
                aligned_occupancy = occupancy_rate.reindex(
                    base_cf.index, method="ffill"
                ).fillna(1.0)
                adjustment_ratio = fixed_ratio + (variable_part * aligned_occupancy)
            else: # float
                adjustment_ratio = fixed_ratio + (variable_part * float(occupancy_rate))

            base_cf *= adjustment_ratio
            
        return base_cf

class OfficeCapExItem(CapExItemBase):
    """
    Office-specific capital expenditure.
    """
    pass

class OfficeExpenses(Model):
    """
    Container for all office-related expenses.
    """
    operating_expenses: List[OfficeOpExItem] = Field(default_factory=list)
    capital_expenses: List[OfficeCapExItem] = Field(default_factory=list) 