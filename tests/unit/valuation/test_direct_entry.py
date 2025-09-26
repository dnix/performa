# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""Tests for DirectEntry - Manual and Rule-Based Valuation."""

from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from performa.core.ledger import Ledger
from performa.core.primitives import GlobalSettings, Timeline
from performa.deal.orchestrator import DealContext
from performa.valuation import DirectEntry


def create_test_context(timeline: Timeline, noi_series=None) -> DealContext:
    """Create a test DealContext with proper ledger and mock deal instance."""
    # Use mock deal to bypass complex validation
    mock_deal = Mock()
    mock_deal.name = "Test Deal"
    mock_deal.uid = "test-deal-uid"

    # Create ledger and context
    ledger = Ledger()
    return DealContext(
        timeline=timeline,
        settings=GlobalSettings(),
        noi_series=noi_series,
        deal=mock_deal,
        ledger=ledger,
    )


class TestDirectEntry:
    """Test DirectEntry functionality."""

    def test_explicit_mode_creation(self):
        """Test explicit value mode."""
        entry = DirectEntry.explicit("Manual Override", 15_000_000)

        assert entry.name == "Manual Override"
        assert entry.mode == "explicit"
        assert entry.value == 15_000_000
        assert entry.kind == "direct_entry"

    def test_unit_multiplier_mode_creation(self):
        """Test unit multiplier mode."""
        entry = DirectEntry.unit_multiplier("Per-SF Value", 100_000, 150.0, "SF")

        assert entry.name == "Per-SF Value"
        assert entry.mode == "unit_multiplier"
        assert entry.units == 100_000
        assert entry.rate_per_unit == 150.0
        assert entry.unit_type == "SF"

    def test_yield_target_mode_creation(self):
        """Test yield target mode."""
        entry = DirectEntry.yield_target("Target 6%", 0.06, "LTM")

        assert entry.name == "Target 6%"
        assert entry.mode == "yield_target"
        assert entry.target_cap_rate == 0.06
        assert entry.noi_basis_kind == "LTM"

    def test_validation_explicit_mode_missing_value(self):
        """Test validation fails for explicit mode without value."""
        with pytest.raises(ValueError, match="Explicit mode requires 'value'"):
            DirectEntry(name="Test", mode="explicit")  # Missing value

    def test_validation_unit_multiplier_missing_params(self):
        """Test validation fails for unit multiplier without required params."""
        # Missing units
        with pytest.raises(
            ValueError,
            match="Unit multiplier mode requires 'units' and 'rate_per_unit'",
        ):
            DirectEntry(
                name="Test", mode="unit_multiplier", rate_per_unit=150.0, unit_type="SF"
            )

        # Missing rate_per_unit
        with pytest.raises(
            ValueError,
            match="Unit multiplier mode requires 'units' and 'rate_per_unit'",
        ):
            DirectEntry(
                name="Test", mode="unit_multiplier", units=100_000, unit_type="SF"
            )

        # Missing unit_type
        with pytest.raises(
            ValueError, match="Unit multiplier mode requires 'unit_type'"
        ):
            DirectEntry(
                name="Test", mode="unit_multiplier", units=100_000, rate_per_unit=150.0
            )

    def test_validation_yield_target_missing_params(self):
        """Test validation fails for yield target without required params."""
        # Missing target_cap_rate
        with pytest.raises(
            ValueError, match="Yield target mode requires 'target_cap_rate'"
        ):
            DirectEntry(name="Test", mode="yield_target", noi_basis_kind="LTM")

        # Missing noi_basis_kind
        with pytest.raises(
            ValueError, match="Yield target mode requires 'noi_basis_kind'"
        ):
            DirectEntry(name="Test", mode="yield_target", target_cap_rate=0.06)

    def test_validation_cap_rate_bounds(self):
        """Test cap rate validation."""
        # Valid cap rate
        DirectEntry.yield_target("Test", 0.06, "LTM")

        # Too low
        with pytest.raises(ValueError, match="should be between 1% and 20%"):
            DirectEntry.yield_target("Test", 0.005, "LTM")

        # Too high
        with pytest.raises(ValueError, match="should be between 1% and 20%"):
            DirectEntry.yield_target("Test", 0.25, "LTM")

    def test_validation_unit_type_accepted(self):
        """Test that standard unit types are accepted."""
        valid_types = ["SF", "units", "keys", "stalls", "acres", "rooms", "beds"]

        for unit_type in valid_types:
            entry = DirectEntry.unit_multiplier(
                f"Test {unit_type}", 100, 200, unit_type
            )
            assert entry.unit_type == unit_type

    def test_calculate_value_explicit(self):
        """Test explicit value calculation."""
        entry = DirectEntry.explicit("Test", 15_000_000)

        result = entry.calculate_value()

        assert result["property_value"] == 15_000_000
        assert result["mode"] == "explicit"

    def test_calculate_value_unit_multiplier(self):
        """Test unit multiplier calculation."""
        entry = DirectEntry.unit_multiplier("Test", 50_000, 200.0, "SF")

        result = entry.calculate_value()

        expected_value = 50_000 * 200.0
        assert result["property_value"] == expected_value
        assert result["units"] == 50_000
        assert result["rate_per_unit"] == 200.0
        assert result["unit_type"] == "SF"
        assert result["mode"] == "unit_multiplier"

    def test_calculate_value_yield_target(self):
        """Test yield target calculation."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
        noi_series = pd.Series([50_000] * 12, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        entry = DirectEntry.yield_target("Test", 0.06, "LTM")

        result = entry.calculate_value(context)

        expected_noi = 600_000  # 50k × 12
        expected_value = 600_000 / 0.06  # 10M

        assert result["property_value"] == expected_value
        assert result["noi_basis"] == expected_noi
        assert result["noi_basis_kind"] == "LTM"
        assert result["target_cap_rate"] == 0.06
        assert result["mode"] == "yield_target"

    def test_yield_target_missing_context(self):
        """Test that yield target fails without context."""
        entry = DirectEntry.yield_target("Test", 0.06, "LTM")

        with pytest.raises(ValueError, match="Context required for yield_target mode"):
            entry.calculate_value()  # No context provided

    def test_compute_cf_explicit(self):
        """Test cash flow computation for explicit mode."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2026, 12, 31))
        context = create_test_context(timeline, None)

        entry = DirectEntry.explicit("Test", 15_000_000)

        cf_series = entry.compute_cf(context)

        # Should have proceeds at last period
        assert cf_series.sum() == 15_000_000
        assert cf_series.iloc[-1] == 15_000_000
        assert cf_series.iloc[0] == 0

    def test_compute_cf_unit_multiplier(self):
        """Test cash flow computation for unit multiplier mode."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2026, 12, 31))
        context = create_test_context(timeline, None)

        entry = DirectEntry.unit_multiplier("Test", 50_000, 200.0, "SF")

        cf_series = entry.compute_cf(context)

        expected_value = 50_000 * 200.0
        assert cf_series.sum() == expected_value
        assert cf_series.iloc[-1] == expected_value

    def test_compute_cf_yield_target(self):
        """Test cash flow computation for yield target mode."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2026, 12, 31))
        noi_series = pd.Series([40_000] * 36, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        entry = DirectEntry.yield_target("Test", 0.06, "LTM")

        cf_series = entry.compute_cf(context)

        # Should calculate value based on NOI and target cap rate
        expected_noi = 480_000  # 40k × 12 (trailing)
        expected_value = 480_000 / 0.06  # 8M

        assert cf_series.sum() == expected_value
        assert cf_series.iloc[-1] == expected_value

    def test_compute_cf_fails_fast_on_error(self):
        """Test that compute_cf fails fast on calculation errors."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2026, 12, 31))
        context = create_test_context(timeline, None)  # Missing NOI for yield_target

        entry = DirectEntry.yield_target("Test", 0.06, "LTM")

        with pytest.raises(RuntimeError, match="DirectEntry valuation failed"):
            entry.compute_cf(context)

    def test_unknown_mode_error(self):
        """Test error handling for unknown mode."""
        # Since mode validation happens at Pydantic level, test invalid construction
        with pytest.raises(ValueError):
            # This should fail during Pydantic validation
            DirectEntry(
                name="Test",
                mode="unknown",  # Invalid mode
                value=100000,
            )

    def test_realistic_unit_types(self):
        """Test realistic unit type scenarios."""
        test_cases = [
            ("SF", 100_000, 150.0),  # Office/retail $/SF
            ("units", 120, 100_000),  # Residential $/unit
            ("keys", 200, 80_000),  # Hotel $/key
            ("stalls", 500, 25_000),  # Parking $/stall
            ("acres", 10, 500_000),  # Land $/acre
            ("beds", 150, 75_000),  # Healthcare $/bed
        ]

        for unit_type, units, rate in test_cases:
            entry = DirectEntry.unit_multiplier(
                f"Test {unit_type}", units, rate, unit_type
            )
            result = entry.calculate_value()

            expected = units * rate
            assert result["property_value"] == expected
            assert result["unit_type"] == unit_type

    def test_noi_basis_integration_with_yield_target(self):
        """Test NOI basis options work correctly with yield target."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2025, 12, 31))

        # Growth scenario: NOI starts low, ends high
        noi_values = [30_000] * 6 + [40_000] * 6 + [50_000] * 12  # 24 months

        noi_series = pd.Series(noi_values, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        target_cap = 0.06

        # Test different basis options with same target cap rate
        ltm_entry = DirectEntry.yield_target("LTM Target", target_cap, "LTM")
        ntm_entry = DirectEntry.yield_target("NTM Target", target_cap, "NTM")
        stabilized_entry = DirectEntry.yield_target(
            "Stabilized Target", target_cap, "Stabilized"
        )

        ltm_result = ltm_entry.calculate_value(context)
        ntm_result = ntm_entry.calculate_value(context)
        stabilized_result = stabilized_entry.calculate_value(context)

        # Values should differ based on NOI basis
        ltm_value = ltm_result["property_value"]
        ntm_value = ntm_result["property_value"]
        stabilized_value = stabilized_result["property_value"]

        # LTM (trailing) should be higher than NTM (early months)
        assert ltm_value > ntm_value

        # All should be positive and reasonable
        assert all(v > 5_000_000 for v in [ltm_value, ntm_value, stabilized_value])
        assert all(v < 15_000_000 for v in [ltm_value, ntm_value, stabilized_value])
