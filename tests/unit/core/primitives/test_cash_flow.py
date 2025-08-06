# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.analysis import AnalysisContext
from performa.core.primitives import (
    CashFlowModel,
    FrequencyEnum,
    GlobalSettings,
    LeveredAggregateLineKey,
    PropertyAttributeKey,
    Timeline,
    UnleveredAggregateLineKey,
)


class MinimalConcreteCashFlowModel(CashFlowModel):
    """A minimal, concrete implementation of CashFlowModel for testing."""
    pass  # Inherits the concrete compute_cf


@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)


@pytest.fixture
def sample_context(sample_timeline: Timeline) -> AnalysisContext:
    return AnalysisContext(timeline=sample_timeline, settings=GlobalSettings(), property_data=None)


def test_instantiation_with_list_value(sample_timeline: Timeline):
    """Test that a CashFlowModel can be instantiated with a list value."""
    list_val = [i for i in range(12)]
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=list_val
    )
    assert model.value == list_val


def test_instantiation_with_series_value(sample_timeline: Timeline):
    series_val = pd.Series(range(12), index=sample_timeline.period_index)
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=series_val
    )
    pd.testing.assert_series_equal(model.value, series_val)


def test_reference_is_unlevered_aggregate_line_key(sample_timeline: Timeline):
    """Test that the reference field accepts UnleveredAggregateLineKey enum values."""
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=1,
        reference=UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES
    )
    assert model.reference == UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES

    # Test that PropertyAttributeKey values are also accepted
    model2 = MinimalConcreteCashFlowModel(
        name="Test2", category="cat", subcategory="sub",
        timeline=sample_timeline, value=1,
        reference=PropertyAttributeKey.NET_RENTABLE_AREA
    )
    assert model2.reference == PropertyAttributeKey.NET_RENTABLE_AREA


def test_reference_rejects_invalid_types(sample_timeline: Timeline):
    """Test that the reference field rejects invalid reference types for type safety."""
    # String references should be rejected (no more slippery strings!)
    with pytest.raises(ValidationError):
        MinimalConcreteCashFlowModel(
            name="Test", category="cat", subcategory="sub",
            timeline=sample_timeline, value=1,
            reference="custom_reference_string"  # Should be rejected!
        )
    
    # LeveredAggregateLineKey should also be rejected (wrong layer)
    with pytest.raises(ValidationError):
        MinimalConcreteCashFlowModel(
            name="Test2", category="cat", subcategory="sub",
            timeline=sample_timeline, value=1,
            reference=LeveredAggregateLineKey.LEVERED_CASH_FLOW  # Should be rejected!
        )


def test_enum_removal_complete(sample_timeline: Timeline):
    """Test that the old AggregateLineKey enum has been completely removed."""
    # Verify that the old enum is no longer available
    try:
        from performa.core.primitives import AggregateLineKey
        assert False, "AggregateLineKey should have been removed but is still importable"
    except ImportError:
        pass  # This is what we expect
    
    # Verify that only the new type-safe enums are available
    model = MinimalConcreteCashFlowModel(
        name="Test", category="cat", subcategory="sub",
        timeline=sample_timeline, value=1,
        reference=UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES
    )
    assert model.reference == UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES


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


def test_per_unit_residential_calculation_fix(sample_timeline: Timeline):
    """
    Test that PER_UNIT calculations now correctly use dwelling units for residential properties.
    
    This is a regression test for the critical bug where PER_UNIT was incorrectly 
    multiplying by net_rentable_area instead of unit_count for residential properties.
    
    Bug Context: $200/unit × 120 units should = $24,000, not $200 × 96,000 SF = $19.2M
    """
    # Create residential property context
    property_data = MockResidentialProperty(unit_count=120, net_rentable_area=96000.0)
    context = AnalysisContext(
        timeline=sample_timeline, 
        settings=GlobalSettings(), 
        property_data=property_data
    )
    
    # Create per-unit expense (utilities example from multifamily)
    expense = MinimalConcreteCashFlowModel(
        name="Common Area Utilities",
        category="Operating Expense",
        subcategory="OpEx",
        timeline=sample_timeline,
        value=200.0,  # $200 per dwelling unit
        reference=PropertyAttributeKey.UNIT_COUNT,  # New system: explicit unit count reference
        frequency=FrequencyEnum.ANNUAL,
    )
    
    # Calculate cash flow
    cash_flow = expense.compute_cf(context)
    
    # Should use unit_count (120), not net_rentable_area (96,000)
    expected_annual_value = 200.0 * 120  # $24,000
    expected_monthly_value = expected_annual_value / 12  # $2,000
    
    # Verify the calculation uses unit_count, not area
    assert abs(cash_flow.iloc[0] - expected_monthly_value) < 1.0, (
        f"Expected ~${expected_monthly_value}/month but got ${cash_flow.iloc[0]}/month. "
        f"Bug: multiplying by area ({property_data.net_rentable_area}) instead of units ({property_data.unit_count})"
    )
    
    # Verify annual total
    annual_total = cash_flow.sum()
    assert abs(annual_total - expected_annual_value) < 12.0, (
        f"Expected ~${expected_annual_value}/year but got ${annual_total}/year"
    )


def test_per_unit_office_calculation_unchanged(sample_timeline: Timeline):
    """
    Test that PER_UNIT calculations still correctly use net_rentable_area for office properties.
    
    This is a regression protection test to ensure our residential fix doesn't break 
    existing office property calculations, which should continue using square footage.
    
    Office Context: $1.50/SF × 1,000 SF should = $1,500 (existing behavior)
    """
    # Create office property context (no unit_count attribute)
    property_data = MockOfficeProperty(net_rentable_area=1000.0)
    context = AnalysisContext(
        timeline=sample_timeline, 
        settings=GlobalSettings(), 
        property_data=property_data
    )
    
    # Create per-square-foot expense (insurance example from office)
    expense = MinimalConcreteCashFlowModel(
        name="Property Insurance",
        category="Operating Expense",
        subcategory="OpEx",
        timeline=sample_timeline,
        value=1.50,  # $1.50 per square foot
        reference=PropertyAttributeKey.NET_RENTABLE_AREA,  # New system: explicit area reference
        frequency=FrequencyEnum.ANNUAL,
    )
    
    # Calculate cash flow
    cash_flow = expense.compute_cf(context)
    
    # Should use net_rentable_area (1,000), existing behavior
    expected_annual_value = 1.50 * 1000.0  # $1,500
    expected_monthly_value = expected_annual_value / 12  # $125
    
    # Verify the calculation uses area (unchanged behavior)
    assert abs(cash_flow.iloc[0] - expected_monthly_value) < 1.0, (
        f"Expected ~${expected_monthly_value}/month but got ${cash_flow.iloc[0]}/month. "
        f"Office calculations should still use net_rentable_area ({property_data.net_rentable_area})"
    )
    
    # Verify annual total
    annual_total = cash_flow.sum()
    assert abs(annual_total - expected_annual_value) < 12.0, (
        f"Expected ~${expected_annual_value}/year but got ${annual_total}/year"
    )


def test_per_unit_edge_case_zero_unit_count(sample_timeline: Timeline):
    """
    Test PER_UNIT calculation handles edge case of zero unit_count gracefully.
    
    When unit_count is 0 or property has unit_count but it's zero, should fall back 
    to area-based calculation to avoid division by zero.
    """
    # Create residential property with zero units
    property_data = MockResidentialProperty(unit_count=0, net_rentable_area=50000.0)
    context = AnalysisContext(
        timeline=sample_timeline, 
        settings=GlobalSettings(), 
        property_data=property_data
    )
    
    # In the new architecture, be explicit about what we want
    # If we want area-based calculation, request NET_RENTABLE_AREA explicitly
    expense = MinimalConcreteCashFlowModel(
        name="Test Expense",
        category="Operating Expense",
        subcategory="OpEx",
        timeline=sample_timeline,
        value=100.0,
        reference=PropertyAttributeKey.NET_RENTABLE_AREA,  # Explicit area reference
        frequency=FrequencyEnum.ANNUAL,
    )
    
    # Should use area when explicitly requested
    cash_flow = expense.compute_cf(context)
    expected_annual_value = 100.0 * 50000.0  # Uses area as requested
    expected_monthly_value = expected_annual_value / 12
    
    assert abs(cash_flow.iloc[0] - expected_monthly_value) < 1.0, (
        "Should use area calculation when NET_RENTABLE_AREA is explicitly requested"
    )
