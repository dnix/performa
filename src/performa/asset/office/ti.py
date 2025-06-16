from __future__ import annotations

import logging
from typing import Callable, Optional, Union

import pandas as pd

from ...common.base import TenantImprovementAllowanceBase

logger = logging.getLogger(__name__)


class OfficeTenantImprovement(TenantImprovementAllowanceBase):
    """
    Office-specific tenant improvement allowance.
    """

    def compute_cf(
        self,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None,
        **kwargs,
    ) -> pd.Series:
        """
        Compute TI cash flow series, handling both upfront and amortized payments.
        """
        # This full logic is ported from the deprecated _ti.py file.
        # It relies on the parent CashFlowModel's compute_cf to first resolve
        # the total TI amount, which might be a direct value or a calculated one.
        # The deprecated version's super().compute_cf() was complex. Here we assume
        # the total amount is resolved and stored in self.value.
        # A more robust solution might involve a dedicated method to get the total amount.
        
        total_amount = 0.0
        if isinstance(self.value, (int, float)):
            total_amount = self.value
        elif self.reference and lookup_fn:
             # This part assumes a more complex calculation based on a reference
             # (e.g., $/SF * area). The parent CashFlowModel logic would handle this.
             # For now, we simulate this by calling the base implementation.
             base_cf = super().compute_cf(lookup_fn=lookup_fn, **kwargs)
             total_amount = base_cf.sum()
        else:
            raise ValueError("TI amount cannot be determined. Provide 'value' or a resolvable 'reference'.")

        if self.payment_method == "upfront":
            payment_date = self.payment_date or self.timeline.start_date.to_timestamp().date()
            payment_period = pd.Period(payment_date, freq="M")
            ti_cf = pd.Series(0.0, index=self.timeline.period_index)
            if payment_period in ti_cf.index:
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
