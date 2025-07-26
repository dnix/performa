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
from performa.asset.office.rent_roll import OfficeRentRoll, OfficeVacantSuite
from performa.asset.office.tenant import OfficeTenant
from performa.core.primitives import (
    AssetTypeEnum,
    FrequencyEnum,
    LeaseTypeEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)


def test_office_tenant_creation():
    tenant = OfficeTenant(id="T1", name="Test Tenant 1")
    assert tenant.name == "Test Tenant 1"

def test_office_lease_spec_creation():
    spec = OfficeLeaseSpec(
        tenant_name="Test Tenant",
        suite="100",
        floor="1",
        area=1000.0,
        use_type="office",
        lease_type=LeaseTypeEnum.NET,
        start_date=date(2024, 1, 1),
        end_date=date(2025, 12, 31),
        base_rent_value=25.0,
        base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
        base_rent_frequency=FrequencyEnum.ANNUAL,
        upon_expiration=UponExpirationEnum.MARKET,
    )
    assert spec.area == 1000.0
    assert spec.lease_type == LeaseTypeEnum.NET

def test_office_rent_roll_properties():
    lease1 = OfficeLeaseSpec(tenant_name="T1", suite="101", floor="1", area=1000, use_type="office", start_date=date(2024,1,1), end_date=date(2025,1,1), base_rent_value=10, base_rent_unit_of_measure="per_unit", lease_type="net", upon_expiration="market")
    lease2 = OfficeLeaseSpec(tenant_name="T2", suite="102", floor="1", area=2000, use_type="office", start_date=date(2024,1,1), end_date=date(2025,1,1), base_rent_value=10, base_rent_unit_of_measure="per_unit", lease_type="net", upon_expiration="market")
    vacant_suite = OfficeVacantSuite(suite="103", floor="1", area=500, use_type="office")
    
    rent_roll = OfficeRentRoll(leases=[lease1, lease2], vacant_suites=[vacant_suite])
    
    assert rent_roll.total_occupied_area == 3000.0
    assert rent_roll.total_vacant_area == 500.0
    assert rent_roll.total_area == 3500.0
    assert pytest.approx(rent_roll.occupancy_rate) == 3000.0 / 3500.0

def test_office_property_properties():
    lease = OfficeLeaseSpec(tenant_name="T1", suite="101", floor="1", area=8000, use_type="office", start_date=date(2024,1,1), end_date=date(2025,1,1), base_rent_value=10, base_rent_unit_of_measure="per_unit", lease_type="net", upon_expiration="market")
    # Add explicit vacant suite to represent the 2,000 SF vacancy 
    vacant_suite = OfficeVacantSuite(suite="102", floor="1", area=2000, use_type="office")
    rent_roll = OfficeRentRoll(leases=[lease], vacant_suites=[vacant_suite])
    losses = OfficeLosses(
        general_vacancy=OfficeGeneralVacancyLoss(rate=0.05),
        collection_loss=OfficeCollectionLoss(rate=0.01),
    )
    expenses = OfficeExpenses()
    prop = OfficeProperty(
        name="Test Prop",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=10000.0,
        net_rentable_area=10000.0,
        rent_roll=rent_roll,
        losses=losses,
        expenses=expenses,
    )

    assert prop.occupied_area == 8000
    assert prop.vacant_area == 2000
    assert prop.occupancy_rate == 0.8 