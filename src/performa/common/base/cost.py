from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Literal, Optional, Union

import pandas as pd
from pydantic import model_validator

from ..primitives.cash_flow import CashFlowModel
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1, PositiveInt

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
    tiers: List[CommissionTier]
    landlord_broker_percentage: FloatBetween0And1 = 0.5
    tenant_broker_percentage: FloatBetween0And1 = 0.5
    payment_timing: Literal["signing", "commencement"] = "signing"
    renewal_rate: Optional[FloatBetween0And1] = None

    def compute_cf(self, **kwargs: Any) -> Union[pd.Series, Dict[str, pd.Series]]:
        # Simplified base implementation
        return pd.Series(0.0, index=self.timeline.period_index)


class TenantImprovementAllowanceBase(CashFlowModel):
    """
    Base class for tenant improvement allowance.
    """
    category: str = "Expense"
    subcategory: str = "TI Allowance"
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

    def compute_cf(self, **kwargs: Any) -> Union[pd.Series, Dict[str, pd.Series]]:
        # Simplified base implementation
        return pd.Series(0.0, index=self.timeline.period_index) 