from __future__ import annotations

import logging
from typing import List, Optional

from pydantic import Field, model_validator

from ..core._enums import (
    ProgramUseEnum,
)
from ..core._model import Model
from ..core._types import (
    FloatBetween0And1,
    PositiveFloat,
)
from ._lease import LeaseSpec

logger = logging.getLogger(__name__)


# --- Vacant Suite ---
class VacantSuite(Model):
    """
    Represents a vacant leasable space.

    Attributes:
        suite: Unique identifier for the space
        floor: Floor number or identifier (optional)
        area: Square footage
        use_type: Intended use
        is_divisible: Indicates if this suite can be subdivided during absorption.
        subdivision_average_lease_area: Target average area for each subdivided lease. Required if is_divisible is True.
        subdivision_minimum_lease_area: Minimum area for a subdivided lease, also used for handling remainders.
        subdivision_naming_pattern: Pattern for naming subdivided leases. {master_suite_id} and {count} are placeholders.

    Note:
        This model is immutable (frozen=True via the base Model). All mutable state required for dynamic subdivision (such as remaining area and units created) must be tracked externally using a SuiteAbsorptionState object or similar. Do not attempt to mutate any attribute of this model during absorption.
    """

    suite: str
    floor: str
    area: PositiveFloat
    use_type: ProgramUseEnum

    # Fields for dynamic subdivision (Feature F4)
    is_divisible: bool = Field(
        default=False, description="Indicates if this suite can be subdivided during absorption."
    )
    subdivision_average_lease_area: Optional[PositiveFloat] = Field(
        default=None, description="Target average area for each subdivided lease. Required if is_divisible is True."
    )
    subdivision_minimum_lease_area: Optional[PositiveFloat] = Field(
        default=None, description="Minimum area for a subdivided lease, also used for handling remainders. Defaults to a fraction of average if not set."
    )
    subdivision_naming_pattern: str = Field(
        default="{master_suite_id}-Sub{count}",
        description="Pattern for naming subdivided leases. {master_suite_id} and {count} are placeholders."
    )

    @model_validator(mode='after')
    def _init_subdivision_state(self) -> "VacantSuite":
        if self.is_divisible:
            if self.subdivision_average_lease_area is None:
                raise ValueError(
                    "'subdivision_average_lease_area' must be set if 'is_divisible' is True."
                )
            if self.subdivision_average_lease_area <= 0:
                raise ValueError(
                    "'subdivision_average_lease_area' must be a positive value."
                )
            if self.subdivision_average_lease_area > self.area:
                raise ValueError(
                    "'subdivision_average_lease_area' cannot be greater than the total suite area."
                )
            if self.subdivision_minimum_lease_area is not None and self.subdivision_minimum_lease_area <= 0:
                raise ValueError(
                    "'subdivision_minimum_lease_area' must be a positive value if set."
                )
            if self.subdivision_minimum_lease_area is not None and self.subdivision_average_lease_area < self.subdivision_minimum_lease_area:
                raise ValueError(
                    "'subdivision_average_lease_area' cannot be less than 'subdivision_minimum_lease_area'."
                )
        return self


# --- Rent Roll ---
class RentRoll(Model):
    """
    Collection of all defined lease specifications and vacant spaces.

    Attributes:
        leases: List of LeaseSpec objects defining initial lease terms.
        vacant_suites: List of all vacant suites at the start.
    """

    leases: List[LeaseSpec]
    vacant_suites: List[VacantSuite]

    @property
    def total_occupied_area(self) -> PositiveFloat:
        """Calculate total area defined in the lease specifications."""
        return sum(lease_spec.area for lease_spec in self.leases)

    @property
    def occupancy_rate(self) -> FloatBetween0And1:
        """Calculate initial occupancy rate based on LeaseSpec areas."""
        total_area = self.total_occupied_area + sum(
            suite.area for suite in self.vacant_suites
        )
        return self.total_occupied_area / total_area if total_area > 0 else 0.0

    @model_validator(mode="after")
    def validate_lease_tenant_mapping(self) -> "RentRoll":
        """Validate placeholder - tenant mapping validation might change with LeaseSpec."""
        # TODO: Review validation logic based on LeaseSpec (e.g., check tenant_name)
        return self

    # TODO: property for all suites
    # TODO: property for stacked floors data (to enable viz)
