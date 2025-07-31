# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional, Union

import pandas as pd

from ...analysis import AnalysisContext
from ...core.base import TenantImprovementAllowanceBase
from ...core.primitives import PropertyAttributeKey

if TYPE_CHECKING:
    from .lease import OfficeLease

logger = logging.getLogger(__name__)


class OfficeTenantImprovement(TenantImprovementAllowanceBase):
    """
    Office-specific tenant improvement allowance.
    """

    def compute_cf(self, context: "AnalysisContext") -> pd.Series:
        """
        Compute TI cash flow series, handling both upfront and amortized payments,
        and respecting the payment_timing field.
        
        Args:
            context: Analysis context containing timeline, settings, and current lease info
              
        Returns:
            Cash flow series for TI payments
        """
        # DYNAMIC RESOLUTION: Handle any PropertyAttributeKey reference
        total_amount = self.value
        if isinstance(self.reference, PropertyAttributeKey):
            if self.reference == PropertyAttributeKey.NET_RENTABLE_AREA:
                total_amount = self.value * self.area
            # Could be extended for other PropertyAttributeKey types as needed

        if self.payment_method == "upfront":
            ti_cf = pd.Series(0.0, index=self.timeline.period_index)
            if total_amount > 0 and not self.timeline.period_index.empty:
                
                # Use date-based logic if lease context is available, otherwise fall back to timeline index
                if context.current_lease and hasattr(context.current_lease, 'signing_date'):
                    # New date-based logic
                    payment_date = None
                    if self.payment_timing == "signing":
                        if context.current_lease.signing_date:
                            payment_date = context.current_lease.signing_date
                        else:
                            raise ValueError(
                                "TI payment_timing is 'signing' but no signing_date provided. "
                                "Either provide signing_date on the lease or use 'commencement' timing."
                            )
                    elif self.payment_timing == "commencement":
                        payment_date = context.current_lease.timeline.start_date.to_timestamp().date()
                    
                    if payment_date:
                        payment_period = pd.Period(payment_date, freq="M")
                        if payment_period in ti_cf.index:
                            ti_cf[payment_period] = total_amount
                else:
                    # Fallback to old timeline index logic for backward compatibility
                    payment_period = self.timeline.period_index[0]
                    if self.payment_timing == "commencement":
                        # This is a simplification; in reality this might differ from timeline start
                        payment_period = self.timeline.period_index[1] if len(self.timeline.period_index) > 1 else self.timeline.period_index[0]
                    
                    if payment_period in ti_cf.index:
                        ti_cf[payment_period] = total_amount

            return ti_cf
        
        elif self.payment_method == "amortized":
            # For amortized TI, spread the cost over the amortization term
            if self.amortization_term_months is None:
                raise ValueError("amortization_term_months is required for amortized TI")
            
            monthly_amount = total_amount / self.amortization_term_months
            ti_cf = pd.Series(0.0, index=self.timeline.period_index)
            
            # Pay over the amortization term starting from timeline start
            for i in range(min(self.amortization_term_months, len(self.timeline.period_index))):
                ti_cf.iloc[i] = monthly_amount
            
            return ti_cf
        
        else:
            raise ValueError(f"Unknown payment_method: {self.payment_method}")
