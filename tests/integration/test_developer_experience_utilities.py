# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration test for developer experience utilities.

Tests that the new test utilities in conftest.py work correctly and solve
the original developer experience issues.
"""

import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "tests"))

import pytest

# Import our new utilities
from conftest import (
    create_test_timeline,
    create_simple_partnership,
    create_waterfall_partnership,
    create_distribution_calculator,
    create_simple_cash_flows,
    validate_distribution_results_structure,
    validate_cash_flow_conservation
)


class TestDeveloperExperienceUtilities:
    """Test suite for developer experience utilities."""

    def test_timeline_creation(self):
        """Test that timeline creation is simple and works correctly."""
        timeline = create_test_timeline("2024-01-01", 24)
        assert timeline.duration_months == 24
        assert len(timeline.period_index) == 24

    def test_partnership_creation(self):
        """Test simple partnership creation."""
        partnership = create_simple_partnership(0.75)
        assert len(partnership.partners) == 2
        assert partnership.partners[0].share == 0.75
        assert partnership.partners[1].share == 0.25
        assert partnership.distribution_method == "pari_passu"

    def test_waterfall_partnership_creation(self):
        """Test waterfall partnership creation."""
        partnership = create_waterfall_partnership(preferred_return_rate=0.10)
        assert partnership.has_promote is True
        assert partnership.distribution_method == "waterfall"

    def test_distribution_calculator_creation(self):
        """Test distribution calculator creation."""
        calc = create_distribution_calculator("waterfall", lp_share=0.8, preferred_return_rate=0.08)
        assert calc.partnership.distribution_method == "waterfall"
        assert len(calc.partnership.partners) == 2

    def test_cash_flow_creation(self):
        """Test cash flow creation utility."""
        timeline = create_test_timeline("2024-01-01", 12)
        cash_flows = create_simple_cash_flows(timeline, 1_000_000, 1_500_000)
        
        assert cash_flows.iloc[0] == -1_000_000  # Investment
        assert cash_flows.iloc[-1] == 1_500_000  # Return
        assert cash_flows.iloc[1:-1].sum() == 0  # Middle periods are zero

    def test_full_integration_waterfall(self):
        """Test full integration: create calculator and run waterfall."""
        timeline = create_test_timeline("2024-01-01", 36)
        calc = create_distribution_calculator("waterfall", lp_share=0.8, preferred_return_rate=0.08)
        cash_flows = create_simple_cash_flows(timeline, 1_000_000, 1_500_000)
        
        # This should work without any API confusion
        results = calc.calculate_waterfall_distribution(cash_flows, timeline)
        
        # Test that we can access the structure easily
        lp_distributions = results["partner_distributions"]["LP"]["total_distributions"]
        gp_distributions = results["partner_distributions"]["GP"]["total_distributions"]
        
        assert lp_distributions > 0
        assert gp_distributions > 0
        assert abs((lp_distributions + gp_distributions) - 1_500_000) < 1.0

    def test_full_integration_pari_passu(self):
        """Test full integration: create calculator and run pari passu."""
        timeline = create_test_timeline("2024-01-01", 12)
        calc = create_distribution_calculator("pari_passu", lp_share=0.8)
        cash_flows = create_simple_cash_flows(timeline, 1_000_000, 1_500_000)
        
        results = calc.calculate_pari_passu_distribution(cash_flows, timeline)
        
        # Test proportional distribution
        lp_distributions = results["partner_distributions"]["LP"]["total_distributions"]
        gp_distributions = results["partner_distributions"]["GP"]["total_distributions"]
        
        assert abs(lp_distributions - 1_500_000 * 0.8) < 1.0
        assert abs(gp_distributions - 1_500_000 * 0.2) < 1.0

    def test_result_structure_validation(self):
        """Test that result structure validation works."""
        timeline = create_test_timeline("2024-01-01", 12)
        calc = create_distribution_calculator("pari_passu", lp_share=0.8)
        cash_flows = create_simple_cash_flows(timeline, 1_000_000, 1_500_000)
        
        results = calc.calculate_pari_passu_distribution(cash_flows, timeline)
        
        # This should not raise any assertions
        assert validate_distribution_results_structure(results) is True

    def test_cash_flow_conservation_validation(self):
        """Test that conservation validation works."""
        timeline = create_test_timeline("2024-01-01", 12)
        calc = create_distribution_calculator("pari_passu", lp_share=0.8)
        cash_flows = create_simple_cash_flows(timeline, 1_000_000, 1_500_000)
        
        results = calc.calculate_pari_passu_distribution(cash_flows, timeline)
        
        # This should not raise any assertions
        assert validate_cash_flow_conservation(results, cash_flows) is True

    def test_developer_experience_improvement(self):
        """Test that the new utilities solve the original problems."""
        # This test demonstrates that what used to take 45+ minutes of debugging
        # now takes seconds and works on the first try
        
        # 1. Timeline creation (was confusing before)
        timeline = create_test_timeline("2024-01-01", 24)
        
        # 2. Partnership creation (was complex before)
        partnership = create_waterfall_partnership(preferred_return_rate=0.08)
        
        # 3. Calculator creation (was blocked by complex requirements before)
        calc = create_distribution_calculator("waterfall", lp_share=0.8)
        
        # 4. Cash flow creation (was manual before)
        cash_flows = create_simple_cash_flows(timeline, 1_000_000, 2_000_000)
        
        # 5. Run calculation (was confusing result structure before)
        results = calc.calculate_waterfall_distribution(cash_flows, timeline)
        
        # 6. Access results (was requiring debugging before)
        lp_irr = results["partner_distributions"]["LP"]["irr"]
        gp_irr = results["partner_distributions"]["GP"]["irr"]
        
        # 7. Validate automatically (was manual checking before)
        validate_distribution_results_structure(results)
        validate_cash_flow_conservation(results, cash_flows)
        
        # If we get here, all the developer experience issues are solved
        assert lp_irr > 0
        assert gp_irr > 0
        assert True  # Success!


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
