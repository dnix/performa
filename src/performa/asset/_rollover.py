from typing import Literal, Optional, Union

from ..utils._model import Model
from ..utils._types import FloatBetween0And1, PositiveFloat
from ._enums import UnitOfMeasureEnum
from ._recovery import RecoveryMethod


class RolloverMarketRent(Model):
    """Market rent assumptions for new and renewal leases"""

    # TODO: maybe renewal rent needs a different object
    new_amount: PositiveFloat
    new_unit: UnitOfMeasureEnum
    renewal_amount: PositiveFloat
    renewal_unit: UnitOfMeasureEnum
    growth_rate_ref: Optional[str] = None


class RolloverRentAdjustment(Model):
    """Rent adjustments during lease term"""

    increase: PositiveFloat
    unit: UnitOfMeasureEnum
    start_increase: int  # months from start
    recurring: bool = False


class RolloverFreeRent(Model):
    """Free rent structure for new/renewal leases"""

    new_months: int = 0
    renewal_months: int = 0
    in_or_out: Literal["in", "out"] = "in"  # TODO: clarify what this means


class RolloverTI(Model):
    """TI allowances for new/renewal leases"""

    new_amount: PositiveFloat
    new_unit: UnitOfMeasureEnum
    renewal_amount: PositiveFloat
    renewal_unit: UnitOfMeasureEnum


class RolloverLC(Model):
    """Leasing commission structure for new/renewal leases"""

    new_amount: PositiveFloat
    new_unit: UnitOfMeasureEnum
    renewal_amount: PositiveFloat
    renewal_unit: UnitOfMeasureEnum
    growth_rate_ref: Optional[str] = None


class RolloverAssumption(Model):
    """
    Market leasing assumptions for lease expiration.

    Defines what happens when a lease expires, including renewal terms,
    new lease terms, and associated costs.
    """

    name: str
    active: bool = True
    renewal_probability: FloatBetween0And1
    term_months: int
    downtime_months: int

    # Rents and adjustments
    market_rents: RolloverMarketRent  # new and renewal
    in_term_adjustments: RolloverRentAdjustment

    # Concessions and costs
    free_rent: RolloverFreeRent
    tenant_improvements: RolloverTI
    leasing_commissions: RolloverLC

    # Renewal concessions
    renewal_free_rent: RolloverFreeRent
    renewal_ti: RolloverTI
    renewal_lc: RolloverLC

    # References to other objects
    recovery_method_ref: RecoveryMethod
    upon_expiration: Union[str, "RolloverAssumption", None] = (
        None  # Self-reference or RLA name
    )

    @property
    def is_terminal(self) -> bool:
        """Whether this RLA leads to another or is an endpoint"""
        return self.upon_expiration is None
