# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for interest rate system.

Tests the enhanced InterestRate classes including FixedRate, FloatingRate,
and the discriminated union pattern with dynamic rate calculations.
"""

import numpy as np
import pandas as pd
import pytest

from performa.debt.rates import FixedRate, FloatingRate, InterestRate, RateIndexEnum


class TestFixedRate:
    """Test FixedRate functionality."""
    
    def test_fixed_rate_creation(self):
        """Test basic fixed rate creation."""
        rate = InterestRate(details=FixedRate(rate=0.05))
        assert rate.details.rate == 0.05
        assert rate.details.rate_type == "fixed"
    
    def test_fixed_rate_calculation(self):
        """Test fixed rate calculation across periods."""
        rate = InterestRate(details=FixedRate(rate=0.06))
        
        # Create timeline
        timeline = pd.period_range('2024-01', periods=12, freq='M')
        
        # Should return same rate for all periods
        for period in timeline:
            assert rate.get_rate_for_period(period) == 0.06


class TestFloatingRate:
    """Test FloatingRate functionality."""
    
    def test_floating_rate_creation(self):
        """Test basic floating rate creation."""
        rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275,
            interest_rate_cap=0.08
        ))
        assert rate.details.rate_index == RateIndexEnum.SOFR_30_DAY_AVG
        assert rate.details.spread == 0.0275
        assert rate.details.interest_rate_cap == 0.08
        assert rate.details.rate_type == "floating"
    
    def test_floating_rate_calculation(self):
        """Test floating rate calculation with index curve."""
        rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275,
            interest_rate_cap=0.08
        ))
        
        # Create timeline and SOFR curve
        timeline = pd.period_range('2024-01', periods=6, freq='M')
        sofr_curve = pd.Series([0.045, 0.048, 0.050, 0.052, 0.055, 0.058], index=timeline)
        
        # Calculate rates
        calculated_rates = []
        for period in timeline:
            calculated_rate = rate.get_rate_for_period(period, sofr_curve)
            calculated_rates.append(calculated_rate)
        
        # Verify rates are SOFR + spread, but capped at 8%
        uncapped_rates = [0.045 + 0.0275, 0.048 + 0.0275, 0.050 + 0.0275, 
                         0.052 + 0.0275, 0.055 + 0.0275, 0.058 + 0.0275]
        expected_rates = [min(rate, 0.08) for rate in uncapped_rates]  # Apply 8% cap
        
        for i, expected in enumerate(expected_rates):
            assert abs(calculated_rates[i] - expected) < 0.001
    
    def test_rate_cap_enforcement(self):
        """Test that rate caps are properly enforced."""
        rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.03,  # 3%
            interest_rate_cap=0.06  # 6% cap
        ))
        
        # Create high SOFR that would exceed cap
        timeline = pd.period_range('2024-01', periods=3, freq='M')
        high_sofr = pd.Series([0.055, 0.060, 0.065], index=timeline)  # 5.5% - 6.5%
        
        # All rates should be capped at 6%
        for period in timeline:
            calculated_rate = rate.get_rate_for_period(period, high_sofr)
            assert calculated_rate <= 0.06
            
        # Specifically test the capped case
        period = timeline[2]  # 6.5% SOFR + 3% spread = 9.5%, should be capped at 6%
        calculated_rate = rate.get_rate_for_period(period, high_sofr)
        assert calculated_rate == 0.06
    
    def test_rate_floor_enforcement(self):
        """Test that rate floors are properly enforced."""
        rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.02,  # 2%
            interest_rate_floor=0.04  # 4% floor
        ))
        
        # Create low SOFR that would be below floor
        timeline = pd.period_range('2024-01', periods=3, freq='M')
        low_sofr = pd.Series([0.005, 0.010, 0.015], index=timeline)  # 0.5% - 1.5%
        
        # All rates should be at or above floor
        for period in timeline:
            calculated_rate = rate.get_rate_for_period(period, low_sofr)
            assert calculated_rate >= 0.04
            
        # Specifically test the floored case
        period = timeline[0]  # 0.5% SOFR + 2% spread = 2.5%, should be floored at 4%
        calculated_rate = rate.get_rate_for_period(period, low_sofr)
        assert calculated_rate == 0.04
    
    def test_floating_rate_requires_index_curve(self):
        """Test that floating rates require index curve."""
        rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275
        ))
        
        period = pd.Period('2024-01', freq='M')
        
        # Should raise error without index curve
        with pytest.raises(ValueError, match="index_curve.*must be provided"):
            rate.get_rate_for_period(period)


class TestInterestRateSystem:
    """Test the overall interest rate system."""
    
    def test_discriminated_union_pattern(self):
        """Test that discriminated union works correctly."""
        # Create both types
        fixed_rate = InterestRate(details=FixedRate(rate=0.05))
        floating_rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275
        ))
        
        # Should be able to distinguish types
        assert fixed_rate.details.rate_type == "fixed"
        assert floating_rate.details.rate_type == "floating"
        
        # Should have different interfaces
        assert hasattr(fixed_rate.details, 'rate')
        assert hasattr(floating_rate.details, 'rate_index')
        assert hasattr(floating_rate.details, 'spread')
    
    def test_rate_validation(self):
        """Test rate validation."""
        # Valid rates should work
        InterestRate(details=FixedRate(rate=0.05))
        InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275
        ))
        
        # Invalid rates should fail
        with pytest.raises(ValueError):
            InterestRate(details=FixedRate(rate=-0.01))  # Negative rate
        
        with pytest.raises(ValueError):
            InterestRate(details=FixedRate(rate=1.5))  # Rate > 100% 