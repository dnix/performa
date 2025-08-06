# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pytest

from performa.core.base import MiscIncomeBase
from performa.core.primitives import (
    RevenueSubcategoryEnum,
    Timeline,
)


@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)


def test_misc_income_base_instantiation(sample_timeline: Timeline):
    """Test successful instantiation of MiscIncomeBase."""
    item = MiscIncomeBase(
        name="Parking Income",
        timeline=sample_timeline,
        value=5000,
    )
    assert item.name == "Parking Income"
    assert item.subcategory == RevenueSubcategoryEnum.MISC
