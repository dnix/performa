# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Development Disposition Models - Exit Strategy Cash Flows

Cash flow models for development project dispositions and exit strategies.
Follows the same patterns as other asset modules for consistency.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..core.primitives import CashFlowModel


class DispositionCashFlow(CashFlowModel):
    """
    Cash flow model for development project disposition proceeds.

    Represents the cash inflow from selling a completed development project
    at stabilized operations. Uses the same patterns as other cash flow models
    in the performa ecosystem.

    Example:
        ```python
        disposition = DispositionCashFlow(
            name="Project Sale",
            timeline=sale_timeline,
            value=net_proceeds,
            category="Disposition",
            subcategory="Sale Proceeds",
            frequency="monthly"
        )
        ```
    """

    def compute_cf(self, context) -> Any:
        """
        Compute cash flow for disposition proceeds.

        Returns a single cash inflow on the disposition date equal to
        the net proceeds after transaction costs.
        """
        cf = pd.Series(0.0, index=self.timeline.period_index)
        if not cf.empty:
            # Single cash inflow on disposition date
            cf.iloc[0] = self.value  # Positive cash inflow from sale
        return cf
