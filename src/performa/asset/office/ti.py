from __future__ import annotations

import logging
from typing import Callable, Optional, Union

import pandas as pd

from ...analysis import AnalysisContext
from ...common.base import TenantImprovementAllowanceBase

logger = logging.getLogger(__name__)


class OfficeTenantImprovement(TenantImprovementAllowanceBase):
    """
    Office-specific tenant improvement allowance.
    """

    def compute_cf(self, context: "AnalysisContext") -> pd.Series:
        """
        Compute TI cash flow series, handling both upfront and amortized payments,
        and respecting the payment_timing field.
        """
        total_amount = 0.0
        if isinstance(self.value, (int, float)):
            total_amount = self.value
        else:
            raise ValueError(f"TI 'value' must be a scalar. Got {type(self.value)}")

        if self.payment_method == "upfront":
            ti_cf = pd.Series(0.0, index=self.timeline.period_index)
            if total_amount > 0 and not self.timeline.period_index.empty:
                # 'signing' is assumed to be the very first period of the item's timeline.
                # 'commencement' is the second period (1 month after signing).
                payment_index = 0
                if self.payment_timing == "commencement":
                    payment_index = 1
                
                if payment_index < len(self.timeline.period_index):
                    payment_period = self.timeline.period_index[payment_index]
                    ti_cf[payment_period] = total_amount
            return ti_cf

        elif self.payment_method == "amortized":
            assert self.interest_rate is not None
            assert self.amortization_term_months is not None

            monthly_rate = self.interest_rate / 12
            if monthly_rate > 0 and total_amount > 0:
                monthly_payment = (
                    total_amount
                    * (monthly_rate * (1 + monthly_rate) ** self.amortization_term_months)
                    / ((1 + monthly_rate) ** self.amortization_term_months - 1)
                )
            elif total_amount > 0: # No interest
                monthly_payment = total_amount / self.amortization_term_months
            else:
                monthly_payment = 0

            amort_end = self.timeline.start_date + self.amortization_term_months - 1
            amort_periods = pd.period_range(
                start=self.timeline.start_date,
                end=min(amort_end, self.timeline.end_date),
                freq="M",
            )
            ti_cf = pd.Series(0.0, index=self.timeline.period_index)
            ti_cf.loc[amort_periods] = monthly_payment
            return ti_cf

        return pd.Series(0.0, index=self.timeline.period_index)
