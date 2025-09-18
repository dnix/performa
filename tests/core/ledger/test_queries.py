# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for FinancialCalculations methods.

This module tests the static calculation methods that serve as the single
source of truth for all financial calculations in the library.
"""

import numpy as np
import pandas as pd

from performa.core.calculations import FinancialCalculations


class TestCalculateIRR:
    """Test the single-source IRR calculation method."""
    
    def test_calculate_irr_valid_flows(self):
        """Test IRR calculation with valid cash flows."""
        # Simple case: invest 1000, get back 1100 after 1 year
        flows = pd.Series(
            [-1000, 1100],
            index=pd.period_range('2024-01', periods=2, freq='Y')  # Annual periods
        )
        irr = FinancialCalculations.calculate_irr(flows)
        
        # Should be approximately 10% annual IRR
        assert irr is not None
        assert 0.09 < irr < 0.11  # Allow for some calculation variance
    
    def test_calculate_irr_empty_series(self):
        """Test IRR with empty series returns None."""
        flows = pd.Series([], dtype=float)
        irr = FinancialCalculations.calculate_irr(flows)
        assert irr is None
    
    def test_calculate_irr_all_negative(self):
        """Test IRR with all negative flows returns None."""
        flows = pd.Series(
            [-1000, -500, -200],
            index=pd.period_range('2024-01', periods=3, freq='M')
        )
        irr = FinancialCalculations.calculate_irr(flows)
        assert irr is None
    
    def test_calculate_irr_all_positive(self):
        """Test IRR with all positive flows returns None."""
        flows = pd.Series(
            [1000, 500, 200],
            index=pd.period_range('2024-01', periods=3, freq='M')
        )
        irr = FinancialCalculations.calculate_irr(flows)
        assert irr is None
    
    def test_calculate_irr_all_zeros(self):
        """Test IRR with all zero flows returns None."""
        flows = pd.Series(
            [0, 0, 0],
            index=pd.period_range('2024-01', periods=3, freq='M')
        )
        irr = FinancialCalculations.calculate_irr(flows)
        assert irr is None
    
    def test_calculate_irr_single_flow(self):
        """Test IRR with single cash flow returns None."""
        flows = pd.Series(
            [1000],
            index=pd.period_range('2024-01', periods=1, freq='M')
        )
        irr = FinancialCalculations.calculate_irr(flows)
        assert irr is None
    
    def test_calculate_irr_complex_flows(self):
        """Test IRR with complex multi-period flows."""
        # Development project: initial investment + construction + returns
        flows = pd.Series(
            [-5000, -3000, -2000, 500, 1000, 8000],
            index=pd.period_range('2024-01', periods=6, freq='M')
        )
        irr = FinancialCalculations.calculate_irr(flows)
        
        assert irr is not None
        assert isinstance(irr, float)
        # Should be reasonable for a development project
        assert -1 < irr < 5  # Between -100% and 500%
    
    def test_calculate_irr_breakeven(self):
        """Test IRR with breakeven scenario."""
        # Invest 1000, get back exactly 1000
        flows = pd.Series(
            [-1000, 1000],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        irr = FinancialCalculations.calculate_irr(flows)
        
        assert irr is not None
        assert abs(irr) < 0.01  # Close to 0%
    
    def test_calculate_irr_with_nans(self):
        """Test IRR calculation gracefully handles NaN values."""
        flows = pd.Series(
            [-1000, np.nan, 1100],
            index=pd.period_range('2024-01', periods=3, freq='M')
        )
        # Should either work or return None gracefully
        irr = FinancialCalculations.calculate_irr(flows)
        # We don't assert a specific result, just that it doesn't crash
        assert irr is None or isinstance(irr, float)


class TestCalculateEquityMultiple:
    """Test the single-source equity multiple calculation method."""
    
    def test_calculate_equity_multiple_valid_flows(self):
        """Test equity multiple with valid cash flows."""
        # Invest 1000, get back 2500
        flows = pd.Series(
            [-1000, 2500],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        multiple = FinancialCalculations.calculate_equity_multiple(flows)
        
        assert multiple is not None
        assert abs(multiple - 2.5) < 0.01  # Should be 2.5x
    
    def test_calculate_equity_multiple_empty_series(self):
        """Test equity multiple with empty series returns None."""
        flows = pd.Series([], dtype=float)
        multiple = FinancialCalculations.calculate_equity_multiple(flows)
        assert multiple is None
    
    def test_calculate_equity_multiple_no_investment(self):
        """Test equity multiple with no negative flows returns None."""
        flows = pd.Series(
            [1000, 500, 200],
            index=pd.period_range('2024-01', periods=3, freq='M')
        )
        multiple = FinancialCalculations.calculate_equity_multiple(flows)
        assert multiple is None
    
    def test_calculate_equity_multiple_zero_investment(self):
        """Test equity multiple with zero investment returns None."""
        flows = pd.Series(
            [0, 1000],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        multiple = FinancialCalculations.calculate_equity_multiple(flows)
        assert multiple is None
    
    def test_calculate_equity_multiple_no_returns(self):
        """Test equity multiple with no positive flows returns 0.0."""
        flows = pd.Series(
            [-1000, -500],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        multiple = FinancialCalculations.calculate_equity_multiple(flows)
        
        assert multiple is not None
        assert multiple == 0.0  # Lost all money
    
    def test_calculate_equity_multiple_complex_flows(self):
        """Test equity multiple with multiple investments and returns."""
        # Multiple investments and multiple returns
        flows = pd.Series(
            [-1000, -500, 800, 900, 200],
            index=pd.period_range('2024-01', periods=5, freq='M')
        )
        multiple = FinancialCalculations.calculate_equity_multiple(flows)
        
        total_invested = 1000 + 500  # 1500
        total_returned = 800 + 900 + 200  # 1900
        expected_multiple = total_returned / total_invested  # 1.267
        
        assert multiple is not None
        assert abs(multiple - expected_multiple) < 0.01
    
    def test_calculate_equity_multiple_partial_loss(self):
        """Test equity multiple with partial loss scenario."""
        # Invest 1000, get back 600
        flows = pd.Series(
            [-1000, 600],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        multiple = FinancialCalculations.calculate_equity_multiple(flows)
        
        assert multiple is not None
        assert abs(multiple - 0.6) < 0.01  # 0.6x multiple (60% loss)


class TestCalculateNPV:
    """Test the single-source NPV calculation method."""
    
    def test_calculate_npv_valid_flows(self):
        """Test NPV calculation with valid cash flows."""
        # Simple case: invest 1000, get 550 twice at 10% discount
        flows = pd.Series(
            [-1000, 550, 550],
            index=pd.period_range('2024-01', periods=3, freq='M')
        )
        npv = FinancialCalculations.calculate_npv(flows, 0.10)
        
        assert npv is not None
        assert isinstance(npv, float)
        # Should be positive but less than the nominal return
        assert -100 < npv < 100  # Reasonable range
    
    def test_calculate_npv_empty_series(self):
        """Test NPV with empty series returns None."""
        flows = pd.Series([], dtype=float)
        npv = FinancialCalculations.calculate_npv(flows, 0.10)
        assert npv is None
    
    def test_calculate_npv_zero_discount_rate(self):
        """Test NPV with zero discount rate equals sum of flows."""
        flows = pd.Series(
            [-1000, 600, 500],
            index=pd.period_range('2024-01', periods=3, freq='M')
        )
        npv = FinancialCalculations.calculate_npv(flows, 0.0)
        
        assert npv is not None
        # With 0% discount, NPV should equal sum of flows
        expected = flows.sum()  # -1000 + 600 + 500 = 100
        assert abs(npv - expected) < 1.0
    
    def test_calculate_npv_invalid_discount_rate(self):
        """Test NPV with invalid discount rate returns None."""
        flows = pd.Series(
            [-1000, 1100],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        
        # Test various invalid rates
        assert FinancialCalculations.calculate_npv(flows, "not_a_number") is None
        assert FinancialCalculations.calculate_npv(flows, -1.5) is None  # Less than -100%
    
    def test_calculate_npv_negative_discount_rate(self):
        """Test NPV with valid negative discount rate works."""
        flows = pd.Series(
            [-1000, 1100],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        
        # -50% discount rate is theoretically valid (though unusual)
        npv = FinancialCalculations.calculate_npv(flows, -0.5)
        assert npv is not None
        assert isinstance(npv, float)
    
    def test_calculate_npv_high_discount_rate(self):
        """Test NPV with high discount rate."""
        flows = pd.Series(
            [-1000, 2000],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        
        # 50% discount rate
        npv = FinancialCalculations.calculate_npv(flows, 0.5)
        assert npv is not None
        # High discount rate should reduce NPV from raw 1000 net cash flow
        assert 900 < npv < 950  # Around 932 with 50% annual rate over 1 month
    
    def test_calculate_npv_complex_flows(self):
        """Test NPV with complex multi-period flows."""
        # Development project cash flows
        flows = pd.Series(
            [-5000, -3000, -2000, 1000, 2000, 8000],
            index=pd.period_range('2024-01', periods=6, freq='M')
        )
        npv = FinancialCalculations.calculate_npv(flows, 0.12)  # 12% discount rate
        
        assert npv is not None
        assert isinstance(npv, float)
        # Should be reasonable for a development project
        assert -10000 < npv < 5000


class TestEdgeCasesAndIntegration:
    """Test edge cases and integration scenarios."""
    
    def test_all_methods_with_same_flows(self):
        """Test all three methods with the same cash flow series."""
        # Standard investment scenario
        flows = pd.Series(
            [-1000, 100, 100, 100, 1300],
            index=pd.period_range('2024-01', periods=5, freq='M')
        )
        
        irr = FinancialCalculations.calculate_irr(flows)
        multiple = FinancialCalculations.calculate_equity_multiple(flows)
        npv = FinancialCalculations.calculate_npv(flows, 0.10)
        
        # All should return valid results
        assert irr is not None
        assert multiple is not None 
        assert npv is not None
        
        # Results should be mathematically consistent  
        # 1.6x return over 5 months = very high annualized IRR
        assert 3.5 < irr < 4.0  # Around 388% annualized IRR
        assert 1.55 < multiple < 1.65  # Exactly 1.6x multiple (1600/1000)
        assert npv > 0  # Should be positive at 10% discount
    
    def test_methods_are_static(self):
        """Verify methods are static and don't require instance."""
        flows = pd.Series(
            [-1000, 1100],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        
        # Should work without creating a LedgerQueries instance
        irr = FinancialCalculations.calculate_irr(flows)
        multiple = FinancialCalculations.calculate_equity_multiple(flows)
        npv = FinancialCalculations.calculate_npv(flows, 0.10)
        
        assert irr is not None
        assert multiple is not None
        assert npv is not None
    
    def test_period_index_required(self):
        """Test that methods work with PeriodIndex (our standard)."""
        # This should work (what we use everywhere)
        period_flows = pd.Series(
            [-1000, 1100],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        
        irr = FinancialCalculations.calculate_irr(period_flows)
        multiple = FinancialCalculations.calculate_equity_multiple(period_flows)
        npv = FinancialCalculations.calculate_npv(period_flows, 0.10)
        
        assert irr is not None
        assert multiple is not None
        assert npv is not None
        
    def test_consistent_none_handling(self):
        """Test that all methods consistently return None for invalid inputs."""
        empty_flows = pd.Series([], dtype=float)
        
        assert FinancialCalculations.calculate_irr(empty_flows) is None
        assert FinancialCalculations.calculate_equity_multiple(empty_flows) is None
        assert FinancialCalculations.calculate_npv(empty_flows, 0.10) is None
