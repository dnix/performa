# src/performa/asset/office/property.py 
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import computed_field

from ...common.base import PropertyBaseModel, VacantSuiteBase
from ...common.primitives import Model
from .absorption import OfficeAbsorptionPlan
from .expense import OfficeExpenses
from .lease_spec import OfficeLeaseSpec
from .losses import OfficeLosses
from .misc_income import OfficeMiscIncome
from .rent_roll import OfficeRentRoll
from .tenant import OfficeTenant


class RentRoll(Model):
    """
    A container for the rent roll, holding lists of both
    in-place lease specifications and vacant suites.
    """

    leases: List[OfficeLeaseSpec] = []
    vacant_suites: List[VacantSuiteBase] = []

    @property
    def total_occupied_area(self) -> float:
        return sum(lease.area for lease in self.leases)


class PropertySuite(Model):
    suite_id: str
    area: float
    tenant: Optional[OfficeTenant] = None


class PropertyFloor(Model):
    number: int
    area: float
    tenants: List[OfficeTenant]


class OfficeProperty(PropertyBaseModel):
    """
    Represents the full data model for an office property.
    """

    rent_roll: OfficeRentRoll
    losses: OfficeLosses
    miscellaneous_income: List[OfficeMiscIncome] = []
    expenses: OfficeExpenses
    absorption_plans: List[OfficeAbsorptionPlan] = []

    @property
    def suites(self) -> List[PropertySuite]:
        leased_suites = [
            PropertySuite(
                suite_id=lease.suite,
                area=lease.area,
                tenant=OfficeTenant(id=lease.tenant_name, name=lease.tenant_name)
            ) for lease in self.rent_roll.leases
        ]
        vacant_suites = [
            PropertySuite(
                suite_id=suite.suite,
                area=suite.area,
                tenant=None
            ) for suite in self.rent_roll.vacant_suites
        ]
        return leased_suites + vacant_suites

    @property
    def floors(self) -> List[PropertyFloor]:
        floor_tenants: Dict[str, List[OfficeTenant]] = {}
        floor_areas: Dict[str, float] = {}
        for lease in self.rent_roll.leases:
            if lease.floor:
                if lease.floor not in floor_tenants:
                    floor_tenants[lease.floor] = []
                    floor_areas[lease.floor] = 0
                floor_tenants[lease.floor].append(OfficeTenant(id=lease.tenant_name, name=lease.tenant_name))
                floor_areas[lease.floor] += lease.area
        return [
            PropertyFloor(
                number=int(floor_num) if floor_num.isdigit() else 0,
                area=floor_areas[floor_num],
                tenants=tenants,
            )
            for floor_num, tenants in floor_tenants.items()
        ]

    @computed_field
    @property
    def occupied_area(self) -> float:
        """Calculate total occupied area from the rent roll."""
        return self.rent_roll.total_occupied_area

    @computed_field
    @property
    def vacant_area(self) -> float:
        """Calculate total vacant area."""
        # FIXME: review this calculation
        total_vacant_area = sum(suite.area for suite in self.rent_roll.vacant_suites)
        # As a sanity check, can also be calculated against NRA
        calculated_vacant = self.net_rentable_area - self.occupied_area
        # In a real model, you might log a warning if these don't match
        return calculated_vacant

    @computed_field
    @property
    def occupancy_rate(self) -> float:
        """Calculate current occupancy rate."""
        if self.net_rentable_area == 0:
            return 0.0
        return self.occupied_area / self.net_rentable_area 