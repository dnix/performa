# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from pydantic import Field, computed_field, model_validator

from ...core.base import PropertyBaseModel, VacantSuiteBase
from ...core.primitives import AssetTypeEnum, Model
from .absorption import OfficeAbsorptionPlan
from .expense import OfficeExpenses
from .lease_spec import OfficeLeaseSpec
from .losses import OfficeLosses
from .misc_income import OfficeMiscIncome
from .rent_roll import OfficeRentRoll
from .tenant import OfficeTenant

logger = logging.getLogger(__name__)


class RentRoll(Model):
    """
    A container for the rent roll, holding lists of both
    in-place lease specifications and vacant suites.
    """

    leases: List[OfficeLeaseSpec] = Field(default_factory=list)
    vacant_suites: List[VacantSuiteBase] = Field(default_factory=list)

    @computed_field
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

    # Real estate classification - this IS a property type (unlike DevelopmentProject)
    property_type: AssetTypeEnum = AssetTypeEnum.OFFICE
    
    rent_roll: OfficeRentRoll
    losses: OfficeLosses
    miscellaneous_income: List[OfficeMiscIncome] = Field(default_factory=list)
    expenses: OfficeExpenses
    absorption_plans: List[OfficeAbsorptionPlan] = Field(default_factory=list)

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
        """Calculate total vacant area from explicit vacant suites."""
        return self.rent_roll.total_vacant_area

    @computed_field
    @property
    def occupancy_rate(self) -> float:
        """Calculate current occupancy rate."""
        if self.net_rentable_area == 0:
            return 0.0
        return self.occupied_area / self.net_rentable_area

    @model_validator(mode='after')
    def _validate_area_consistency(self) -> "OfficeProperty":
        """
        Validate that rent roll total area matches net rentable area.
        
        Logs a warning if there's a meaningful discrepancy, which could indicate:
        - Missing vacant suites in the rent roll
        - Incorrect NRA specification  
        - Area calculation errors
        """
        rent_roll_total = self.rent_roll.total_area
        nra = self.net_rentable_area
        
        # Allow small rounding differences (0.1% tolerance)
        tolerance = 0.001
        if nra > 0 and abs(rent_roll_total - nra) / nra > tolerance:
            percentage_diff = abs(rent_roll_total - nra) / nra * 100
            logger.warning(
                f"Area inconsistency detected in property '{self.name}': "
                f"Rent roll total area ({rent_roll_total:,.0f} SF) differs from "
                f"Net Rentable Area ({nra:,.0f} SF) by {percentage_diff:.1f}%. "
                f"This may indicate missing vacant suites or incorrect NRA specification."
            )
        elif nra == 0 and rent_roll_total > 0:
            logger.warning(
                f"Area inconsistency detected in property '{self.name}': "
                f"Rent roll has {rent_roll_total:,.0f} SF but Net Rentable Area is 0. "
                f"This may indicate missing NRA specification."
            )
        
        return self 