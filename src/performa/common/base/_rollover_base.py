from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Union

import pandas as pd

from ..primitives._enums import FrequencyEnum, UnitOfMeasureEnum, UponExpirationEnum
from ..primitives._model import Model
from ..primitives._types import FloatBetween0And1, PositiveFloat, PositiveInt

if TYPE_CHECKING:
    from ..primitives._growth_rates import GrowthRate

    # Import placeholder base classes from other .base modules
    from ._cost_base import LeasingCommissionBase, TenantImprovementAllowanceBase
    from ._recovery_base import RecoveryMethodBase
    from ._rent_abatement_base import RentAbatementBase
    from ._rent_escalation_base import RentEscalationBase


class RolloverLeaseTermsBase(Model):
    """
    Base class for lease terms applied in different rollover scenarios.
    """
    term_months: Optional[PositiveInt] = None
    market_rent: Optional[Union[PositiveFloat, pd.Series, Dict, List]] = None
    unit_of_measure: UnitOfMeasureEnum = UnitOfMeasureEnum.PER_UNIT
    frequency: FrequencyEnum = FrequencyEnum.ANNUAL
    growth_rate: Optional["GrowthRate"] = None
    rent_escalation: Optional["RentEscalationBase"] = None
    rent_abatement: Optional["RentAbatementBase"] = None
    recovery_method: Optional["RecoveryMethodBase"] = None
    ti_allowance: Optional["TenantImprovementAllowanceBase"] = None
    leasing_commission: Optional["LeasingCommissionBase"] = None


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
    option_terms: RolloverLeaseTermsBase
    upon_expiration: UponExpirationEnum = UponExpirationEnum.MARKET
    next_profile: Optional[str] = None 