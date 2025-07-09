from __future__ import annotations

from typing import List, Optional

from pydantic import Field, PositiveFloat, computed_field, model_validator

from ...core.base import VacantSuiteBase
from ...core.primitives import Model, ProgramUseEnum
from .lease_spec import OfficeLeaseSpec


class OfficeVacantSuite(VacantSuiteBase):
    """
    Represents a vacant office suite, with support for subdivision.
    """
    is_divisible: bool = Field(default=False)
    subdivision_average_lease_area: Optional[PositiveFloat] = Field(default=None)
    subdivision_minimum_lease_area: Optional[PositiveFloat] = Field(default=None)
    subdivision_naming_pattern: str = Field(default="{master_suite_id}-Sub{count}")

    @model_validator(mode='after')
    def _validate_subdivision(self) -> "OfficeVacantSuite":
        if self.is_divisible:
            if self.subdivision_average_lease_area is None:
                raise ValueError("'subdivision_average_lease_area' must be set if 'is_divisible' is True.")
            if self.subdivision_average_lease_area <= 0:
                raise ValueError("'subdivision_average_lease_area' must be a positive value.")
            if self.subdivision_average_lease_area > self.area:
                raise ValueError("'subdivision_average_lease_area' cannot be greater than the total suite area.")
            if self.subdivision_minimum_lease_area is not None:
                if self.subdivision_minimum_lease_area <= 0:
                    raise ValueError("'subdivision_minimum_lease_area' must be a positive value if set.")
                if self.subdivision_average_lease_area < self.subdivision_minimum_lease_area:
                    raise ValueError("'subdivision_average_lease_area' cannot be less than 'subdivision_minimum_lease_area'.")
        return self

class OfficeRentRoll(Model):
    """
    Collection of all defined lease specifications and vacant spaces for an office property.
    """
    leases: List[OfficeLeaseSpec]
    vacant_suites: List[OfficeVacantSuite]

    @computed_field
    @property
    def total_occupied_area(self) -> float:
        """Calculate total area defined in the lease specifications."""
        return sum(lease_spec.area for lease_spec in self.leases)

    @computed_field
    @property
    def total_vacant_area(self) -> float:
        """Calculate total area of all vacant suites."""
        return sum(suite.area for suite in self.vacant_suites)
    
    @computed_field
    @property
    def total_area(self) -> float:
        return self.total_occupied_area + self.total_vacant_area

    @computed_field
    @property
    def occupancy_rate(self) -> float:
        """Calculate initial occupancy rate."""
        total_area = self.total_area
        return self.total_occupied_area / total_area if total_area > 0 else 0.0 