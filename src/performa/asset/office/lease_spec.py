# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date
from typing import List, Optional, Union

import pandas as pd

from ...core.base import LeaseSpecBase
from ...core.primitives import LeaseTypeEnum, ProgramUseEnum, UponExpirationEnum
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

    # Office-specific field with override for use_type default
    use_type: ProgramUseEnum = ProgramUseEnum.OFFICE

    lease_type: LeaseTypeEnum = LeaseTypeEnum.NET

    # Multiple escalations support
    rent_escalations: Optional[
        Union[OfficeRentEscalation, List[OfficeRentEscalation]]
    ] = None

    rent_abatement: Optional[OfficeRentAbatement] = None
    recovery_method: Optional[OfficeRecoveryMethod] = None
    ti_allowance: Optional[OfficeTenantImprovement] = None
    leasing_commission: Optional[OfficeLeasingCommission] = None
    rollover_profile: Optional[OfficeRolloverProfile] = None
    upon_expiration: UponExpirationEnum = UponExpirationEnum.MARKET

    # Term validation is now handled by LeaseSpecBase

    @property
    def computed_end_date(self) -> date:
        if self.end_date:
            return self.end_date
        if self.term_months:
            return (
                pd.Period(self.start_date, freq="M") + self.term_months - 1
            ).end_time.date()
        raise ValueError("Cannot compute end_date without end_date or term_months")

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
