# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Callable, List, Literal, Optional, Union

import pandas as pd
from pydantic import model_validator

from ...analysis import AnalysisContext
from ...core.base import CommissionTier
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
        Calculates the leasing commission based on a tiered structure with flexible payment timing.
        Each tier can specify its own payment split between signing and commencement.
        
        Args:
            context: Analysis context containing timeline, settings, and current lease info
            
        Returns:
            Cash flow series for leasing commission payments
        """
        if not isinstance(self.value, (int, float)):
            raise ValueError(f"LC 'value' must be a scalar annual rent. Got {type(self.value)}")

        total_annual_rent = self.value
        term_in_years = self.timeline.duration_months / 12.0
        
        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        
        sorted_tiers = sorted(self.tiers, key=lambda t: t.year_start)
        
        for tier in sorted_tiers:
            tier_start_year = tier.year_start
            tier_end_year = tier.year_end or term_in_years
            
            years_in_tier = max(0, min(term_in_years, tier_end_year) - (tier_start_year - 1))
            
            if years_in_tier > 0:
                commissionable_rent_in_tier = total_annual_rent * years_in_tier
                tier_commission = commissionable_rent_in_tier * tier.rate
                
                if self.renewal_rate is not None:
                    tier_commission *= self.renewal_rate

                # Split the tier commission according to payment timing percentages
                signing_amount = tier_commission * tier.signing_percentage
                commencement_amount = tier_commission * tier.commencement_percentage
                
                # Place payments at appropriate dates
                if signing_amount > 0:
                    signing_period = self._get_payment_period(context, "signing")
                    if signing_period in lc_cf.index:
                        lc_cf[signing_period] += signing_amount
                
                if commencement_amount > 0:
                    commencement_period = self._get_payment_period(context, "commencement")
                    if commencement_period in lc_cf.index:
                        lc_cf[commencement_period] += commencement_amount

        return lc_cf
    
    def _get_payment_period(self, context: AnalysisContext, timing: str) -> pd.Period:
        """
        Get the payment period for a specific timing milestone.
        
        Args:
            context: Analysis context with lease information
            timing: Either "signing" or "commencement"
            
        Returns:
            Period when payment should occur
        """
        if context.current_lease and hasattr(context.current_lease, 'signing_date'):
            # Date-based logic when lease context is available
            if timing == "signing":
                if context.current_lease.signing_date:
                    return pd.Period(context.current_lease.signing_date, freq="M")
                else:
                    raise ValueError(
                        "LC tier requires signing payment but no signing_date provided. "
                        "Either provide signing_date on the lease or adjust tier payment percentages."
                    )
            elif timing == "commencement":
                return pd.Period(context.current_lease.timeline.start_date.to_timestamp().date(), freq="M")
        elif timing == "signing":
            return self.timeline.period_index[0]
        elif timing == "commencement":
            return self.timeline.period_index[1] if len(self.timeline.period_index) > 1 else self.timeline.period_index[0]
        
        raise ValueError(f"Unknown payment timing: {timing}")
