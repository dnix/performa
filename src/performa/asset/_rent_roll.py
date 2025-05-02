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
from ._lease import Lease

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
    Collection of all leases and vacant spaces.
    
    Attributes:
        leases: List of all lease agreements
        vacant_suites: List of all vacant suites
    """
    leases: List[Lease] # Needs Lease import
    vacant_suites: List[VacantSuite]

    @property
    def total_occupied_area(self) -> PositiveFloat:
        """Calculate total leased area in square feet."""
        return sum(lease.area for lease in self.leases)

    @property
    def occupancy_rate(self) -> FloatBetween0And1:
        """Calculate current occupancy rate as a decimal between 0 and 1."""
        total_area = self.total_occupied_area + sum(
            suite.area for suite in self.vacant_suites
        )
        return self.total_occupied_area / total_area if total_area > 0 else 0.0

    @model_validator(mode="after")
    def validate_lease_tenant_mapping(self) -> "RentRoll":
        """Validate that all leases have a corresponding tenant."""
        # TODO: implement this
        return self

    # TODO: add validation for total area
    # TODO: property for all suites
    # TODO: property for stacked floors data (to enable viz)
