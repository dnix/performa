# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pytest

from performa.asset.office.expense import OfficeExpenses
from performa.asset.office.lease_spec import OfficeLeaseSpec
from performa.asset.office.losses import (
    OfficeCollectionLoss,
    OfficeGeneralVacancyLoss,
    OfficeLosses,
)
from performa.asset.office.property import OfficeProperty
from performa.asset.office.rent_roll import OfficeRentRoll
from performa.core.primitives import AssetTypeEnum


@pytest.fixture
def sample_property():
    lease1 = OfficeLeaseSpec(tenant_name="T1", suite="101", floor="1", area=1000, use_type="office", start_date=date(2024,1,1), end_date=date(2025,1,1), base_rent_value=10, base_rent_unit_of_measure="per_unit", lease_type="net", upon_expiration="market")
    lease2 = OfficeLeaseSpec(tenant_name="T2", suite="201", floor="2", area=2000, use_type="office", start_date=date(2024,1,1), end_date=date(2025,1,1), base_rent_value=10, base_rent_unit_of_measure="per_unit", lease_type="net", upon_expiration="market")
    rent_roll = OfficeRentRoll(leases=[lease1, lease2], vacant_suites=[])
    
    return OfficeProperty(
        name="Test Property",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=3000,
        net_rentable_area=3000,
        rent_roll=rent_roll,
        expenses=OfficeExpenses(),
        losses=OfficeLosses(
            general_vacancy=OfficeGeneralVacancyLoss(), 
            collection_loss=OfficeCollectionLoss()
        ),
    )

def test_property_suites(sample_property):
    suites = sample_property.suites
    assert len(suites) == 2
    assert suites[0].suite_id == "101"
    assert suites[1].tenant.name == "T2"

def test_property_floors(sample_property):
    floors = sample_property.floors
    assert len(floors) == 2
    
    floor1 = next(f for f in floors if f.number == 1)
    floor2 = next(f for f in floors if f.number == 2)

    assert floor1.area == 1000
    assert len(floor1.tenants) == 1
    assert floor2.area == 2000
    assert len(floor2.tenants) == 1
