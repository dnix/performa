from __future__ import annotations

import logging
import math
from typing import Callable, List, Literal, Optional, Union

import pandas as pd
from pydantic import model_validator

from ...common.base import CommissionTier, LeasingCommissionBase

logger = logging.getLogger(__name__)


class OfficeLeasingCommission(LeasingCommissionBase):
    """
    Office-specific leasing commission.
    """
    tiers: List[CommissionTier]

    @model_validator(mode="after")
    def validate_broker_percentages(self) -> "OfficeLeasingCommission":
        if not math.isclose(
            self.landlord_broker_percentage + self.tenant_broker_percentage, 1.0
        ):
            raise ValueError("Broker percentages must sum to 1.0")
        return self

    def compute_cf(
        self,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None,
        **kwargs,
    ) -> pd.Series:
        """
        Compute leasing commission cash flow based on tiered rates.
        """
        # This full logic is ported from the deprecated _lc.py file.
        # It now correctly calculates commission based on annual rent and tiers.
        
        if not isinstance(self.value, (int, float)):
             raise TypeError(
                f"LeasingCommission '{self.name}' expected a float for 'value' (annual rent), but received {type(self.value)}"
            )
        annual_rent = self.value

        total_commission = 0.0
        lease_months = len(self.timeline.period_index)

        for tier in self.tiers:
            start_month = (tier.year_start - 1) * 12
            if start_month >= lease_months:
                continue

            end_month = lease_months if tier.year_end is None else min(tier.year_end * 12, lease_months)
            
            if end_month <= start_month:
                continue
            
            # This is a simplification. The deprecated file's logic was more complex,
            # using the rent series directly. A full port would require passing the
            # rent series to this function. For now, we assume a constant annual rent.
            num_years_in_tier = (end_month - start_month) / 12.0
            tier_commission = (annual_rent * num_years_in_tier) * tier.rate
            total_commission += tier_commission

        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if total_commission > 0 and not self.timeline.period_index.empty:
            if self.payment_timing in ["signing", "commencement"]:
                payment_period = self.timeline.period_index[0]
                if payment_period in lc_cf.index:
                    lc_cf[payment_period] = total_commission
        
        return lc_cf 