# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

import pandas as pd

from ...analysis import AnalysisContext
from ...core.base import MiscIncomeBase

logger = logging.getLogger(__name__)


class OfficeMiscIncome(MiscIncomeBase):
    """
    Office-specific miscellaneous income.
    """

    def compute_cf(self, context: AnalysisContext) -> pd.Series:
        """
        Compute miscellaneous income cash flow, applying growth and occupancy adjustments.
        """
        # Base calculation (including growth) is handled by the parent class
        base_cf = super().compute_cf(context=context)

        # Apply occupancy adjustment if income is variable
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