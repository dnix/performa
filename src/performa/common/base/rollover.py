from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Union

import pandas as pd

from ..primitives.enums import FrequencyEnum, UnitOfMeasureEnum, UponExpirationEnum
from ..primitives.growth_rates import GrowthRate
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1, PositiveFloat, PositiveInt
from .cost import LeasingCommissionBase, TenantImprovementAllowanceBase
from .lease import RentAbatementBase, RentEscalationBase
from .recovery import RecoveryMethodBase


class RolloverLeaseTermsBase(Model):
    """
    Base class for lease terms applied in different rollover scenarios.
    """
    term_months: Optional[PositiveInt] = None
    market_rent: Optional[Union[PositiveFloat, pd.Series, Dict, List]] = None
    unit_of_measure: UnitOfMeasureEnum = UnitOfMeasureEnum.PER_UNIT
    frequency: FrequencyEnum = FrequencyEnum.ANNUAL
    growth_rate: Optional[GrowthRate] = None
    rent_escalation: Optional[RentEscalationBase] = None
    rent_abatement: Optional[RentAbatementBase] = None
    recovery_method: Optional[RecoveryMethodBase] = None
    ti_allowance: Optional[TenantImprovementAllowanceBase] = None
    leasing_commission: Optional[LeasingCommissionBase] = None


class RolloverProfileBase(Model):
    """
    Base class for a comprehensive profile for lease rollovers and renewals.
    """
    name: str
    term_months: PositiveInt
    renewal_probability: FloatBetween0And1
    downtime_months: int
    market_terms: RolloverLeaseTermsBase
    renewal_terms: RolloverLeaseTermsBase
    option_terms: Optional[RolloverLeaseTermsBase] = None
    upon_expiration: UponExpirationEnum = UponExpirationEnum.MARKET
    next_profile: Optional[str] = None 