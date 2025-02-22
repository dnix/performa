from typing import Literal, Optional, Union

from ..core._enums import UnitOfMeasureEnum
from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat
from ._recovery import RecoveryMethod
from ._rollover import RolloverAssumption


class RolloverMarketRent(Model):
    """Defines market rent assumptions for new and renewal lease terms."""

    # TODO: maybe renewal rent needs a different object
    new_amount: PositiveFloat
    new_unit: UnitOfMeasureEnum
    renewal_amount: PositiveFloat
    renewal_unit: UnitOfMeasureEnum
    growth_rate_ref: Optional[str] = None


class RolloverRentAdjustment(Model):
    """Defines rent adjustments applied during the lease term."""

    increase: PositiveFloat
    unit: UnitOfMeasureEnum
    start_increase: int  # months from start
    recurring: bool = False


class RolloverFreeRent(Model):
    """Defines free rent concessions for lease rollover scenarios."""

    new_months: int = 0
    renewal_months: int = 0
    in_or_out: Literal["in", "out"] = "in"  # TODO: clarify what this means


class RolloverTI(Model):
    """Defines tenant improvement allowances for lease rollover scenarios."""

    new_amount: PositiveFloat
    new_unit: UnitOfMeasureEnum
    renewal_amount: PositiveFloat
    renewal_unit: UnitOfMeasureEnum


class RolloverLC(Model):
    """Defines leasing commission settings for lease rollover scenarios."""

    new_amount: PositiveFloat
    new_unit: UnitOfMeasureEnum
    renewal_amount: PositiveFloat
    renewal_unit: UnitOfMeasureEnum
    growth_rate_ref: Optional[str] = None


class RolloverAssumption(Model):
    """
    Represents lease rollover assumptions as defined by Argus Enterprise/Valuation DCF.

    Attributes:
        name: Identifier for this rollover assumption.
        active: Indicator if the rollover profile is currently active.
        renewal_probability: Likelihood of lease renewal upon expiration.
        term_months: Lease term (in months) for the rollover period.
        downtime_months: Expected downtime (in months) before a new lease commences.
        market_rents: Market rent assumptions covering both new leases and renewals.
        in_term_adjustments: Adjustments applied during the active lease term.
        free_rent: Free rent concessions provided during the lease rollover.
        tenant_improvements: TI allowances offered as part of the rollover.
        leasing_commissions: Leasing commission structure for the rollover.
        renewal_free_rent: Free rent concessions specifically for lease renewals.
        renewal_ti: Tenant improvement allowances for renewals.
        renewal_lc: Leasing commission settings for lease renewals.
        recovery_method_ref: Reference to the recovery method to apply across the rollover.
        upon_expiration: Either a string label or self-reference indicating the designated rollover profile.
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
    upon_expiration: Optional[Union[str, RolloverAssumption]] = None

    @property
    def is_terminal(self) -> bool:
        """Whether this RLA leads to another or is an endpoint"""
        return self.upon_expiration is None
