# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for DCF Valuation module.
"""

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.valuation import DCFValuation


class TestDCFValuation:
    """Tests for DCF valuation functionality."""
    
    def test_dcf_creation_basic(self):
        """Test basic DCF creation."""
        dcf = DCFValuation(
            name="Test DCF",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=10
        )
        
        assert dcf.name == "Test DCF"
        assert dcf.discount_rate == 0.08
        assert dcf.terminal_cap_rate == 0.065
        assert dcf.hold_period_years == 10
        assert dcf.terminal_growth_rate is None
        assert dcf.reversion_costs_rate == 0.025  # default
    
    def test_dcf_validation_discount_rate(self):
        """Test discount rate validation."""
        # Valid discount rate
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065, hold_period_years=10
        )
        assert dcf.discount_rate == 0.08
        
        # Invalid discount rate - too low
        with pytest.raises(ValidationError, match="Discount rate.*should be between 2% and 25%"):
            DCFValuation(
                name="Test", discount_rate=0.01, terminal_cap_rate=0.065, hold_period_years=10
            )
        
        # Invalid discount rate - too high
        with pytest.raises(ValidationError, match="Discount rate.*should be between 2% and 25%"):
            DCFValuation(
                name="Test", discount_rate=0.30, terminal_cap_rate=0.065, hold_period_years=10
            )
    
    def test_dcf_validation_cap_rate(self):
        """Test terminal cap rate validation."""
        # Valid cap rate
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065, hold_period_years=10
        )
        assert dcf.terminal_cap_rate == 0.065
        
        # Invalid cap rate - too low
        with pytest.raises(ValidationError, match="Terminal cap rate.*should be between 1% and 20%"):
            DCFValuation(
                name="Test", discount_rate=0.08, terminal_cap_rate=0.005, hold_period_years=10
            )
    
    def test_dcf_validation_growth_rate(self):
        """Test terminal growth rate validation."""
        # Valid growth rate
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065, 
            hold_period_years=10, terminal_growth_rate=0.02
        )
        assert dcf.terminal_growth_rate == 0.02
        
        # Growth rate >= discount rate should fail
        with pytest.raises(ValidationError, match="Terminal growth rate.*must be less than.*discount rate"):
            DCFValuation(
                name="Test", discount_rate=0.08, terminal_cap_rate=0.065,
                hold_period_years=10, terminal_growth_rate=0.09
            )
    
    def test_dcf_validation_hold_period(self):
        """Test hold period validation."""
        # Valid hold period
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065, hold_period_years=5
        )
        assert dcf.hold_period_years == 5
        
        # Invalid hold period - too short
        with pytest.raises(ValidationError, match="Hold period.*should be between 1 and 50 years"):
            DCFValuation(
                name="Test", discount_rate=0.08, terminal_cap_rate=0.065, hold_period_years=0
            )
    
    def test_computed_properties(self):
        """Test computed properties."""
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065,
            hold_period_years=5, reversion_costs_rate=0.025
        )
        
        assert dcf.net_terminal_proceeds_rate == 0.975  # 1.0 - 0.025
        assert abs(dcf.terminal_discount_factor - (1.0 / (1.08 ** 5))) < 0.0001
    
    def test_calculate_present_value_basic(self):
        """Test basic present value calculation."""
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065, hold_period_years=5
        )
        
        cash_flows = pd.Series([100000, 105000, 110000, 115000, 120000])
        terminal_noi = 125000
        
        result = dcf.calculate_present_value(cash_flows, terminal_noi)
        
        # Check result structure
        assert "present_value" in result
        assert "pv_operations" in result
        assert "pv_terminal" in result
        assert "gross_terminal_value" in result
        assert "net_terminal_value" in result
        assert "terminal_noi" in result
        assert "operations_percentage" in result
        assert "terminal_percentage" in result
        
        # Check calculations are reasonable
        assert result["present_value"] > 0
        assert result["pv_operations"] > 0
        assert result["pv_terminal"] > 0
        assert result["present_value"] == result["pv_operations"] + result["pv_terminal"]
        assert result["operations_percentage"] + result["terminal_percentage"] == 100.0
        
        # Terminal value should be NOI / cap rate
        expected_gross_terminal = terminal_noi / dcf.terminal_cap_rate
        assert abs(result["gross_terminal_value"] - expected_gross_terminal) < 1.0
    
    def test_calculate_present_value_with_growth(self):
        """Test present value calculation with terminal growth."""
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065,
            hold_period_years=5, terminal_growth_rate=0.02
        )
        
        cash_flows = pd.Series([100000, 105000, 110000, 115000, 120000])
        terminal_noi = 125000
        
        result = dcf.calculate_present_value(cash_flows, terminal_noi)
        
        # With growth, terminal NOI should be grown
        expected_grown_noi = terminal_noi * ((1.02) ** 5)
        assert abs(result["terminal_noi"] - expected_grown_noi) < 1.0
    
    def test_calculate_present_value_edge_cases(self):
        """Test edge cases for present value calculation."""
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065, hold_period_years=5
        )
        
        # Empty cash flows should raise error
        with pytest.raises(ValueError, match="Cash flows cannot be empty"):
            dcf.calculate_present_value(pd.Series([]), 125000)
        
        # Too many cash flows should truncate
        long_cash_flows = pd.Series([100000] * 10)  # 10 years but hold period is 5
        result = dcf.calculate_present_value(long_cash_flows, 125000)
        assert result["present_value"] > 0  # Should still work
    
    def test_calculate_metrics(self):
        """Test comprehensive metrics calculation."""
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065, hold_period_years=5
        )
        
        cash_flows = pd.Series([100000, 105000, 110000, 115000, 120000])
        terminal_noi = 125000
        initial_investment = 1500000
        
        metrics = dcf.calculate_metrics(cash_flows, terminal_noi, initial_investment)
        
        # Check all expected metrics are present
        expected_keys = [
            "present_value", "pv_operations", "pv_terminal", "gross_terminal_value",
            "net_terminal_value", "terminal_noi", "operations_percentage",
            "terminal_percentage", "npv", "value_per_dollar_invested",
            "initial_investment", "profit", "profit_margin"
        ]
        
        for key in expected_keys:
            assert key in metrics
        
        # Check relationships
        assert metrics["npv"] == metrics["present_value"] - initial_investment
        assert metrics["profit"] == metrics["npv"]
        assert metrics["value_per_dollar_invested"] == metrics["present_value"] / initial_investment
        assert metrics["initial_investment"] == initial_investment
    
    def test_sensitivity_analysis(self):
        """Test sensitivity analysis."""
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065, hold_period_years=5
        )
        
        cash_flows = pd.Series([100000, 105000, 110000, 115000, 120000])
        terminal_noi = 125000
        
        sensitivity = dcf.calculate_sensitivity_analysis(
            cash_flows, terminal_noi, 
            discount_rate_range=(-0.01, 0.01),
            cap_rate_range=(-0.005, 0.005),
            steps=3
        )
        
        # Should return a DataFrame
        assert isinstance(sensitivity, pd.DataFrame)
        assert len(sensitivity) == 9  # 3x3 grid
        
        # Check columns
        expected_cols = ["discount_rate", "terminal_cap_rate", "present_value", 
                        "discount_rate_delta", "cap_rate_delta"]
        for col in expected_cols:
            assert col in sensitivity.columns
        
        # Check that values vary
        assert sensitivity["present_value"].nunique() > 1  # Should have different values
    
    def test_factory_methods(self):
        """Test factory methods."""
        # Conservative factory
        conservative = DCFValuation.conservative()
        assert conservative.name == "Conservative DCF"
        assert conservative.discount_rate == 0.09
        assert conservative.terminal_cap_rate == 0.07
        assert conservative.hold_period_years == 10
        assert conservative.reversion_costs_rate == 0.025
        assert conservative.terminal_growth_rate is None
        
        # Aggressive factory
        aggressive = DCFValuation.aggressive()
        assert aggressive.name == "Aggressive DCF"
        assert aggressive.discount_rate == 0.075
        assert aggressive.terminal_cap_rate == 0.055
        assert aggressive.hold_period_years == 7
        assert aggressive.terminal_growth_rate == 0.02
        assert aggressive.reversion_costs_rate == 0.020
        
        # Custom parameters
        custom_conservative = DCFValuation.conservative(
            name="Custom", discount_rate=0.10, hold_period_years=15
        )
        assert custom_conservative.name == "Custom"
        assert custom_conservative.discount_rate == 0.10
        assert custom_conservative.hold_period_years == 15
    
    def test_model_immutability(self):
        """Test that DCF models are immutable."""
        dcf = DCFValuation(
            name="Test", discount_rate=0.08, terminal_cap_rate=0.065, hold_period_years=5
        )
        
        # Should not be able to modify attributes directly (frozen model)
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            dcf.discount_rate = 0.10
        
        # But should be able to create copies with modifications
        modified_dcf = dcf.model_copy(update={"discount_rate": 0.10})
        assert modified_dcf.discount_rate == 0.10
        assert dcf.discount_rate == 0.08  # Original unchanged 