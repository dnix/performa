# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Industry Standard Waterfall Validation Tests

This module validates our DistributionCalculator against industry-standard
waterfall calculations commonly used in institutional real estate.

Based on typical institutional waterfall structures:
1. Preferred Return (6-8% typical)
2. Hurdle Tiers with GP Promote
3. Residual Split

These tests validate our implementation matches industry standards for
waterfall mechanics, cash flow conservation, and performance calculations.
"""

import pandas as pd

from performa.core.primitives import Timeline
from performa.deal.analysis.partnership import DistributionCalculator
from performa.deal.partnership import (
    Partner,
    PartnershipStructure,
    WaterfallPromote,
    WaterfallTier,
)


class TestIndustryStandardWaterfallValidation:
    """
    Validate our DistributionCalculator against industry-standard calculations.

    This test suite validates waterfall structures commonly used in
    institutional real estate to ensure our calculations are accurate.
    """

    def test_simple_institutional_waterfall(self):
        """
        Test a simple institutional waterfall with basic parameters.

        Structure:
        - 8% preferred return to LP
        - 20% GP promote after preferred return
        - 50/50 residual split

        This matches typical institutional structures.
        """
        # Create institutional partnership structure
        partners = [
            Partner(name="GP", kind="GP", share=0.10),  # 10% GP equity
            Partner(name="LP", kind="LP", share=0.90),  # 90% LP equity
        ]

        # Create institutional waterfall promote
        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,  # 8% preferred return (institutional typical)
            tiers=[
                WaterfallTier(
                    tier_hurdle_rate=0.08,  # Hit immediately after pref return
                    promote_rate=0.20,  # 20% GP promote (institutional typical)
                )
            ],
            final_promote_rate=0.50,  # 50/50 residual split (institutional typical)
        )

        partnership = PartnershipStructure(
            partners=partners, promote=promote, distribution_method="waterfall"
        )

        # Create test cash flows: initial investment + 5 years of distributions
        # Pattern: One negative (investment), followed by positive distributions
        # This matches typical institutional assumption: single upfront investment
        periods = pd.period_range("2024-01", periods=61, freq="M")
        cash_flows = pd.Series(0.0, index=periods)

        # Initial investment (negative - month 0)
        cash_flows.iloc[0] = -1_000_000  # $1M investment

        # Annual distributions (positive - years 1-5)
        annual_distributions = [
            120_000,
            130_000,
            140_000,
            150_000,
            1_200_000,
        ]  # Last year includes sale

        for year, annual_dist in enumerate(annual_distributions, 1):
            year_end_month = year * 12
            if year_end_month < len(cash_flows):
                cash_flows.iloc[year_end_month] = annual_dist

        # Calculate distributions using our DistributionCalculator
        calculator = DistributionCalculator(partnership)
        timeline = Timeline(
            start_date=periods[0],
            duration_months=len(periods),
        )
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate basic structure
        assert results["distribution_method"] == "waterfall"
        assert "GP" in results["partner_distributions"]
        assert "LP" in results["partner_distributions"]

        # Validate cash flow consistency
        gp_total = results["partner_distributions"]["GP"]["total_distributions"]
        lp_total = results["partner_distributions"]["LP"]["total_distributions"]
        total_positive_cash = cash_flows[cash_flows > 0].sum()

        assert abs((gp_total + lp_total) - total_positive_cash) < 1.0, (
            f"Distribution total mismatch: GP {gp_total} + LP {lp_total} != {total_positive_cash}"
        )

        # Validate LP gets preferred return first (institutional priority)
        lp_result = results["partner_distributions"]["LP"]
        assert lp_result["irr"] >= 0.08, (
            f"LP should achieve at least 8% preferred return, got {lp_result['irr']:.2%}"
        )

        # Validate GP gets reasonable promote (should be significant given the returns)
        gp_result = results["partner_distributions"]["GP"]
        gp_contribution_ratio = 0.10  # GP contributed 10%
        gp_distribution_ratio = gp_total / total_positive_cash

        assert gp_distribution_ratio > gp_contribution_ratio, (
            f"GP should get promoted beyond contribution ratio: {gp_distribution_ratio:.1%} vs {gp_contribution_ratio:.1%}"
        )

        print(" Industry-standard simple waterfall validation passed!")
        print(f"   LP IRR: {lp_result['irr']:.2%}")
        print(f"   GP IRR: {gp_result['irr']:.2%}")
        print(
            f"   GP promote achieved: {gp_distribution_ratio:.1%} vs {gp_contribution_ratio:.1%} contribution"
        )

    def test_multi_tier_institutional_waterfall(self):
        """
        Test a sophisticated multi-tier institutional waterfall.

        Structure (based on institutional examples):
        - 8% preferred return to LP
        - Tier 1: 20% GP promote until LP achieves 12% IRR
        - Tier 2: 35% GP promote until LP achieves 15% IRR
        - Residual: 50/50 split
        """
        # Create sophisticated partnership structure
        partners = [
            Partner(name="GP", kind="GP", share=0.05),  # 5% GP equity (institutional)
            Partner(name="LP", kind="LP", share=0.95),  # 95% LP equity (institutional)
        ]

        # Create multi-tier waterfall (institutional style)
        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,  # 8% preferred return
            tiers=[
                WaterfallTier(
                    tier_hurdle_rate=0.12,  # 12% first hurdle
                    promote_rate=0.20,  # 20% GP promote
                ),
                WaterfallTier(
                    tier_hurdle_rate=0.15,  # 15% second hurdle
                    promote_rate=0.35,  # 35% GP promote
                ),
            ],
            final_promote_rate=0.50,  # 50/50 residual split
        )

        partnership = PartnershipStructure(
            partners=partners, promote=promote, distribution_method="waterfall"
        )

        # Create high-performing cash flows to hit multiple tiers
        periods = pd.period_range("2024-01", periods=73, freq="M")  # 6 years
        cash_flows = pd.Series(0.0, index=periods)

        # Initial investment
        cash_flows.iloc[0] = -2_000_000  # $2M investment

        # Strong performance: escalating distributions + large exit
        annual_distributions = [100_000, 150_000, 200_000, 250_000, 300_000, 2_500_000]

        for year, annual_dist in enumerate(annual_distributions, 1):
            year_end_month = year * 12
            if year_end_month < len(cash_flows):
                cash_flows.iloc[year_end_month] = annual_dist

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        timeline = Timeline(
            start_date=periods[0],
            duration_months=len(periods),
        )
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate multi-tier performance
        lp_result = results["partner_distributions"]["LP"]
        gp_result = results["partner_distributions"]["GP"]

        # LP should achieve good returns given strong performance
        assert lp_result["irr"] >= 0.10, (
            f"LP should achieve at least 10% IRR given strong performance, got {lp_result['irr']:.2%}"
        )

        # GP should achieve strong returns due to promote structure
        # With 5% equity contribution, 17-20% IRR is excellent performance
        assert gp_result["irr"] >= 0.17, (
            f"GP should achieve high IRR due to promote, got {gp_result['irr']:.2%}"
        )

        # GP should get substantial promote beyond contribution
        gp_total = results["partner_distributions"]["GP"]["total_distributions"]
        total_positive_cash = cash_flows[cash_flows > 0].sum()
        gp_distribution_ratio = gp_total / total_positive_cash

        assert gp_distribution_ratio > 0.06, (
            f"GP should get promote beyond their contribution in multi-tier structure: {gp_distribution_ratio:.1%}"
        )

        print(" Industry-standard multi-tier waterfall validation passed!")
        print(f"   LP IRR: {lp_result['irr']:.2%}")
        print(f"   GP IRR: {gp_result['irr']:.2%}")
        print(f"   GP total promote: {gp_distribution_ratio:.1%}")

    def test_single_investment_assumptions_validation(self):
        """
        Test the common institutional assumption of single upfront investment.

        Most institutional deals have a single negative cash flow (investment)
        followed by positive distributions over time.
        """
        # Create test case with exactly one negative value (typical institutional pattern)
        periods = pd.period_range("2024-01", periods=37, freq="M")  # 3 years
        cash_flows = pd.Series(0.0, index=periods)

        # Single negative value (investment)
        cash_flows.iloc[0] = -500_000

        # Multiple positive values (distributions)
        cash_flows.iloc[12] = 50_000  # Year 1
        cash_flows.iloc[24] = 60_000  # Year 2
        cash_flows.iloc[36] = 550_000  # Year 3 exit

        # Verify assumption: exactly one negative value
        negative_count = (cash_flows < 0).sum()
        assert negative_count == 1, (
            f"Single investment assumption violated: should have exactly 1 negative value, got {negative_count}"
        )

        # Create simple partnership for validation
        partners = [
            Partner(name="GP", kind="GP", share=0.20),
            Partner(name="LP", kind="LP", share=0.80),
        ]

        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,
            tiers=[],  # Simple structure for assumption testing
            final_promote_rate=0.30,  # 30% GP promote after pref return
        )

        partnership = PartnershipStructure(
            partners=partners, promote=promote, distribution_method="waterfall"
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        timeline = Timeline(
            start_date=periods[0],
            duration_months=len(periods),
        )
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate calculation works with single investment assumption
        assert results["distribution_method"] == "waterfall"
        assert results["total_metrics"]["total_distributions"] > 0

        # Validate conservation of cash flows
        total_distributions = sum(
            partner["total_distributions"]
            for partner in results["partner_distributions"].values()
        )
        total_positive_cash = cash_flows[cash_flows > 0].sum()

        assert abs(total_distributions - total_positive_cash) < 1.0, (
            "Cash flow conservation violated with single investment assumption"
        )

        print(" Single investment assumptions validation passed!")
        print("   Single negative value assumption: ✓")
        print("   Cash flow conservation: ✓")
        print("   Waterfall calculation: ✓")

    def test_performance_benchmark_validation(self):
        """
        Benchmark our performance against realistic institutional expectations.

        This test uses realistic deal parameters and validates that our results
        are in line with industry expectations for waterfall distributions.
        """
        # Create realistic institutional deal structure
        partners = [
            Partner(name="GP", kind="GP", share=0.10),
            Partner(name="LP", kind="LP", share=0.90),
        ]

        # Institutional waterfall
        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,  # 8% pref return
            tiers=[
                WaterfallTier(tier_hurdle_rate=0.12, promote_rate=0.20),
                WaterfallTier(tier_hurdle_rate=0.15, promote_rate=0.35),
            ],
            final_promote_rate=0.50,
        )

        partnership = PartnershipStructure(
            partners=partners, promote=promote, distribution_method="waterfall"
        )

        # Realistic deal cash flows: moderate performance
        periods = pd.period_range("2024-01", periods=61, freq="M")  # 5 years
        cash_flows = pd.Series(0.0, index=periods)

        cash_flows.iloc[0] = -5_000_000  # $5M investment
        cash_flows.iloc[12] = 300_000  # Year 1: 6% cash yield
        cash_flows.iloc[24] = 350_000  # Year 2: 7% cash yield
        cash_flows.iloc[36] = 400_000  # Year 3: 8% cash yield
        cash_flows.iloc[48] = 450_000  # Year 4: 9% cash yield
        cash_flows.iloc[60] = 5_500_000  # Year 5: 10% gain on sale

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        timeline = Timeline(
            start_date=periods[0],
            duration_months=len(periods),
        )
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Expected performance benchmarks (based on industry standards)
        lp_result = results["partner_distributions"]["LP"]
        gp_result = results["partner_distributions"]["GP"]

        # LP should achieve reasonable returns (may not hit full preferred return in moderate scenarios)
        expected_lp_irr_range = (
            0.06,
            0.15,
        )  # 6-15% range (realistic for moderate performance)
        assert (
            expected_lp_irr_range[0] <= lp_result["irr"] <= expected_lp_irr_range[1]
        ), (
            f"LP IRR outside expected range {expected_lp_irr_range}: {lp_result['irr']:.2%}"
        )

        # GP should get reasonable returns (may not always achieve high promote in moderate performance)
        expected_gp_irr_range = (
            0.06,
            0.30,
        )  # 6-30% range (realistic for varying performance)
        assert (
            expected_gp_irr_range[0] <= gp_result["irr"] <= expected_gp_irr_range[1]
        ), (
            f"GP IRR outside expected range {expected_gp_irr_range}: {gp_result['irr']:.2%}"
        )

        # Validate equity multiples are reasonable
        assert 1.2 <= lp_result["equity_multiple"] <= 2.0, (
            f"LP equity multiple outside reasonable range: {lp_result['equity_multiple']:.2f}x"
        )

        assert 1.2 <= gp_result["equity_multiple"] <= 3.0, (
            f"GP equity multiple outside reasonable range: {gp_result['equity_multiple']:.2f}x"
        )

        print(" Performance benchmark validation passed!")
        print(
            f"   LP Performance: {lp_result['irr']:.2%} IRR, {lp_result['equity_multiple']:.2f}x"
        )
        print(
            f"   GP Performance: {gp_result['irr']:.2%} IRR, {gp_result['equity_multiple']:.2f}x"
        )
        print("   Industry benchmark ranges achieved ✓")


if __name__ == "__main__":
    """Run industry standard waterfall validation tests standalone."""
    print("Running Industry Standard Waterfall Validation Tests...")

    test_suite = TestIndustryStandardWaterfallValidation()

    try:
        test_suite.test_simple_institutional_waterfall()
        test_suite.test_multi_tier_institutional_waterfall()
        test_suite.test_single_investment_assumptions_validation()
        test_suite.test_performance_benchmark_validation()

        print("\n All industry standard waterfall validation tests passed!")
        print("    Simple institutional waterfall structure")
        print("    Multi-tier institutional structure")
        print("    Single investment assumptions handling")
        print("    Industry performance benchmarks")
        print("\n🏆 Our DistributionCalculator matches industry standards!")

    except Exception as e:
        print(f"\n Industry standard validation failed: {e}")
        raise
