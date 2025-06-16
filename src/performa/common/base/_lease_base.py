from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Union

import numpy as np
import pandas as pd
from pydantic import computed_field, model_validator

from ..primitives._cash_flow import CashFlowModel
from ..primitives._enums import (
    FrequencyEnum,
    LeaseStatusEnum,
    ProgramUseEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from ..primitives._model import Model
from ..primitives._timeline import Timeline
from ..primitives._types import FloatBetween0And1, PositiveFloat, PositiveInt

# --- Placeholder Base Classes to avoid circular imports ---
# These will be replaced with actual imports from other .base modules once they are created.

class RentEscalationBase(Model):
    type: Literal["fixed", "percentage", "cpi"]
    amount: PositiveFloat
    unit_of_measure: UnitOfMeasureEnum
    is_relative: bool
    start_date: date
    recurring: bool = False
    frequency_months: Optional[int] = None


class RentAbatementBase(Model):
    months: int
    includes_recoveries: bool = False
    start_month: int = 1
    abated_ratio: FloatBetween0And1 = 1.0


class RecoveryMethodBase(Model):
    pass

class TenantImprovementAllowanceBase(CashFlowModel):
    def compute_cf(self, **kwargs: Any) -> Union[pd.Series, Dict[str, pd.Series]]:
        return super().compute_cf(**kwargs)

class LeasingCommissionBase(CashFlowModel):
    def compute_cf(self, **kwargs: Any) -> Union[pd.Series, Dict[str, pd.Series]]:
        return super().compute_cf(**kwargs)

class RolloverProfileBase(Model):
    pass

class TenantBase(Model):
    pass

# --- Main Base Models ---

class LeaseSpecBase(Model):
    """
    Base definition for a lease term's parameters.
    """

    tenant_name: str
    suite: str
    floor: str
    area: PositiveFloat
    use_type: ProgramUseEnum
    start_date: date
    end_date: Optional[date] = None
    term_months: Optional[PositiveInt] = None
    base_rent_value: PositiveFloat
    base_rent_unit_of_measure: UnitOfMeasureEnum
    base_rent_frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    rent_escalation: Optional[RentEscalationBase] = None
    rent_abatement: Optional[RentAbatementBase] = None
    recovery_method_ref: Optional[str] = None
    ti_allowance_ref: Optional[str] = None
    lc_ref: Optional[str] = None
    upon_expiration: UponExpirationEnum
    rollover_profile_ref: Optional[str] = None

    @model_validator(mode="after")
    def check_term(self) -> "LeaseSpecBase":
        if self.end_date is None and self.term_months is None:
            raise ValueError("Either end_date or term_months must be provided")
        if self.end_date and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self

    @computed_field
    @property
    def computed_end_date(self) -> date:
        if self.end_date:
            return self.end_date
        if self.term_months:
            return (
                pd.Period(self.start_date, freq="M") + self.term_months - 1
            ).end_time.date()
        raise ValueError("Cannot compute end_date without end_date or term_months")


class LeaseBase(CashFlowModel):
    """
    Base model for a lease, handling fundamental cash flow calculations.
    """
    category: str = "Revenue"
    subcategory: str = "Lease" # Simplified from enum for base class
    status: LeaseStatusEnum
    area: PositiveFloat
    rent_escalation: Optional[RentEscalationBase] = None
    rent_abatement: Optional[RentAbatementBase] = None

    def _apply_escalations(self, base_flow: pd.Series) -> pd.Series:
        # Simplified escalation logic for the base class
        if not self.rent_escalation:
            return base_flow
        # Placeholder for real implementation
        return base_flow

    def _apply_abatements(self, rent_flow: pd.Series) -> tuple[pd.Series, pd.Series]:
        # Simplified abatement logic for the base class
        if not self.rent_abatement:
            return rent_flow, pd.Series(0.0, index=rent_flow.index)
        # Placeholder for real implementation
        return rent_flow, pd.Series(0.0, index=rent_flow.index)

    def compute_cf(self, **kwargs: Any) -> Dict[str, pd.Series]:
        """
        Computes base rent, applies escalations and abatements.
        Does NOT handle recoveries or other complex components.
        """
        # 1. Calculate Base Rent from `value`, `unit_of_measure`, `frequency`
        if isinstance(self.value, (int, float)):
            initial_monthly_value = self.value
            if self.frequency == FrequencyEnum.ANNUAL:
                initial_monthly_value /= 12
            if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
                initial_monthly_value *= self.area
            base_rent = pd.Series(
                initial_monthly_value, index=self.timeline.period_index
            )
        else:
            # Handle series/dict value if necessary, or raise error for base class
            raise NotImplementedError("Base class only supports scalar rent value.")

        # 2. Apply Escalations
        base_rent_with_escalations = self._apply_escalations(base_rent)

        # 3. Apply Abatements
        base_rent_final, abatement_cf = self._apply_abatements(
            base_rent_with_escalations
        )

        return {
            "base_rent": base_rent_final,
            "abatement_applied": abatement_cf,
        } 