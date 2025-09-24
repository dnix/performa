# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pytest

from performa.asset.office.lease_spec import OfficeLeaseSpec
from performa.asset.office.rent_roll import OfficeRentRoll, OfficeVacantSuite
from performa.core.primitives import PropertyAttributeKey


def test_office_vacant_suite_validation():
    # This should work
    OfficeVacantSuite(
        suite="101",
        floor="1",
        area=1000,
        use_type="office",
        is_divisible=True,
        subdivision_average_lease_area=200,
    )

    # This should fail because average area is missing
    with pytest.raises(
        ValueError, match="'subdivision_average_lease_area' must be set"
    ):
        OfficeVacantSuite(
            suite="101", floor="1", area=1000, use_type="office", is_divisible=True
        )

    # This should fail because average is larger than total
    with pytest.raises(
        ValueError, match="'subdivision_average_lease_area' cannot be greater"
    ):
        OfficeVacantSuite(
            suite="101",
            floor="1",
            area=1000,
            use_type="office",
            is_divisible=True,
            subdivision_average_lease_area=1200,
        )


def test_office_rent_roll_properties():
    lease1 = OfficeLeaseSpec(
        tenant_name="T1",
        suite="101",
        floor="1",
        area=1000,
        use_type="office",
        start_date=date(2024, 1, 1),
        end_date=date(2025, 1, 1),
        base_rent_value=10,
        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        lease_type="net",
        upon_expiration="market",
    )
    lease2 = OfficeLeaseSpec(
        tenant_name="T2",
        suite="102",
        floor="1",
        area=2000,
        use_type="office",
        start_date=date(2024, 1, 1),
        end_date=date(2025, 1, 1),
        base_rent_value=10,
        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        lease_type="net",
        upon_expiration="market",
    )
    vacant_suite = OfficeVacantSuite(
        suite="103", floor="1", area=500, use_type="office"
    )

    rent_roll = OfficeRentRoll(leases=[lease1, lease2], vacant_suites=[vacant_suite])

    assert rent_roll.total_occupied_area == 3000.0
    assert rent_roll.total_vacant_area == 500.0
    assert rent_roll.total_area == 3500.0
    assert pytest.approx(rent_roll.occupancy_rate) == 3000.0 / 3500.0
