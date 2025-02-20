from datetime import date
from typing import List, Literal, Optional

from pydantic import model_validator

from ..utils._model import Model
from ..utils._types import (
    FloatBetween0And1,
    PositiveFloat,
)
from ._enums import (
    LeaseStatusEnum,
    LeaseTypeEnum,
    ProgramUseEnum,
    UnitOfMeasureEnum,
)
from ._line_item import LineItem
from ._market import MarketProfile
from ._recovery import RecoveryMethod


class Tenant(Model):
    """
    Individual tenant record representing a lease agreement.

    Attributes:
        id: Unique identifier
        name: Tenant name
        suite: Suite/unit identifier
        leased_area: Square footage leased
        percent_of_building: Percentage of total building area
        use_type: Type of use (office, retail, etc)
        lease_start: Start date of current lease
        lease_end: End date of current lease
        current_base_rent: Current annual/monthly rent
        rent_type: Type of lease (gross, net, etc)
        expense_base_year: Base year for expense stops
        renewal_probability: Likelihood of renewal
        market_profile: Applicable market assumptions
    """

    # Identity
    id: str
    name: str
    suite: str

    # Space
    leased_area: PositiveFloat  # in square feet
    percent_of_building: FloatBetween0And1

    # Use
    use_type: ProgramUseEnum

    # Current Lease Terms
    lease_start: date
    lease_end: date
    current_base_rent: PositiveFloat  # annual or monthly rent
    rent_type: LeaseTypeEnum  # options: Gross, Net, Modified Gross
    expense_base_year: Optional[int] = None

    # Renewal Terms
    renewal_probability: FloatBetween0And1
    market_profile: MarketProfile  # reference to applicable market assumptions


class RentEscalation(Model):
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
    """
    Represents a lease agreement for a tenant space.

    Attributes:
        tenant: The tenant occupying the space
        suite: Suite identifier
        floor: Optional floor number/identifier
        space_type: Type of use (office, retail, etc)
        status: Current lease status
        available_date: When space becomes available
        start_date: Lease commencement date
        end_date: Lease expiration date
        lease_term_months: Duration of lease in months
        area: Square footage of leased space
        base_rent: Starting base rent amount
        rent_unit: Units for base rent (e.g. $/SF/YR)
        rent_escalations: Schedule of rent increases
        free_rent: Schedule of free rent periods
        recovery_method: How operating expenses are recovered
        ti_allowance: Tenant improvement allowance
        leasing_commission: Commission percentage
        upon_expiration: What happens at lease end
        rollover_assumption: Reference to rollover assumptions
    """

    tenant: Tenant
    suite: str
    floor: Optional[str] = None
    space_type: ProgramUseEnum
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
    rent_unit: UnitOfMeasureEnum  # e.g. $/SF/YR
    rent_escalations: List[RentEscalation]
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
    use_type: ProgramUseEnum
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


class MiscIncome(LineItem):
    """Miscellaneous income items like parking revenue"""

    ...


# TODO: aggregate revenue items into unified Revenue object?


class SecurityDeposit(Model):
    """
    Model representing the security deposit configuration for a tenant,
    based on Argus Enterprise's Security Deposits specification.

    Attributes:
        deposit_mode (Literal["Refundable", "Non-Refundable", "Hybrid"]):
            Indicates if the security deposit is fully refundable, entirely non-refundable, 
            or a hybrid approach where a portion is refundable.
        deposit_unit (Literal["Months", "Dollar", "DollarPerSF"]):
            Unit used to express the deposit. For example, the deposit may be determined 
            as a number of months' rent, a fixed dollar amount, or a rate per square foot.
        deposit_amount (PositiveFloat):
            The total amount of the security deposit.
        interest_rate (Optional[FloatBetween0And1]):
            The interest rate applicable to the refundable portion of the deposit.
            Relevant only if the deposit mode is "Refundable" or "Hybrid".
        percent_to_refund (Optional[FloatBetween0And1]):
            The percentage of the deposit that is refundable. When using a hybrid mode,
            the remainder is retained.
    """
    deposit_mode: Literal["Refundable", "Non-Refundable", "Hybrid"]
    deposit_unit: Literal["Months", "Dollar", "DollarPerSF"]
    deposit_amount: PositiveFloat
    interest_rate: Optional[FloatBetween0And1] = None
    percent_to_refund: Optional[FloatBetween0And1] = None
