from __future__ import annotations

from performa.common.primitives._enums import (
    AggregateLineKey,
    AssetTypeEnum,
    FrequencyEnum,
    UnitOfMeasureEnum,
)


def test_enum_member_values():
    """Test that some key enum members have the correct string value."""
    assert FrequencyEnum.ANNUAL == "annual"
    assert UnitOfMeasureEnum.PER_UNIT == "per_unit"
    assert AssetTypeEnum.OFFICE == "office"
    assert AggregateLineKey.NET_OPERATING_INCOME == "Net Operating Income"

def test_aggregate_line_key_helpers():
    """Test the helper methods on the AggregateLineKey enum."""
    noi_key = AggregateLineKey.NET_OPERATING_INCOME
    raw_key = AggregateLineKey._RAW_TOTAL_REVENUE

    assert not AggregateLineKey.is_internal_key(noi_key)
    assert AggregateLineKey.is_internal_key(raw_key)

    display_keys = AggregateLineKey.get_display_keys()
    assert noi_key in display_keys
    assert raw_key not in display_keys

    assert AggregateLineKey.from_value("Net Operating Income") == noi_key
    assert AggregateLineKey.from_value("NonExistentKey") is None
