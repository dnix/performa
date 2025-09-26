# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""Tests for BaseValuation - Abstract Base Class."""

from datetime import date
from typing import Dict
from unittest.mock import Mock

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.core.ledger import Ledger
from performa.core.primitives import GlobalSettings, Timeline
from performa.deal.orchestrator import DealContext
from performa.valuation import DirectCapValuation, DirectEntry
from performa.valuation.base.valuation import BaseValuation


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


class MockValuation(BaseValuation):
    """Mock implementation for testing abstract base."""

    kind: str = "mock"

    def compute_cf(self, context: "DealContext") -> pd.Series:
        """Mock implementation."""
        return pd.Series([1000000], index=context.timeline.period_index[-1:])

    def calculate_value(self, **kwargs) -> Dict[str, float]:
        """Mock implementation."""
        return {"property_value": 1000000}


class TestBaseValuation:
    """Test BaseValuation abstract base class."""

    def test_abstract_class_cannot_instantiate(self):
        """Test that BaseValuation cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseValuation(name="Test")

    def test_concrete_subclass_instantiation(self):
        """Test that concrete subclass can be instantiated."""
        mock = MockValuation(name="Mock Test")

        assert mock.name == "Mock Test"
        assert mock.uid is not None
        assert mock.kind == "mock"

    def test_required_name_field(self):
        """Test that name field is required."""
        with pytest.raises(ValidationError, match="Field required"):
            MockValuation()  # Missing name

    def test_validate_context_valid_timeline(self):
        """Test context validation with valid timeline."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2026, 12, 31))
        context = create_test_context(timeline, None)

        mock = MockValuation(name="Test")

        # Should not raise exception
        mock.validate_context(context)

    def test_validate_context_empty_timeline(self):
        """Test context validation with empty timeline."""
        # Create context with empty timeline
        empty_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=0)
        context = create_test_context(empty_timeline, None)

        mock = MockValuation(name="Test")

        with pytest.raises(ValueError, match="Timeline is required"):
            mock.validate_context(context)

    def test_compute_cf_interface(self):
        """Test that compute_cf interface works correctly."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2026, 12, 31))
        context = create_test_context(timeline, None)

        mock = MockValuation(name="Test")

        cf_series = mock.compute_cf(context)

        assert isinstance(cf_series, pd.Series)
        assert cf_series.sum() == 1000000  # From mock implementation

    def test_calculate_value_interface(self):
        """Test that calculate_value interface works correctly."""
        mock = MockValuation(name="Test")

        result = mock.calculate_value()

        assert isinstance(result, dict)
        assert "property_value" in result
        assert result["property_value"] == 1000000

    def test_uid_uniqueness(self):
        """Test that each instance gets unique UID."""
        mock1 = MockValuation(name="Test 1")
        mock2 = MockValuation(name="Test 2")

        assert mock1.uid != mock2.uid

    def test_subclass_must_implement_abstract_methods(self):
        """Test that subclass must implement abstract methods."""

        class IncompleteValuation(BaseValuation):
            """Incomplete subclass missing abstract methods."""

            kind: str = "incomplete"
            # Missing compute_cf and calculate_value implementations

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteValuation(name="Test")

    def test_polymorphic_usage(self):
        """Test polymorphic usage of valuation classes."""
        # Create different valuation instances
        valuations = [
            DirectCapValuation(name="DirectCap", cap_rate=0.06),
            DirectEntry.explicit("DirectEntry", 10_000_000),
            MockValuation(name="Mock"),
        ]

        # Test they all implement the base interface
        for val in valuations:
            assert isinstance(val, BaseValuation)
            assert hasattr(val, "name")
            assert hasattr(val, "uid")
            assert hasattr(val, "compute_cf")
            assert hasattr(val, "calculate_value")
            assert callable(val.compute_cf)
            assert callable(val.calculate_value)

    def test_base_validation_integration(self):
        """Test integration between base validation and subclass validation."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2026, 12, 31))
        noi_series = pd.Series([50_000] * 36, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(name="Integration Test", cap_rate=0.06)

        # Should pass base validation
        valuation.validate_context(context)

        # Should work with compute_cf
        cf_series = valuation.compute_cf(context)
        assert cf_series.sum() > 0

    def test_error_handling_consistency(self):
        """Test that error handling is consistent across base class."""
        mock = MockValuation(name="Error Test")

        # Test that validation errors are properly raised
        empty_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=0)
        invalid_context = create_test_context(empty_timeline, None)

        with pytest.raises(ValueError, match="Timeline is required"):
            mock.validate_context(invalid_context)
