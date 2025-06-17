from __future__ import annotations

from abc import abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Union
from uuid import UUID

import numpy as np
import pandas as pd
from pydantic import computed_field, model_validator

from ..primitives.cash_flow import CashFlowModel
from ..primitives.enums import (
    CalculationPass,
    FrequencyEnum,
    LeaseStatusEnum,
    ProgramUseEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from ..primitives.model import Model
from ..primitives.timeline import Timeline
from ..primitives.types import FloatBetween0And1, PositiveFloat, PositiveInt

# FIXME: --- Placeholder Base Classes to avoid circular imports ---
# These will be replaced with actual imports from other .base modules once they are created.

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext

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
    recovery_method: Optional[RecoveryMethodBase] = None
    rollover_profile: Optional[RolloverProfileBase] = None
    upon_expiration: UponExpirationEnum

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
    Base abstract model for a lease.

    This class serves as the foundation for all lease types. It is abstract
    and requires concrete subclasses (e.g., `CommercialLeaseBase`) to implement
    the detailed cash flow calculation logic in `compute_cf` and the rollover
    projection logic in `project_future_cash_flows`.
    """
    category: str = "Revenue"
    subcategory: str = "Lease" # Simplified from enum for base class
    status: LeaseStatusEnum
    area: PositiveFloat
    suite: str
    floor: str
    upon_expiration: UponExpirationEnum
    rent_escalation: Optional[RentEscalationBase] = None
    rent_abatement: Optional[RentAbatementBase] = None

    @computed_field
    @property
    def calculation_pass(self) -> CalculationPass:
        """Overrides the default pass. Leases are dependent calculations."""
        return CalculationPass.DEPENDENT_VALUES

    @abstractmethod
    def compute_cf(self, context: AnalysisContext) -> Dict[str, pd.Series]:
        """
        Computes all cash flows related to the lease for its initial term.

        This method must be implemented by subclasses to calculate all relevant
        cash flow components (e.g., base rent, escalations, abatements, recoveries,
        TI, LC) and return them as a dictionary of pandas Series.
        """
        raise NotImplementedError

    @abstractmethod
    def project_future_cash_flows(self, context: AnalysisContext) -> pd.DataFrame:
        """
        Projects cash flows for this lease and all subsequent rollover events
        throughout the analysis period.

        This method must be implemented by subclasses to handle the logic of
        lease expiration and the creation of new speculative or renewal leases
        based on the `upon_expiration` setting and rollover profiles.
        """
        pass 