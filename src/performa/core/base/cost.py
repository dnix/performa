from __future__ import annotations

import logging
import math
from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Union

import pandas as pd
from pydantic import model_validator

from ..primitives.cash_flow import CashFlowModel
from ..primitives.enums import UnitOfMeasureEnum
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1, PositiveFloat, PositiveInt

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext

logger = logging.getLogger(__name__)


class CommissionTier(Model):
    """
    Represents a tier in the leasing commission structure with flexible payment timing.
    
    Supports split payments across signing and commencement milestones, enabling
    real-world scenarios like "50% at signing, 50% at commencement".
    
    Examples:
        # Traditional: 100% at signing
        CommissionTier(year_start=1, year_end=5, rate=0.06)
        
        # Split payment: 50% at signing, 50% at commencement  
        CommissionTier(
            year_start=1, year_end=5, rate=0.06,
            signing_percentage=0.5, commencement_percentage=0.5
        )
        
        # Multi-tier with different payment schedules:
        [
            CommissionTier(year_start=1, year_end=3, rate=0.06, signing_percentage=0.5, commencement_percentage=0.5),
            CommissionTier(year_start=4, year_end=5, rate=0.03, signing_percentage=1.0, commencement_percentage=0.0)
        ]
    """
    year_start: PositiveInt = 1
    year_end: Optional[PositiveInt] = None
    rate: FloatBetween0And1
    
    # Payment timing splits (defaults maintain backward compatibility)
    signing_percentage: FloatBetween0And1 = 1.0      # Default: 100% at signing
    commencement_percentage: FloatBetween0And1 = 0.0  # Default: 0% at commencement
    
    @model_validator(mode="after")
    def validate_payment_percentages(self) -> "CommissionTier":
        """Ensure payment percentages sum to 1.0"""
        if not math.isclose(self.signing_percentage + self.commencement_percentage, 1.0):
            raise ValueError(
                f"Payment percentages must sum to 1.0. Got signing={self.signing_percentage}, "
                f"commencement={self.commencement_percentage}, sum={self.signing_percentage + self.commencement_percentage}"
            )
        return self


class LeasingCommissionBase(CashFlowModel):
    """
    Base class for leasing commissions.
    """
    category: str = "Expense"
    subcategory: str = "Lease"  # Special subcategory for lease-related costs
    payment_timing: Literal["signing", "commencement"] = "signing"  # When the LC is paid
    renewal_rate: Optional[FloatBetween0And1] = None

    def compute_cf(self, context: AnalysisContext) -> pd.Series:
        """
        Base LC calculation. Subclasses should override this method.
        
        Default implementation: Simple upfront payment at timeline start.
        """
        commission_amount = self.value
        
        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if commission_amount > 0 and not self.timeline.period_index.empty:
            # For LC, both signing and commencement typically occur at timeline start
            # This is different from TI where commencement might be delayed
            payment_period = self.timeline.period_index[0]
            
            if payment_period in lc_cf.index:
                lc_cf[payment_period] = commission_amount
        
        return lc_cf


class TenantImprovementAllowanceBase(CashFlowModel):
    """
    Base class for tenant improvement allowances (TI).
    """
    area: Optional[PositiveFloat] = None  # Optional - can get from lease context
    category: str = "Expense"
    subcategory: str = "Lease"  # Special subcategory for lease-related costs
    payment_method: Literal["upfront", "amortized"] = "upfront"
    payment_timing: Literal["signing", "commencement"] = "commencement"  # When the TI is paid
    interest_rate: Optional[FloatBetween0And1] = None  # For amortized TI
    amortization_term_months: Optional[PositiveInt] = None  # For amortized TI

    def compute_cf(self, context: AnalysisContext) -> pd.Series:
        """
        Base TI calculation. Subclasses should override this method.
        
        Default implementation: Simple upfront payment at timeline start.
        """
        total_amount = self.value
        if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
            # Get area from lease context if available, otherwise use area field
            area = self.area
            if context.current_lease and hasattr(context.current_lease, 'area'):
                area = context.current_lease.area
            
            if area:
                total_amount = self.value * area
            else:
                raise ValueError("Area required for PER_UNIT TI but not available from lease context or TI model")
        
        if self.payment_method == "upfront":
            ti_cf = pd.Series(0.0, index=self.timeline.period_index)
            if total_amount > 0 and not self.timeline.period_index.empty:
                # Default implementation: simple timeline-based payment
                payment_period = self.timeline.period_index[0]
                if self.payment_timing == "commencement":
                    payment_period = self.timeline.period_index[1] if len(self.timeline.period_index) > 1 else self.timeline.period_index[0]
                
                if payment_period in ti_cf.index:
                    ti_cf[payment_period] = total_amount
            return ti_cf
        elif self.payment_method == "amortized":
            # For amortized, spread evenly across timeline (simplified)
            monthly_amount = total_amount / len(self.timeline.period_index) if not self.timeline.period_index.empty else 0
            return pd.Series(monthly_amount, index=self.timeline.period_index)
        
        return pd.Series(0.0, index=self.timeline.period_index) 