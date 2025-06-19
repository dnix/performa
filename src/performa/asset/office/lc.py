from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Callable, List, Literal, Optional, Union

import pandas as pd
from pydantic import model_validator

from ...analysis import AnalysisContext
from ...common.base import CommissionTier
from ..commercial.lc import CommercialLeasingCommissionBase

if TYPE_CHECKING:
    from .lease import OfficeLease

logger = logging.getLogger(__name__)


class OfficeLeasingCommission(CommercialLeasingCommissionBase):
    """
    Office-specific leasing commission. Inherits tiered calculation
    logic from the commercial base class.
    """
    tiers: List[CommissionTier]

    @model_validator(mode="after")
    def validate_broker_percentages(self) -> "OfficeLeasingCommission":
        if not math.isclose(
            self.landlord_broker_percentage + self.tenant_broker_percentage, 1.0
        ):
            raise ValueError("Broker percentages must sum to 1.0")
        return self

    def compute_cf(self, context: AnalysisContext) -> pd.Series:
        """
        Calculates the leasing commission based on a tiered structure.
        The 'value' field is expected to be the total annual rent for the lease.
        
        Args:
            context: Analysis context containing timeline, settings, and current lease info
            
        Returns:
            Cash flow series for leasing commission payments
        """
        if not isinstance(self.value, (int, float)):
            raise ValueError(f"LC 'value' must be a scalar annual rent. Got {type(self.value)}")

        total_annual_rent = self.value
        term_in_years = self.timeline.duration_months / 12.0
        
        total_commission = 0.0
        
        sorted_tiers = sorted(self.tiers, key=lambda t: t.year_start)
        
        for tier in sorted_tiers:
            tier_start_year = tier.year_start
            tier_end_year = tier.year_end or term_in_years
            
            years_in_tier = max(0, min(term_in_years, tier_end_year) - (tier_start_year - 1))
            
            if years_in_tier > 0:
                commissionable_rent_in_tier = total_annual_rent * years_in_tier
                total_commission += commissionable_rent_in_tier * tier.rate
                
        if self.renewal_rate is not None:
             total_commission *= self.renewal_rate

        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if total_commission > 0 and not self.timeline.period_index.empty:
            
            # Use date-based logic if lease context is available, otherwise fall back to timeline index
            if context.current_lease and hasattr(context.current_lease, 'signing_date'):
                # New date-based logic
                payment_date = None
                if self.payment_timing == "signing":
                    if context.current_lease.signing_date:
                        payment_date = context.current_lease.signing_date
                    else:
                        raise ValueError(
                            "LC payment_timing is 'signing' but no signing_date provided. "
                            "Either provide signing_date on the lease or use 'commencement' timing."
                        )
                elif self.payment_timing == "commencement":
                    payment_date = context.current_lease.timeline.start_date.to_timestamp().date()
                
                if payment_date:
                    payment_period = pd.Period(payment_date, freq="M")
                    if payment_period in lc_cf.index:
                        lc_cf[payment_period] = total_commission
            else:
                # Fallback to old timeline index logic for backward compatibility
                payment_period = self.timeline.period_index[0]
                if self.payment_timing == "commencement":
                    # This is a simplification; in reality this might differ from timeline start
                    payment_period = self.timeline.period_index[1] if len(self.timeline.period_index) > 1 else self.timeline.period_index[0]
                
                if payment_period in lc_cf.index:
                    lc_cf[payment_period] = total_commission

        return lc_cf
