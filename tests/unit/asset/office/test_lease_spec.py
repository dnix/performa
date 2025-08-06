# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pytest

from performa.asset.office.lease_spec import OfficeLeaseSpec
from performa.core.primitives import (
    LeaseTypeEnum,
    PropertyAttributeKey,
    UponExpirationEnum,
)


def test_lease_spec_computed_end_date():
    spec = OfficeLeaseSpec(
        tenant_name="Test",
        suite="100",
        floor="1",
        area=1000,
        use_type="office",
        lease_type=LeaseTypeEnum.NET,
        upon_expiration=UponExpirationEnum.MARKET,
        start_date=date(2024, 1, 15),
        term_months=24,
        base_rent_value=10,
        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
    )
    assert spec.computed_end_date == date(2025, 12, 31)


def test_lease_spec_computed_term_months():
    spec = OfficeLeaseSpec(
        tenant_name="Test",
        suite="100",
        floor="1",
        area=1000,
        use_type="office",
        lease_type=LeaseTypeEnum.NET,
        upon_expiration=UponExpirationEnum.MARKET,
        start_date=date(2024, 1, 1),
        end_date=date(2025, 12, 31),
        base_rent_value=10,
        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
    )
    assert spec.computed_term_months == 24


def test_lease_spec_term_validation():
    with pytest.raises(
        ValueError, match="Either end_date or term_months must be provided"
    ):
        OfficeLeaseSpec(
            tenant_name="Test",
            suite="100",
            floor="1",
            area=1000,
            use_type="office",
            lease_type=LeaseTypeEnum.NET,
            upon_expiration=UponExpirationEnum.MARKET,
            start_date=date(2024, 1, 1),
            base_rent_value=10,
            base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        )

    with pytest.raises(ValueError, match="end_date must be after start_date"):
        OfficeLeaseSpec(
            tenant_name="Test",
            suite="100",
            floor="1",
            area=1000,
            use_type="office",
            lease_type=LeaseTypeEnum.NET,
            upon_expiration=UponExpirationEnum.MARKET,
            start_date=date(2024, 1, 1),
            end_date=date(2023, 12, 31),
            base_rent_value=10,
            base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        )
