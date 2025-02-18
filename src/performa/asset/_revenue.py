from datetime import date
from typing import List, Literal, Optional

from pydantic import model_validator

from ..utils._model import Model
from ..utils._types import (
    FloatBetween0And1,
    PositiveFloat,
    SquareFootRange,
)
from ._enums import (
    AssetUseEnum,
    LeaseStatusEnum,
    UnitOfMeasureEnum,
)
from ._line_item import LineItem
from ._recovery import RecoveryMethod
from ._tenant import Tenant


class RentStep(Model):
    """
    Rent increase structure for a lease.

    Attributes:
        type: Type of escalation (fixed, CPI, percentage)
        amount: Amount of increase (percentage or fixed amount)
        unit_of_measure: Units for the amount
        is_relative: Whether amount is relative to previous rent
        start_date: When increase takes effect
        recurring: Whether increase repeats
        frequency_months: How often increase occurs if recurring
    """

    type: Literal["fixed", "percentage", "cpi"]
    amount: PositiveFloat
    unit_of_measure: UnitOfMeasureEnum
    is_relative: bool  # True for relative to previous rent
    start_date: date
    recurring: bool = False
    frequency_months: Optional[int] = None


class FreeRentSchedule(Model):
    """
    Structured free rent periods.

    Attributes:
        months: Duration of free rent
        includes_recoveries: Whether recoveries are also abated
        start_month: When free rent begins (relative to lease start)
        percent_abated: Portion of rent that is abated
    """

    months: int
    includes_recoveries: bool = False
    start_month: int = 1
    percent_abated: FloatBetween0And1 = 1.0


class Lease(Model):
    """Enhanced lease model"""

    tenant: Tenant
    suite: str
    floor: Optional[str] = None
    space_type: AssetUseEnum
    status: LeaseStatusEnum

    # Dates
    available_date: date
    start_date: date
    end_date: date
    lease_term_months: int

    # Area
    area: PositiveFloat

    # Rent
    base_rent: PositiveFloat
    rent_unit: UnitOfMeasureEnum
    rent_steps: List[RentStep]
    free_rent: List[FreeRentSchedule]

    # Recovery
    recovery_method: RecoveryMethod

    # Leasing costs
    ti_allowance: PositiveFloat
    leasing_commission: FloatBetween0And1

    # Rollover
    upon_expiration: Literal["market", "renew", "vacate", "option", "reconfigured"]
    rollover_assumption: Optional[str]  # Reference to RLA

    @property
    def is_active(self) -> bool:
        """Whether lease is currently active"""
        today = date.today()
        return self.start_date <= today <= self.end_date

    @model_validator(mode="after")
    def validate_dates(self) -> "Lease":
        """Validate lease dates are logical"""
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")
        if self.available_date > self.start_date:
            raise ValueError("Available date must be before or on start date")
        return self


class VacantSuite(Model):
    """
    Represents a vacant leasable space.

    Attributes:
        suite_id: Unique identifier for the space
        area: Square footage
        use_type: Intended use
        asking_rent: Listed rental rate
        last_lease_end: When space became vacant
    """

    suite_id: str
    area: PositiveFloat
    use_type: AssetUseEnum
    asking_rent: PositiveFloat
    last_lease_end: Optional[date] = None


class RentRoll(Model):
    """Collection of all leases and vacant spaces"""

    leases: List[Lease]
    vacant_suites: List[VacantSuite]

    @property
    def total_occupied_area(self) -> PositiveFloat:
        """Calculate total leased area"""
        return sum(lease.area for lease in self.leases)

    @property
    def occupancy_rate(self) -> FloatBetween0And1:
        """Calculate current occupancy rate"""
        total_area = self.total_occupied_area + sum(
            suite.area for suite in self.vacant_suites
        )
        return self.total_occupied_area / total_area if total_area > 0 else 0.0

    @model_validator(mode="after")
    def validate_lease_tenant_mapping(self) -> "RentRoll":
        """Ensure all leases map to tenants in the rent roll"""
        tenant_ids = {t.id for t in self.leases}
        for lease in self.leases:
            if lease.tenant.id not in tenant_ids:
                raise ValueError(
                    f"Lease references tenant {lease.tenant.id} "
                    f"not found in rent roll"
                )
        return self

    # TODO: add validation for total area

    # TODO: property for all suites
    # TODO: property for stacked floors data (to enable viz)


class MarketProfile(Model):
    """Market leasing assumptions"""

    # Market Rents
    base_rent: PositiveFloat  # per sq ft
    rent_growth_rate: FloatBetween0And1

    # Typical Terms
    lease_term_months: int
    free_rent_months: int = 0

    # Leasing Costs
    ti_allowance: PositiveFloat  # per sq ft
    leasing_commission: FloatBetween0And1  # percent of rent

    # Turnover
    renewal_probability: FloatBetween0And1
    downtime_months: int

    # Applies To
    space_type: AssetUseEnum
    size_range: Optional[SquareFootRange] = None  # sq ft range


class MiscIncome(LineItem):
    """Miscellaneous income items like parking revenue"""

    ...


# TODO: aggregate revenue items?
