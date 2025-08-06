# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for Direct Cap Valuation module.
"""

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.valuation import DirectCapValuation


class TestDirectCapValuation:
    """Tests for Direct Cap valuation functionality."""

    def test_direct_cap_creation_basic(self):
        """Test basic Direct Cap creation."""
        valuation = DirectCapValuation(name="Test Direct Cap", cap_rate=0.065)

        assert valuation.name == "Test Direct Cap"
        assert valuation.cap_rate == 0.065
        assert valuation.occupancy_adjustment is None
        assert valuation.market_adjustments is None

    def test_direct_cap_validation_cap_rate(self):
        """Test cap rate validation."""
        # Valid cap rate
        valuation = DirectCapValuation(name="Test", cap_rate=0.065)
        assert valuation.cap_rate == 0.065

        # Invalid cap rate - too low
        with pytest.raises(
            ValidationError, match="Cap rate.*should be between 1% and 20%"
        ):
            DirectCapValuation(name="Test", cap_rate=0.005)

        # Invalid cap rate - too high
        with pytest.raises(
            ValidationError, match="Cap rate.*should be between 1% and 20%"
        ):
            DirectCapValuation(name="Test", cap_rate=0.25)

    def test_direct_cap_validation_occupancy(self):
        """Test occupancy adjustment validation."""
        # Valid occupancy
        valuation = DirectCapValuation(
            name="Test", cap_rate=0.065, occupancy_adjustment=0.95
        )
        assert valuation.occupancy_adjustment == 0.95

        # Invalid occupancy - too low
        with pytest.raises(
            ValidationError,
            match="Occupancy adjustment.*should be between 10% and 100%",
        ):
            DirectCapValuation(name="Test", cap_rate=0.065, occupancy_adjustment=0.05)

        # Invalid occupancy - too high
        with pytest.raises(
            ValidationError,
            match="Occupancy adjustment.*should be between 10% and 100%",
        ):
            DirectCapValuation(name="Test", cap_rate=0.065, occupancy_adjustment=1.05)

    def test_direct_cap_validation_market_adjustments(self):
        """Test market adjustments validation."""
        # Valid market adjustments
        valuation = DirectCapValuation(
            name="Test",
            cap_rate=0.065,
            market_adjustments={"location": 1.10, "condition": 0.95},
        )
        assert valuation.market_adjustments["location"] == 1.10

        # Invalid market adjustment - too low
        with pytest.raises(
            ValidationError, match="Market adjustment.*should be between 0.10 and 3.00"
        ):
            DirectCapValuation(
                name="Test", cap_rate=0.065, market_adjustments={"bad_factor": 0.05}
            )

        # Invalid market adjustment - too high
        with pytest.raises(
            ValidationError, match="Market adjustment.*should be between 0.10 and 3.00"
        ):
            DirectCapValuation(
                name="Test", cap_rate=0.065, market_adjustments={"bad_factor": 5.0}
            )

    def test_combined_market_adjustment(self):
        """Test combined market adjustment calculation."""
        # No adjustments
        valuation = DirectCapValuation(name="Test", cap_rate=0.065)
        assert valuation.combined_market_adjustment == 1.0

        # Single adjustment
        valuation = DirectCapValuation(
            name="Test", cap_rate=0.065, market_adjustments={"location": 1.10}
        )
        assert valuation.combined_market_adjustment == 1.10

        # Multiple adjustments
        valuation = DirectCapValuation(
            name="Test",
            cap_rate=0.065,
            market_adjustments={"location": 1.10, "condition": 0.95},
        )
        assert abs(valuation.combined_market_adjustment - (1.10 * 0.95)) < 0.0001

    def test_calculate_value_basic(self):
        """Test basic value calculation."""
        valuation = DirectCapValuation(name="Test", cap_rate=0.065)

        first_year_noi = 500000
        result = valuation.calculate_value(first_year_noi)

        # Check result structure
        expected_keys = [
            "property_value",
            "base_value",
            "effective_noi",
            "cap_rate",
            "market_adjustment_factor",
            "occupancy_rate",
            "implied_yield",
        ]

        for key in expected_keys:
            assert key in result

        # Check calculations
        expected_value = first_year_noi / valuation.cap_rate
        assert abs(result["property_value"] - expected_value) < 1.0
        assert result["base_value"] == result["property_value"]  # No adjustments
        assert result["effective_noi"] == first_year_noi
        assert result["cap_rate"] == 0.065
        assert result["market_adjustment_factor"] == 1.0
        assert result["occupancy_rate"] == 1.0

    def test_calculate_value_with_occupancy(self):
        """Test value calculation with occupancy adjustment."""
        valuation = DirectCapValuation(
            name="Test", cap_rate=0.065, occupancy_adjustment=0.95
        )

        first_year_noi = 500000
        potential_noi = 550000
        result = valuation.calculate_value(first_year_noi, potential_noi)

        # Should use potential NOI with occupancy adjustment
        expected_effective_noi = potential_noi * 0.95
        assert abs(result["effective_noi"] - expected_effective_noi) < 1.0

        expected_value = expected_effective_noi / valuation.cap_rate
        assert abs(result["property_value"] - expected_value) < 1.0

    def test_calculate_value_with_market_adjustments(self):
        """Test value calculation with market adjustments."""
        valuation = DirectCapValuation(
            name="Test",
            cap_rate=0.065,
            market_adjustments={"location": 1.10, "condition": 0.95},
        )

        first_year_noi = 500000
        result = valuation.calculate_value(first_year_noi)

        # Base value calculation
        base_value = first_year_noi / valuation.cap_rate
        assert abs(result["base_value"] - base_value) < 1.0

        # Adjusted value
        market_factor = 1.10 * 0.95
        expected_adjusted_value = base_value * market_factor
        assert abs(result["property_value"] - expected_adjusted_value) < 1.0
        assert abs(result["market_adjustment_factor"] - market_factor) < 0.0001

    def test_calculate_value_per_sf(self):
        """Test value per square foot calculation."""
        valuation = DirectCapValuation(name="Test", cap_rate=0.065)

        first_year_noi = 500000
        total_area = 100000
        result = valuation.calculate_value_per_sf(first_year_noi, total_area)

        # Should include per-SF metrics
        assert "total_area" in result
        assert "value_per_sf" in result
        assert "noi_per_sf" in result

        expected_value = first_year_noi / valuation.cap_rate
        expected_value_per_sf = expected_value / total_area
        expected_noi_per_sf = first_year_noi / total_area

        assert result["total_area"] == total_area
        assert abs(result["value_per_sf"] - expected_value_per_sf) < 0.01
        assert abs(result["noi_per_sf"] - expected_noi_per_sf) < 0.01

        # Invalid area should raise error
        with pytest.raises(ValueError, match="Total area must be positive"):
            valuation.calculate_value_per_sf(first_year_noi, 0)

    def test_sensitivity_analysis(self):
        """Test sensitivity analysis."""
        valuation = DirectCapValuation(name="Test", cap_rate=0.065)

        first_year_noi = 500000
        sensitivity = valuation.calculate_sensitivity_analysis(
            first_year_noi, cap_rate_range=(-0.005, 0.005), steps=5
        )

        # Should return a DataFrame
        assert isinstance(sensitivity, pd.DataFrame)
        assert len(sensitivity) == 5

        # Check columns
        expected_cols = [
            "cap_rate",
            "property_value",
            "cap_rate_delta",
            "value_change_pct",
        ]
        for col in expected_cols:
            assert col in sensitivity.columns

        # Check that values vary
        assert sensitivity["property_value"].nunique() > 1
        assert sensitivity["cap_rate"].nunique() > 1

    def test_calculate_metrics(self):
        """Test comprehensive metrics calculation."""
        valuation = DirectCapValuation(name="Test", cap_rate=0.065)

        first_year_noi = 500000
        acquisition_cost = 7000000
        total_area = 100000

        metrics = valuation.calculate_metrics(
            first_year_noi, acquisition_cost, total_area
        )

        # Should include all value metrics plus acquisition comparison
        expected_keys = [
            "property_value",
            "base_value",
            "effective_noi",
            "cap_rate",
            "market_adjustment_factor",
            "occupancy_rate",
            "implied_yield",
            "total_area",
            "value_per_sf",
            "noi_per_sf",
            "acquisition_cost",
            "value_premium",
            "value_premium_pct",
            "acquisition_cap_rate",
        ]

        for key in expected_keys:
            assert key in metrics

        # Check acquisition metrics
        expected_premium = metrics["property_value"] - acquisition_cost
        assert metrics["value_premium"] == expected_premium
        assert metrics["acquisition_cost"] == acquisition_cost
        assert metrics["acquisition_cap_rate"] == first_year_noi / acquisition_cost

    def test_factory_methods(self):
        """Test factory methods."""
        # Market value factory
        market_val = DirectCapValuation.market_value(cap_rate=0.065)
        assert market_val.name == "Market Value"
        assert market_val.cap_rate == 0.065
        assert market_val.occupancy_adjustment is None

        # Stabilized value factory
        stabilized_val = DirectCapValuation.stabilized_value(
            cap_rate=0.065, occupancy_rate=0.95
        )
        assert stabilized_val.name == "Stabilized Value"
        assert stabilized_val.cap_rate == 0.065
        assert stabilized_val.occupancy_adjustment == 0.95

        # Conservative factory
        conservative = DirectCapValuation.conservative()
        assert conservative.name == "Conservative Value"
        assert conservative.cap_rate == 0.075
        assert conservative.occupancy_adjustment == 0.90

        # Aggressive factory
        aggressive = DirectCapValuation.aggressive()
        assert aggressive.name == "Aggressive Value"
        assert aggressive.cap_rate == 0.055
        assert aggressive.occupancy_adjustment == 0.98

        # Custom parameters
        custom_market = DirectCapValuation.market_value(
            cap_rate=0.07, name="Custom Market"
        )
        assert custom_market.name == "Custom Market"
        assert custom_market.cap_rate == 0.07

    def test_model_immutability(self):
        """Test that Direct Cap models are immutable."""
        valuation = DirectCapValuation(name="Test", cap_rate=0.065)

        # Should not be able to modify attributes directly (frozen model)
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            valuation.cap_rate = 0.08

        # But should be able to create copies with modifications
        modified_valuation = valuation.model_copy(update={"cap_rate": 0.08})
        assert modified_valuation.cap_rate == 0.08
        assert valuation.cap_rate == 0.065  # Original unchanged
