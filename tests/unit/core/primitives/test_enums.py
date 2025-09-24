# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from performa.core.primitives import (
    AssetTypeEnum,
    FrequencyEnum,
    LeveredAggregateLineKey,
    PropertyAttributeKey,
    UnleveredAggregateLineKey,
)


def test_enum_member_values():
    """Test that some key enum members have the correct string value."""
    assert FrequencyEnum.ANNUAL == "annual"
    assert PropertyAttributeKey.UNIT_COUNT == "unit_count"
    assert AssetTypeEnum.OFFICE == "office"
    assert UnleveredAggregateLineKey.NET_OPERATING_INCOME == "Net Operating Income"


def test_unlevered_aggregate_line_key_functionality():
    """Test UnleveredAggregateLineKey enum functionality."""
    # Test key unlevered line items exist
    assert UnleveredAggregateLineKey.NET_OPERATING_INCOME == "Net Operating Income"
    assert (
        UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES == "Total Operating Expenses"
    )
    assert UnleveredAggregateLineKey.UNLEVERED_CASH_FLOW == "Unlevered Cash Flow"

    # Test from_value method still works
    noi_key = UnleveredAggregateLineKey.NET_OPERATING_INCOME
    assert UnleveredAggregateLineKey.from_value("Net Operating Income") == noi_key
    assert UnleveredAggregateLineKey.from_value("NonExistentKey") is None


def test_levered_aggregate_line_key_functionality():
    """Test LeveredAggregateLineKey enum functionality."""
    # Test key levered line items exist
    assert LeveredAggregateLineKey.TOTAL_DEBT_SERVICE == "Total Debt Service"
    assert LeveredAggregateLineKey.LEVERED_CASH_FLOW == "Levered Cash Flow"

    # Test from_value method still works
    debt_key = LeveredAggregateLineKey.TOTAL_DEBT_SERVICE
    assert LeveredAggregateLineKey.from_value("Total Debt Service") == debt_key
    assert LeveredAggregateLineKey.from_value("NonExistentKey") is None


def test_architectural_separation():
    """Test that unlevered and levered enums maintain proper separation."""
    # UnleveredAggregateLineKey should NOT have levered concepts
    unlevered_values = [key.value for key in UnleveredAggregateLineKey]
    assert "Total Debt Service" not in unlevered_values
    assert "Levered Cash Flow" not in unlevered_values

    # LeveredAggregateLineKey should NOT have unlevered concepts (only financing)
    levered_values = [key.value for key in LeveredAggregateLineKey]
    assert "Net Operating Income" not in levered_values
    assert "Total Operating Expenses" not in levered_values
    assert "Unlevered Cash Flow" not in levered_values

    # Verify the keys exist in the right places
    assert "Unlevered Cash Flow" in unlevered_values
    assert "Levered Cash Flow" in levered_values


def test_legacy_enum_removed():
    """Test that the legacy AggregateLineKey enum has been completely removed."""
    # Verify the old enum is no longer importable
    try:
        # This import should fail
        exec("from performa.core.primitives.enums import AggregateLineKey")
        assert (
            False
        ), "AggregateLineKey should have been removed but is still importable"
    except ImportError:
        pass  # This is expected

    # Verify the new type-safe enums work correctly
    unlevered_values = [key.value for key in UnleveredAggregateLineKey]
    levered_values = [key.value for key in LeveredAggregateLineKey]

    # Verify separation is maintained
    assert "Net Operating Income" in unlevered_values
    assert "Total Operating Expenses" in unlevered_values
    assert "Unlevered Cash Flow" in unlevered_values

    assert "Total Debt Service" in levered_values
    assert "Levered Cash Flow" in levered_values

    # Verify no overlap
    assert "Total Debt Service" not in unlevered_values
    assert "Net Operating Income" not in levered_values
