from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Union

import pandas as pd
from pydantic import model_validator

from ..primitives.cash_flow import CashFlowModel
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1, PositiveInt

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext

logger = logging.getLogger(__name__)


class CommissionTier(Model):
    """
    Represents a tier in the leasing commission structure.
    """
    year_start: PositiveInt = 1
    year_end: Optional[PositiveInt] = None
    rate: FloatBetween0And1


class LeasingCommissionBase(CashFlowModel):
    """
    Base class for leasing commissions.
    """
    category: str = "Expense"
    subcategory: str = "Leasing Commission"
    payment_timing: Literal["signing", "commencement"] = "signing"
    renewal_rate: Optional[FloatBetween0And1] = None

    def compute_cf(self, context: "AnalysisContext") -> pd.Series:
        # This is a simplified base implementation.
        # Concrete implementations should calculate the total commission
        # and place it in the correct period on the timeline.
        total_commission = 0.0
        if isinstance(self.value, (int, float)):
            total_commission = self.value # Assume value is pre-calculated total

        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if total_commission > 0 and not self.timeline.period_index.empty:
            payment_period = self.timeline.period_index[0]
            if payment_period in lc_cf.index:
                lc_cf[payment_period] = total_commission
        return lc_cf


class TenantImprovementAllowanceBase(CashFlowModel):
    """
    Base class for tenant improvement allowance.
    """
    category: str = "Expense"
    subcategory: str = "TI Allowance"
    payment_timing: Literal["signing", "commencement"] = "commencement"
    payment_method: Literal["upfront", "amortized"] = "upfront"
    payment_date: Optional[date] = None
    interest_rate: Optional[FloatBetween0And1] = None
    amortization_term_months: Optional[PositiveInt] = None

    @model_validator(mode="after")
    def validate_amortization(self) -> "TenantImprovementAllowanceBase":
        if self.payment_method == "amortized":
            if self.interest_rate is None:
                raise ValueError("interest_rate is required for amortized TI")
            if self.amortization_term_months is None:
                raise ValueError("amortization_term_months is required for amortized TI")
        return self

    def compute_cf(self, context: "AnalysisContext") -> pd.Series:
        # This is a simplified base implementation.
        # Concrete implementations should handle different payment methods.
        total_amount = 0.0
        if isinstance(self.value, (int, float)):
            total_amount = self.value

        ti_cf = pd.Series(0.0, index=self.timeline.period_index)
        if total_amount > 0 and not self.timeline.period_index.empty:
             payment_period = self.timeline.period_index[0]
             if payment_period in ti_cf.index:
                ti_cf[payment_period] = total_amount
        return ti_cf 