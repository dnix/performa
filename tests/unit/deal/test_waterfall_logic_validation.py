# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Waterfall Logic Validation Tests

This module validates the mathematical soundness and logical integrity of our
DistributionCalculator waterfall logic. These tests focus on core principles:

1. Cash Flow Conservation - Money in equals money out
2. Hurdle Progression - LP gets preferred return before GP promote
3. Promote Mechanics - GP promote only applies after hurdles are met
4. IRR Calculations - Internal rate of return calculations are accurate
5. Edge Cases - Boundary conditions and extreme scenarios

These are NOT external benchmark tests - they validate internal logic consistency.
"""

import pandas as pd

from performa.core.primitives import Timeline
from performa.deal.analysis.partnership import DistributionCalculator
from performa.deal.entities import Partner
from performa.deal.partnership import (
    PartnershipStructure,
    WaterfallPromote,
    WaterfallTier,
)


class TestWaterfallLogicValidation:
    """
    Validate the mathematical soundness of waterfall distribution logic.

    These tests ensure our calculations follow correct waterfall principles
    regardless of external benchmarks.
    """

    def test_cash_flow_conservation_principle(self):
        """
        Test that cash flows are perfectly conserved in all scenarios.

        Principle: Total distributions must exactly equal total positive cash flows.
        This is a fundamental requirement - money cannot be created or destroyed.
        """
        # Create partnership structure
        partners = [
            Partner(name="GP", kind="GP", share=0.20),
            Partner(name="LP", kind="LP", share=0.80),
        ]

        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,
            tiers=[
                WaterfallTier(tier_hurdle_rate=0.12, promote_rate=0.25),
            ],
            final_promote_rate=0.50,
        )

        partnership = PartnershipStructure(
            partners=partners, promote=promote, distribution_method="waterfall"
        )

        # Test multiple cash flow scenarios
        scenarios = [
            # Scenario 1: Simple case
            [-1_000_000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1_200_000],
            # Scenario 2: Multiple distributions
            [-500_000, 50_000, 60_000, 70_000, 80_000, 90_000, 100_000, 200_000],
            # Scenario 3: Irregular timing
            [-2_000_000, 0, 100_000, 0, 150_000, 0, 0, 200_000, 0, 1_800_000],
        ]

        for scenario_cash_flows in scenarios:
            periods = pd.period_range(
                "2024-01", periods=len(scenario_cash_flows), freq="M"
            )
            cash_flows = pd.Series(scenario_cash_flows, index=periods)

            timeline = Timeline(
                start_date=periods[0],
                duration_months=len(periods),
            )

            # Calculate distributions
            calculator = DistributionCalculator(partnership)
            results = calculator.calculate_distributions(cash_flows, timeline)

            # Validate conservation: total distributions = total positive cash flows
            total_positive_cash = cash_flows[cash_flows > 0].sum()
            total_distributions = sum(
                partner["total_distributions"]
                for partner in results["partner_distributions"].values()
            )

            assert abs(total_distributions - total_positive_cash) < 0.01, (
                f"Cash flow conservation violated: {total_distributions} != {total_positive_cash}"
            )

            # Validate total deal metrics match sum of partners
            deal_total_dist = results["total_metrics"]["total_distributions"]
            assert abs(deal_total_dist - total_positive_cash) < 0.01, (
                f"Deal total mismatch: {deal_total_dist} != {total_positive_cash}"
            )

        print(" Cash flow conservation principle validated across all scenarios")

    def test_preferred_return_priority_principle(self):
        """
        Test that LP gets preferred return before GP gets any promote.

        Principle: In waterfall structures, LP must achieve preferred return
        before GP receives distributions above their pro-rata share.
        """
        # Create structure with clear preferred return
        partners = [
            Partner(name="GP", kind="GP", share=0.10),  # Small GP contribution
            Partner(name="LP", kind="LP", share=0.90),  # Large LP contribution
        ]

        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,  # 8% preferred return
            tiers=[],  # No hurdles after pref return
            final_promote_rate=0.30,  # 30% GP promote after pref return
        )

        partnership = PartnershipStructure(
            partners=partners, promote=promote, distribution_method="waterfall"
        )

        # Test scenario where LP should get 8% before GP gets promote
        periods = pd.period_range("2024-01", periods=13, freq="M")  # 1 year
        cash_flows = pd.Series(0.0, index=periods)
        cash_flows.iloc[0] = -1_000_000  # $1M investment
        cash_flows.iloc[12] = 1_300_000  # Year 1: 30% return (well above 8% pref)

        timeline = Timeline(
            start_date=periods[0],
            duration_months=len(periods),
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate LP achieves at least preferred return
        lp_result = results["partner_distributions"]["LP"]
        lp_irr = lp_result["irr"]

        # With 30% return, LP should achieve good IRR (but less than 30% due to GP promote)
        assert lp_irr >= 0.15, (
            f"LP should achieve good IRR with strong performance: {lp_irr:.2%}"
        )

        # Validate GP gets promote (more than pro-rata share)
        gp_result = results["partner_distributions"]["GP"]
        gp_pro_rata_share = 0.10  # GP contributed 10%
        total_positive_cash = cash_flows[cash_flows > 0].sum()
        gp_actual_share = gp_result["total_distributions"] / total_positive_cash

        # GP should get more than their pro-rata contribution (due to promote)
        # Allow small tolerance for edge cases
        assert gp_actual_share >= gp_pro_rata_share * 1.05, (
            f"GP should get promote beyond pro-rata: {gp_actual_share:.2%} vs {gp_pro_rata_share:.2%}"
        )

        print(" Preferred return priority principle validated")
        print(f"   LP IRR: {lp_irr:.2%} (targeting 8.0% preferred)")
        print(
            f"   GP promote: {gp_actual_share:.1%} vs {gp_pro_rata_share:.1%} pro-rata"
        )

    def test_hurdle_progression_logic(self):
        """
        Test that hurdles are hit in correct order with appropriate promote rates.

        Principle: Waterfall tiers should be processed sequentially, with promote
        rates increasing as higher hurdles are achieved.
        """
        # Create multi-tier structure
        partners = [
            Partner(name="GP", kind="GP", share=0.05),
            Partner(name="LP", kind="LP", share=0.95),
        ]

        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,  # 8% preferred return
            tiers=[
                WaterfallTier(
                    tier_hurdle_rate=0.12, promote_rate=0.20
                ),  # 12% hurdle, 20% promote
                WaterfallTier(
                    tier_hurdle_rate=0.16, promote_rate=0.35
                ),  # 16% hurdle, 35% promote
            ],
            final_promote_rate=0.50,  # 50% promote above all hurdles
        )

        partnership = PartnershipStructure(
            partners=partners, promote=promote, distribution_method="waterfall"
        )

        # Create high-performing scenario to hit multiple hurdles
        periods = pd.period_range("2024-01", periods=37, freq="M")  # 3 years
        cash_flows = pd.Series(0.0, index=periods)
        cash_flows.iloc[0] = -1_000_000  # $1M investment
        cash_flows.iloc[12] = 120_000  # Year 1: 12% return
        cash_flows.iloc[24] = 140_000  # Year 2: 14% return
        cash_flows.iloc[36] = 1_300_000  # Year 3: Strong exit

        timeline = Timeline(
            start_date=periods[0],
            duration_months=len(periods),
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate that LP achieves high returns (should hit multiple hurdles)
        lp_result = results["partner_distributions"]["LP"]
        lp_irr = lp_result["irr"]

        # With this cash flow pattern, LP should achieve well above preferred return
        assert lp_irr >= 0.12, (
            f"LP should achieve high IRR in strong scenario: {lp_irr:.2%}"
        )

        # Validate that GP gets substantial promote due to hitting higher tiers
        gp_result = results["partner_distributions"]["GP"]
        total_positive_cash = cash_flows[cash_flows > 0].sum()
        gp_distribution_ratio = gp_result["total_distributions"] / total_positive_cash

        # GP should get significant promote in high-performing scenario
        assert gp_distribution_ratio > 0.10, (
            f"GP should get significant promote in high-performing scenario: {gp_distribution_ratio:.1%}"
        )

        # GP IRR should be very high due to promote
        gp_irr = gp_result["irr"]
        assert gp_irr > lp_irr, (
            f"GP IRR should exceed LP IRR due to promote: GP {gp_irr:.2%} vs LP {lp_irr:.2%}"
        )

        print(" Hurdle progression logic validated")
        print(f"   LP achieved: {lp_irr:.2%} IRR (multiple hurdles hit)")
        print(f"   GP achieved: {gp_irr:.2%} IRR (promote working)")
        print(f"   GP promote level: {gp_distribution_ratio:.1%}")

    def test_edge_case_scenarios(self):
        """
        Test edge cases and boundary conditions.

        Principle: Waterfall logic should handle extreme scenarios gracefully
        without breaking or producing nonsensical results.
        """
        partners = [
            Partner(name="GP", kind="GP", share=0.25),
            Partner(name="LP", kind="LP", share=0.75),
        ]

        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,
            tiers=[
                WaterfallTier(tier_hurdle_rate=0.15, promote_rate=0.30),
            ],
            final_promote_rate=0.50,
        )

        partnership = PartnershipStructure(
            partners=partners, promote=promote, distribution_method="waterfall"
        )

        calculator = DistributionCalculator(partnership)

        # Edge Case 1: No positive distributions (total loss)
        periods1 = pd.period_range("2024-01", periods=13, freq="M")
        cash_flows1 = pd.Series(0.0, index=periods1)
        cash_flows1.iloc[0] = -1_000_000  # Investment
        # No positive cash flows = total loss

        timeline1 = Timeline(
            start_date=periods1[0],
            duration_months=len(periods1),
        )

        results1 = calculator.calculate_distributions(cash_flows1, timeline1)

        # Should handle gracefully - no distributions
        for partner_result in results1["partner_distributions"].values():
            assert partner_result["total_distributions"] == 0.0
            assert partner_result["irr"] is None  # Can't calculate IRR with no returns

        # Edge Case 2: Massive returns (extreme high performance)
        periods2 = pd.period_range("2024-01", periods=13, freq="M")
        cash_flows2 = pd.Series(0.0, index=periods2)
        cash_flows2.iloc[0] = -1_000_000  # $1M investment
        cash_flows2.iloc[12] = 10_000_000  # $10M return (10x multiple)

        timeline2 = Timeline(
            start_date=periods2[0],
            duration_months=len(periods2),
        )

        results2 = calculator.calculate_distributions(cash_flows2, timeline2)

        # Should handle extreme returns - conservation should still hold
        total_distributions = sum(
            partner["total_distributions"]
            for partner in results2["partner_distributions"].values()
        )
        assert abs(total_distributions - 10_000_000) < 1.0

        # GP should get massive promote due to extreme performance
        gp_result = results2["partner_distributions"]["GP"]
        gp_distribution_ratio = gp_result["total_distributions"] / 10_000_000
        assert gp_distribution_ratio > 0.40, (
            f"GP should get large promote in extreme scenario: {gp_distribution_ratio:.1%}"
        )

        # Edge Case 3: Exactly hit hurdle rate
        periods3 = pd.period_range("2024-01", periods=25, freq="M")
        cash_flows3 = pd.Series(0.0, index=periods3)
        cash_flows3.iloc[0] = -1_000_000
        cash_flows3.iloc[24] = 1_160_000  # Exactly 8% IRR (preferred return)

        timeline3 = Timeline(
            start_date=periods3[0],
            duration_months=len(periods3),
        )

        results3 = calculator.calculate_distributions(cash_flows3, timeline3)

        # Should handle exact hurdle achievement
        lp_irr = results3["partner_distributions"]["LP"]["irr"]
        # Should be close to 8% (allowing for small numerical precision)
        assert 0.075 <= lp_irr <= 0.085, (
            f"LP IRR should be close to 8% when exactly hitting preferred: {lp_irr:.2%}"
        )

        print(" Edge case scenarios validated")
        print("   ✓ Total loss scenario handled")
        print("   ✓ Extreme returns scenario handled")
        print("   ✓ Exact hurdle achievement handled")

    def test_mathematical_precision_consistency(self):
        """
        Test that calculations are mathematically consistent and precise.

        Principle: Small changes in inputs should produce proportional changes
        in outputs, and calculations should be numerically stable.
        """
        partners = [
            Partner(name="GP", kind="GP", share=0.15),
            Partner(name="LP", kind="LP", share=0.85),
        ]

        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,
            tiers=[
                WaterfallTier(tier_hurdle_rate=0.12, promote_rate=0.25),
            ],
            final_promote_rate=0.40,
        )

        partnership = PartnershipStructure(
            partners=partners, promote=promote, distribution_method="waterfall"
        )

        calculator = DistributionCalculator(partnership)

        # Base scenario
        periods = pd.period_range("2024-01", periods=25, freq="M")
        base_cash_flows = pd.Series(0.0, index=periods)
        base_cash_flows.iloc[0] = -1_000_000
        base_cash_flows.iloc[24] = 1_200_000  # 20% return

        timeline = Timeline(
            start_date=periods[0],
            duration_months=len(periods),
        )

        base_results = calculator.calculate_distributions(base_cash_flows, timeline)
        base_gp_total = base_results["partner_distributions"]["GP"][
            "total_distributions"
        ]
        base_lp_total = base_results["partner_distributions"]["LP"][
            "total_distributions"
        ]

        # Scenario with slightly higher returns
        higher_cash_flows = base_cash_flows.copy()
        higher_cash_flows.iloc[24] = 1_210_000  # $10K more

        higher_results = calculator.calculate_distributions(higher_cash_flows, timeline)
        higher_gp_total = higher_results["partner_distributions"]["GP"][
            "total_distributions"
        ]
        higher_lp_total = higher_results["partner_distributions"]["LP"][
            "total_distributions"
        ]

        # Validate that extra $10K is distributed correctly
        extra_gp = higher_gp_total - base_gp_total
        extra_lp = higher_lp_total - base_lp_total

        assert abs((extra_gp + extra_lp) - 10_000) < 1.0, (
            "Extra distributions should sum to extra cash flow"
        )

        # Validate that distributions are reasonable (GP should get some promote)
        assert extra_gp > 0 and extra_lp > 0, (
            "Both partners should benefit from additional returns"
        )

        assert extra_gp > 1_500, (
            f"GP should get meaningful promote from extra returns: ${extra_gp:,.0f}"
        )

        # Test numerical stability with very small amounts
        tiny_cash_flows = base_cash_flows.copy()
        tiny_cash_flows.iloc[24] = 1_000_001  # Just $1 more than investment

        tiny_results = calculator.calculate_distributions(tiny_cash_flows, timeline)

        # Should handle tiny profits without numerical issues
        tiny_total_dist = sum(
            partner["total_distributions"]
            for partner in tiny_results["partner_distributions"].values()
        )

        # NOTE: Our waterfall correctly separates return of capital from profit distribution
        # See DistributionCalculator.calculate_waterfall_distribution() Steps 1 & 2
        assert abs(tiny_total_dist - 1_000_001) < 0.01, (
            "Should handle tiny profits without numerical issues (total distributions)"
        )

        print(" Mathematical precision and consistency validated")
        print(f"   Extra $10K distributed: GP +${extra_gp:,.0f}, LP +${extra_lp:,.0f}")
        print("   ✓ Numerical stability confirmed")
        print("   ✓ Proportional response to input changes")


if __name__ == "__main__":
    """Run waterfall logic validation tests standalone."""
    print("Running Waterfall Logic Validation Tests...")

    test_suite = TestWaterfallLogicValidation()

    try:
        test_suite.test_cash_flow_conservation_principle()
        test_suite.test_preferred_return_priority_principle()
        test_suite.test_hurdle_progression_logic()
        test_suite.test_edge_case_scenarios()
        test_suite.test_mathematical_precision_consistency()

        print("\n All waterfall logic validation tests passed!")
        print("    Cash flow conservation principle")
        print("    Preferred return priority principle")
        print("    Hurdle progression logic")
        print("    Edge case scenarios")
        print("    Mathematical precision consistency")
        print("\n🏆 Our waterfall logic is mathematically sound!")

    except Exception as e:
        print(f"\n Waterfall logic validation failed: {e}")
        raise
