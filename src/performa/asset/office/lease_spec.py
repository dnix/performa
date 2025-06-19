# src/performa/asset/office/lease_spec.py 
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
from pydantic import computed_field, model_validator

from ...common.base import LeaseSpecBase
from ...common.primitives import LeaseTypeEnum, PositiveInt, UponExpirationEnum
from .lc import OfficeLeasingCommission
from .recovery import OfficeRecoveryMethod
from .rent_abatement import OfficeRentAbatement
from .rent_escalation import OfficeRentEscalation
from .rollover import OfficeRolloverProfile
from .ti import OfficeTenantImprovement


class OfficeLeaseSpec(LeaseSpecBase):
    """
    Office-specific lease terms specification.
    """
    lease_type: LeaseTypeEnum
    rent_escalation: Optional[OfficeRentEscalation] = None
    rent_abatement: Optional[OfficeRentAbatement] = None
    recovery_method: Optional[OfficeRecoveryMethod] = None
    ti_allowance: Optional[OfficeTenantImprovement] = None
    leasing_commission: Optional[OfficeLeasingCommission] = None
    rollover_profile: Optional[OfficeRolloverProfile] = None
    upon_expiration: UponExpirationEnum

    @model_validator(mode="after")
    def check_term(self) -> "OfficeLeaseSpec":
        # Call parent validator first to ensure signing_date validation happens
        super().check_term()
        
        # Additional OfficeLeaseSpec-specific validation
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

    @computed_field
    @property
    def computed_term_months(self) -> int:
        if self.term_months:
            return self.term_months
        if self.end_date:
            periods = pd.period_range(
                start=self.start_date, end=self.end_date, freq="M"
            )
            return len(periods)
        raise ValueError("Cannot compute term_months without end_date or term_months")

    pass 