from __future__ import annotations

import logging
from typing import List

from pydantic import model_validator

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
    """

    suite: str
    floor: str
    area: PositiveFloat
    use_type: ProgramUseEnum


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

    # TODO: add validation for total area
    # TODO: property for all suites
    # TODO: property for stacked floors data (to enable viz)
