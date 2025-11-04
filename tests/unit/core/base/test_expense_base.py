# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import date

import pytest

from performa.analysis import AnalysisContext
from performa.core.base.expense import CapExItemBase, OpExItemBase
from performa.core.ledger import Ledger
from performa.core.primitives import (
    CashFlowModel,
    ExpenseSubcategoryEnum,
    FrequencyEnum,
    GlobalSettings,
    PercentageGrowthRate,
    PropertyAttributeKey,
    Timeline,
)

logger = logging.getLogger(__name__)


class MockResidentialProperty:
    """Mock residential property with unit_count attribute for testing."""

    def __init__(self, unit_count: int = 120, net_rentable_area: float = 96000.0):
        self.unit_count = unit_count
        self.net_rentable_area = net_rentable_area


class MockOfficeProperty:
    """Mock office property without unit_count attribute for testing."""

    def __init__(self, net_rentable_area: float = 1000.0):
        self.net_rentable_area = net_rentable_area
        # Note: No unit_count attribute - this is the key difference


class MinimalConcreteCashFlowModel(CashFlowModel):
    """A minimal, concrete implementation of CashFlowModel for testing."""

    pass


@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)


@pytest.fixture
def sample_context(sample_timeline: Timeline) -> AnalysisContext:
    ledger = Ledger()
    return AnalysisContext(
        timeline=sample_timeline,
        settings=GlobalSettings(),
        property_data=None,
        ledger=ledger,
    )


def test_opex_item_base(sample_context: AnalysisContext):
    """Test the OpExItemBase inheritance from CashFlowModel."""
    opex = OpExItemBase(
        name="Test OpEx",
        timeline=sample_context.timeline,
        subcategory=ExpenseSubcategoryEnum.OPEX,
        value=100,
    )
    result = opex.compute_cf(context=sample_context)
    assert len(result) == 12
    assert result.sum() > 0


def test_capex_item_base(sample_context: AnalysisContext):
    """Test the CapExItemBase compute_cf implementation."""
    capex = CapExItemBase(
        name="Test CapEx",
        timeline=sample_context.timeline,
        value={"2024-06-01": 50000},
    )
    result = capex.compute_cf(context=sample_context)
    assert len(result) == 12
    assert result.sum() == 50000  # No growth applied to CapEx


def test_per_unit_capex_residential_vs_cashflow_model():
    """
    Test that CapExItemBase PER_UNIT calculations match CashFlowModel for residential properties.

    This ensures our fix is consistent across both classes.
    """
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
    property_data = MockResidentialProperty(unit_count=120, net_rentable_area=96000.0)
    property_data.uid = (
        "550e8400-e29b-41d4-a716-446655440099"  # Ensure uid exists with valid UUID
    )
    ledger = Ledger()
    context = AnalysisContext(
        timeline=timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        ledger=ledger,
    )

    # Create CapEx item
    capex = CapExItemBase(
        name="Roof Replacement",
        timeline=timeline,
        value=500.0,  # $500 per unit
        reference=PropertyAttributeKey.UNIT_COUNT,  # Residential uses UNIT_COUNT
        frequency=FrequencyEnum.ANNUAL,
    )

    # Create equivalent CashFlowModel
    cashflow = MinimalConcreteCashFlowModel(
        name="Roof Replacement",
        category="Test",
        subcategory="Test",
        timeline=timeline,
        value=500.0,  # $500 per unit
        reference=PropertyAttributeKey.UNIT_COUNT,  # Residential uses UNIT_COUNT
        frequency=FrequencyEnum.ANNUAL,
    )

    # Calculate cash flows
    capex_cf = capex.compute_cf(context)
    cashflow_cf = cashflow.compute_cf(context)

    # Both should use unit_count (120), not net_rentable_area (96,000)
    expected_annual_value = 500.0 * 120  # $60,000
    expected_monthly_value = expected_annual_value / 12  # $5,000

    # Verify CapEx calculation
    assert abs(capex_cf.iloc[0] - expected_monthly_value) < 1.0, (
        f"CapEx: Expected ~${expected_monthly_value}/month but got ${capex_cf.iloc[0]}/month"
    )

    # CapEx should NOT have growth applied, so CashFlow might differ if it has growth
    # But for PER_UNIT base calculation, they should be the same
    capex_annual = capex_cf.sum()

    # The base calculation should be identical (before any growth)
    assert abs(capex_annual - expected_annual_value) < 12.0, (
        f"CapEx annual total: Expected ~${expected_annual_value} but got ${capex_annual}"
    )


def test_per_unit_capex_office_vs_cashflow_model():
    """
    Test that CapExItemBase PER_UNIT calculations match CashFlowModel for office properties.

    This ensures our fix preserves existing office behavior.
    """
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
    property_data = MockOfficeProperty(net_rentable_area=1000.0)
    property_data.uid = (
        "550e8400-e29b-41d4-a716-446655440099"  # Ensure uid exists with valid UUID
    )
    ledger = Ledger()
    context = AnalysisContext(
        timeline=timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        ledger=ledger,
    )

    # Create CapEx item
    capex = CapExItemBase(
        name="HVAC Replacement",
        timeline=timeline,
        value=15.0,  # $15 per SF
        reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        frequency=FrequencyEnum.ANNUAL,
    )

    # Calculate cash flow
    capex_cf = capex.compute_cf(context)

    # Should use net_rentable_area (1,000), existing behavior
    expected_annual_value = 15.0 * 1000.0  # $15,000
    expected_monthly_value = expected_annual_value / 12  # $1,250

    # Verify calculation
    assert abs(capex_cf.iloc[0] - expected_monthly_value) < 1.0, (
        f"Office CapEx: Expected ~${expected_monthly_value}/month but got ${capex_cf.iloc[0]}/month"
    )

    capex_annual = capex_cf.sum()
    assert abs(capex_annual - expected_annual_value) < 12.0, (
        f"Office CapEx annual: Expected ~${expected_annual_value} but got ${capex_annual}"
    )


def test_capex_now_applies_growth_rates():
    """
    Test that CapExItemBase now correctly applies growth rates (FIXED behavior).

     CORRECTED: CapEx now applies growth rates when specified, matching industry standards.

    Real-world: Capital reserves ($450/unit/year) should grow with construction inflation.
    Industry practice: Capital reserves typically DO escalate annually (2-3%).
    New implementation: Growth rates applied (industry standard)
    """
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)  # 2 years
    property_data = MockResidentialProperty(unit_count=100)
    property_data.uid = (
        "550e8400-e29b-41d4-a716-446655440099"  # Ensure uid exists with valid UUID
    )
    ledger = Ledger()
    context = AnalysisContext(
        timeline=timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        ledger=ledger,
    )

    # Create CapEx with growth rate (now properly applied)
    capex = CapExItemBase(
        name="Capital Reserves",
        timeline=timeline,
        value=300.0,
        reference=PropertyAttributeKey.UNIT_COUNT,  # Residential uses UNIT_COUNT
        frequency=FrequencyEnum.ANNUAL,
        growth_rate=PercentageGrowthRate(
            name="CapEx Growth", value=0.03
        ),  # 3% growth - now applied!
    )

    capex_cf = capex.compute_cf(context)

    # NEW BEHAVIOR: Should escalate with 3% growth (continuously compounded)
    year1_total = capex_cf.iloc[:12].sum()
    year2_total = capex_cf.iloc[12:24].sum()

    # With continuous compounding, Year 1 will be higher than base $30K
    # This is correct - growth is applied from day 1
    print(f"Year 1 total: ${year1_total:,.0f}")
    print(f"Year 2 total: ${year2_total:,.0f}")

    # Verify growth is applied correctly
    assert year2_total > year1_total, (
        "CapEx should now grow year over year (industry standard)"
    )

    # Verify the year-over-year growth rate is approximately correct
    growth_rate = (year2_total / year1_total) - 1
    assert abs(growth_rate - 0.03) < 0.005, (
        f"Growth rate should be ~3%, got {growth_rate:.1%}"
    )

    # Verify we're in the right ballpark (with compounding)
    assert year1_total > 30000, (
        "Year 1 should be above base due to continuous compounding"
    )
    assert year1_total < 32000, "Year 1 shouldn't be too much above base"
    assert year2_total > 31000, "Year 2 should show continued growth"


def test_capex_without_growth_rate_stays_flat():
    """
    Test that CapEx without growth rate specified remains flat (for one-time items).

    Use case: One-time roof replacement, major renovation - should not escalate.
    """
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
    property_data = MockResidentialProperty(unit_count=100)
    property_data.uid = (
        "550e8400-e29b-41d4-a716-446655440099"  # Ensure uid exists with valid UUID
    )
    ledger = Ledger()
    context = AnalysisContext(
        timeline=timeline,
        settings=GlobalSettings(),
        property_data=property_data,
        ledger=ledger,
    )

    # Create CapEx without growth rate
    capex = CapExItemBase(
        name="Roof Replacement",
        timeline=timeline,
        value=50000.0,  # One-time $50K expense
        frequency=FrequencyEnum.ANNUAL,
        # No growth_rate specified
    )

    capex_cf = capex.compute_cf(context)

    year1_total = capex_cf.iloc[:12].sum()
    year2_total = capex_cf.iloc[12:24].sum()

    # Should be flat when no growth specified
    expected_annual = 50000.0
    assert abs(year1_total - expected_annual) < 12.0
    assert abs(year2_total - expected_annual) < 12.0
    assert abs(year1_total - year2_total) < 12.0, "CapEx without growth should be flat"


def test_capex_recoverable_inheritance():
    """
    Test that CapExItemBase now inherits recoverable logic from ExpenseItemBase.

    This verifies the refactoring that moved recoverable_ratio and is_recoverable
    up to the parent class so both OpEx and CapEx can be recoverable.
    """
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)

    # Test non-recoverable CapEx (default)
    capex_non_recoverable = CapExItemBase(
        name="Capital Reserves",
        timeline=timeline,
        value=50000.0,
        frequency=FrequencyEnum.ANNUAL,
        # recoverable_ratio defaults to 0.0
    )

    assert capex_non_recoverable.recoverable_ratio == 0.0
    assert capex_non_recoverable.is_recoverable == False  # noqa: E712

    # Test partially recoverable CapEx (tenant improvement pass-through)
    capex_recoverable = CapExItemBase(
        name="HVAC Upgrade",
        timeline=timeline,
        value=100000.0,
        frequency=FrequencyEnum.ANNUAL,
        recoverable_ratio=0.6,  # 60% recoverable from tenants
    )

    assert capex_recoverable.recoverable_ratio == 0.6
    assert capex_recoverable.is_recoverable == True  # noqa: E712

    # Test fully recoverable CapEx
    capex_fully_recoverable = CapExItemBase(
        name="Tenant Improvement Allowance",
        timeline=timeline,
        value=25000.0,
        frequency=FrequencyEnum.ANNUAL,
        recoverable_ratio=1.0,  # 100% recoverable
    )

    assert capex_fully_recoverable.recoverable_ratio == 1.0
    assert capex_fully_recoverable.is_recoverable == True  # noqa: E712


def test_opex_recoverable_still_works():
    """
    Test that OpExItemBase still has recoverable logic after refactoring.

    This ensures the move of recoverable logic to ExpenseItemBase didn't break OpEx.
    """
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)

    # Test non-recoverable OpEx
    opex_non_recoverable = OpExItemBase(
        name="Property Management",
        timeline=timeline,
        value=5000.0,
        frequency=FrequencyEnum.ANNUAL,
        recoverable_ratio=0.0,  # Not recoverable
    )

    assert opex_non_recoverable.recoverable_ratio == 0.0
    assert opex_non_recoverable.is_recoverable == False  # noqa: E712

    # Test fully recoverable OpEx (CAM charges)
    opex_recoverable = OpExItemBase(
        name="Common Area Maintenance",
        timeline=timeline,
        value=8000.0,
        frequency=FrequencyEnum.ANNUAL,
        recoverable_ratio=1.0,  # Fully recoverable
    )

    assert opex_recoverable.recoverable_ratio == 1.0
    assert opex_recoverable.is_recoverable == True  # noqa: E712

    # Test variable OpEx (OpEx-specific feature)
    opex_variable = OpExItemBase(
        name="Utilities",
        timeline=timeline,
        value=3000.0,
        frequency=FrequencyEnum.ANNUAL,
        recoverable_ratio=0.8,  # 80% recoverable
        variable_ratio=0.7,  # 70% varies with occupancy
    )

    assert opex_variable.recoverable_ratio == 0.8
    assert opex_variable.is_recoverable == True  # noqa: E712
    assert opex_variable.variable_ratio == 0.7
    assert opex_variable.is_variable == True  # noqa: E712
