# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import math
from typing import List, Literal

import pandas as pd

from ...analysis import AnalysisContext
from ...core.base import CommissionTier, LeasingCommissionBase
from ...core.primitives.types import FloatBetween0And1


class CommercialLeasingCommissionBase(LeasingCommissionBase):
    """
    Base class for leasing commissions in commercial properties,
    featuring a tiered calculation logic.
    """
    tiers: List[CommissionTier]
    landlord_broker_percentage: FloatBetween0And1 = 0.5
    tenant_broker_percentage: FloatBetween0And1 = 0.5

    def compute_cf(self, context: AnalysisContext) -> pd.Series:
        """
        Calculates the leasing commission based on a tiered structure.
        The 'value' field is expected to be the total annual rent for the lease.
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
            payment_period = self.timeline.period_index[0]
            if self.payment_timing == "commencement":
                 # This is a simplification; a more robust model might have an explicit
                 # rent commencement date that differs from the timeline start.
                 payment_period = self.timeline.period_index[0]
            
            if payment_period in lc_cf.index:
                lc_cf[payment_period] = total_commission

        return lc_cf 