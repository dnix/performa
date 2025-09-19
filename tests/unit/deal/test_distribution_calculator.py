# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for Distribution Calculator

This module tests the partnership distribution calculator logic.
"""

from datetime import datetime
from unittest.mock import Mock

import pandas as pd
import pytest

from performa.core.primitives import Timeline
from performa.deal import create_simple_partnership
from performa.deal.distribution_calculator import (
    DistributionCalculator,
    calculate_partner_distributions_with_structure,
)
from performa.deal.entities import Partner
from performa.deal.partnership import (
    CarryPromote,
    PartnershipStructure,
    WaterfallPromote,
    WaterfallTier,
)


class TestDistributionCalculator:
    """Tests for the DistributionCalculator class."""

    def test_simple_pari_passu_distribution(self):
        """Test basic pari passu distribution with 2 partners."""
        # Create partnership: 30% GP, 70% LP
        gp = Partner(name="Development GP", kind="GP", share=0.30)
        lp = Partner(name="Institutional LP", kind="LP", share=0.70)
        partnership = PartnershipStructure(partners=[gp, lp])

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=12)

        # Create cash flows: $10M investment, $15M return
        cash_flows = pd.Series(
            [
                -10_000_000,  # Investment period
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,  # Hold periods
                15_000_000,  # Sale period
            ],
            index=timeline.period_index,
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_pari_passu_distribution(cash_flows, timeline)

        # Validate results structure
        assert results["distribution_method"] == "pari_passu"
        assert "partner_distributions" in results
        assert "total_metrics" in results
        assert "partnership_summary" in results

        # Validate partner distributions
        gp_results = results["partner_distributions"]["Development GP"]
        lp_results = results["partner_distributions"]["Institutional LP"]

        # GP should invest 30% and receive 30%
        assert gp_results["total_investment"] == 3_000_000  # 30% of $10M
        assert gp_results["total_distributions"] == 4_500_000  # 30% of $15M
        assert gp_results["net_profit"] == 1_500_000  # $4.5M - $3M
        assert gp_results["equity_multiple"] == 1.5  # $4.5M / $3M
        assert gp_results["ownership_percentage"] == 0.30

        # LP should invest 70% and receive 70%
        assert lp_results["total_investment"] == 7_000_000  # 70% of $10M
        assert lp_results["total_distributions"] == 10_500_000  # 70% of $15M
        assert lp_results["net_profit"] == 3_500_000  # $10.5M - $7M
        assert lp_results["equity_multiple"] == 1.5  # $10.5M / $7M
        assert lp_results["ownership_percentage"] == 0.70

        # Validate total metrics
        total_metrics = results["total_metrics"]
        assert total_metrics["total_investment"] == 10_000_000
        assert total_metrics["total_distributions"] == 15_000_000
        assert total_metrics["net_profit"] == 5_000_000
        assert total_metrics["equity_multiple"] == 1.5

        # Validate partnership summary
        partnership_summary = results["partnership_summary"]
        assert partnership_summary["partner_count"] == 2
        assert partnership_summary["gp_total_share"] == 0.30
        assert partnership_summary["lp_total_share"] == 0.70
        assert partnership_summary["gp_count"] == 1
        assert partnership_summary["lp_count"] == 1

    def test_multi_period_cash_flows(self):
        """Test distribution with multiple cash flow periods."""
        # Create partnership: 25% GP, 75% LP
        gp = Partner(name="GP", kind="GP", share=0.25)
        lp = Partner(name="LP", kind="LP", share=0.75)
        partnership = PartnershipStructure(partners=[gp, lp])

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=6)

        # Create cash flows: investment over 2 periods, returns over 2 periods
        cash_flows = pd.Series(
            [
                -5_000_000,  # Period 1: Initial investment
                -3_000_000,  # Period 2: Additional investment
                0,  # Period 3: No cash flow
                0,  # Period 4: No cash flow
                6_000_000,  # Period 5: Partial return
                4_000_000,  # Period 6: Final return
            ],
            index=timeline.period_index,
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate total metrics
        total_metrics = results["total_metrics"]
        assert total_metrics["total_investment"] == 8_000_000  # $5M + $3M
        assert total_metrics["total_distributions"] == 10_000_000  # $6M + $4M
        assert total_metrics["net_profit"] == 2_000_000
        assert total_metrics["equity_multiple"] == 1.25

        # Validate GP cash flows
        gp_results = results["partner_distributions"]["GP"]
        gp_cash_flows = gp_results["cash_flows"]

        # GP should get 25% of each cash flow
        assert gp_cash_flows.iloc[0] == -1_250_000  # 25% of -$5M
        assert gp_cash_flows.iloc[1] == -750_000  # 25% of -$3M
        assert gp_cash_flows.iloc[2] == 0
        assert gp_cash_flows.iloc[3] == 0
        assert gp_cash_flows.iloc[4] == 1_500_000  # 25% of $6M
        assert gp_cash_flows.iloc[5] == 1_000_000  # 25% of $4M

        # Validate LP cash flows
        lp_results = results["partner_distributions"]["LP"]
        lp_cash_flows = lp_results["cash_flows"]

        # LP should get 75% of each cash flow
        assert lp_cash_flows.iloc[0] == -3_750_000  # 75% of -$5M
        assert lp_cash_flows.iloc[1] == -2_250_000  # 75% of -$3M
        assert lp_cash_flows.iloc[2] == 0
        assert lp_cash_flows.iloc[3] == 0
        assert lp_cash_flows.iloc[4] == 4_500_000  # 75% of $6M
        assert lp_cash_flows.iloc[5] == 3_000_000  # 75% of $4M

    def test_complex_partnership_structure(self):
        """Test distribution with multiple GPs and LPs."""
        # Create complex partnership
        gp1 = Partner(name="Lead GP", kind="GP", share=0.15)
        gp2 = Partner(name="Co-GP", kind="GP", share=0.10)
        lp1 = Partner(name="Institutional LP", kind="LP", share=0.50)
        lp2 = Partner(name="Family Office LP", kind="LP", share=0.25)

        partnership = PartnershipStructure(
            partners=[gp1, gp2, lp1, lp2], distribution_method="pari_passu"
        )

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=3)

        # Create cash flows: $20M investment, $30M return
        cash_flows = pd.Series(
            [
                -20_000_000,  # Investment
                0,  # Hold
                30_000_000,  # Return
            ],
            index=timeline.period_index,
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate all partners got their proportional share
        gp1_results = results["partner_distributions"]["Lead GP"]
        gp2_results = results["partner_distributions"]["Co-GP"]
        lp1_results = results["partner_distributions"]["Institutional LP"]
        lp2_results = results["partner_distributions"]["Family Office LP"]

        # Lead GP: 15%
        assert gp1_results["total_investment"] == 3_000_000  # 15% of $20M
        assert gp1_results["total_distributions"] == 4_500_000  # 15% of $30M
        assert gp1_results["equity_multiple"] == 1.5

        # Co-GP: 10%
        assert gp2_results["total_investment"] == 2_000_000  # 10% of $20M
        assert gp2_results["total_distributions"] == 3_000_000  # 10% of $30M
        assert gp2_results["equity_multiple"] == 1.5

        # Institutional LP: 50%
        assert lp1_results["total_investment"] == 10_000_000  # 50% of $20M
        assert lp1_results["total_distributions"] == 15_000_000  # 50% of $30M
        assert lp1_results["equity_multiple"] == 1.5

        # Family Office LP: 25%
        assert lp2_results["total_investment"] == 5_000_000  # 25% of $20M
        assert lp2_results["total_distributions"] == 7_500_000  # 25% of $30M
        assert lp2_results["equity_multiple"] == 1.5

        # Validate partnership summary
        partnership_summary = results["partnership_summary"]
        assert partnership_summary["partner_count"] == 4
        assert partnership_summary["gp_total_share"] == 0.25  # 15% + 10%
        assert partnership_summary["lp_total_share"] == 0.75  # 50% + 25%
        assert partnership_summary["gp_count"] == 2
        assert partnership_summary["lp_count"] == 2

    def test_create_partner_summary_dataframe(self):
        """Test creating a formatted summary DataFrame."""
        # Create partnership
        gp = Partner(name="Test GP", kind="GP", share=0.20)
        lp = Partner(name="Test LP", kind="LP", share=0.80)
        partnership = PartnershipStructure(partners=[gp, lp])

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=2)

        # Create cash flows
        cash_flows = pd.Series(
            [
                -1_000_000,  # Investment
                1_200_000,  # Return
            ],
            index=timeline.period_index,
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Create summary DataFrame
        summary_df = calculator.create_partner_summary_dataframe(results)

        # Validate DataFrame structure
        assert len(summary_df) == 3  # 2 partners + 1 total row
        assert list(summary_df.columns) == [
            "Partner",
            "Type",
            "Ownership",
            "Investment",
            "Distributions",
            "Net Profit",
            "Equity Multiple",
            "IRR",
        ]

        # Validate content
        assert summary_df.iloc[0]["Partner"] == "Test GP"
        assert summary_df.iloc[0]["Type"] == "GP"
        assert summary_df.iloc[0]["Ownership"] == "20.0%"
        assert summary_df.iloc[0]["Investment"] == "$200,000"
        assert summary_df.iloc[0]["Distributions"] == "$240,000"
        assert summary_df.iloc[0]["Net Profit"] == "$40,000"
        assert summary_df.iloc[0]["Equity Multiple"] == "1.20x"

        assert summary_df.iloc[1]["Partner"] == "Test LP"
        assert summary_df.iloc[1]["Type"] == "LP"
        assert summary_df.iloc[1]["Ownership"] == "80.0%"
        assert summary_df.iloc[1]["Investment"] == "$800,000"
        assert summary_df.iloc[1]["Distributions"] == "$960,000"
        assert summary_df.iloc[1]["Net Profit"] == "$160,000"
        assert summary_df.iloc[1]["Equity Multiple"] == "1.20x"

        assert summary_df.iloc[2]["Partner"] == "TOTAL"
        assert summary_df.iloc[2]["Type"] == "ALL"
        assert summary_df.iloc[2]["Ownership"] == "100.0%"
        assert summary_df.iloc[2]["Investment"] == "$1,000,000"
        assert summary_df.iloc[2]["Distributions"] == "$1,200,000"
        assert summary_df.iloc[2]["Net Profit"] == "$200,000"
        assert summary_df.iloc[2]["Equity Multiple"] == "1.20x"


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_calculate_partner_distributions_with_structure(self):
        """Test the convenience function for calculating distributions."""
        # Create partnership
        partnership = create_simple_partnership(
            gp_name="Simple GP", gp_share=0.25, lp_name="Simple LP", lp_share=0.75
        )

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=2)

        # Create cash flows
        cash_flows = pd.Series(
            [
                -4_000_000,  # Investment
                5_000_000,  # Return
            ],
            index=timeline.period_index,
        )

        # Calculate distributions using convenience function
        results = calculate_partner_distributions_with_structure(
            partnership, cash_flows, timeline
        )

        # Validate results
        assert results["distribution_method"] == "pari_passu"
        assert "Simple GP" in results["partner_distributions"]
        assert "Simple LP" in results["partner_distributions"]

        # Validate GP results
        gp_results = results["partner_distributions"]["Simple GP"]
        assert gp_results["total_investment"] == 1_000_000  # 25% of $4M
        assert gp_results["total_distributions"] == 1_250_000  # 25% of $5M
        assert gp_results["equity_multiple"] == 1.25

        # Validate LP results
        lp_results = results["partner_distributions"]["Simple LP"]
        assert lp_results["total_investment"] == 3_000_000  # 75% of $4M
        assert lp_results["total_distributions"] == 3_750_000  # 75% of $5M
        assert lp_results["equity_multiple"] == 1.25

    def test_create_simple_partnership(self):
        """Test the helper function for creating simple partnerships."""
        # Create partnership using helper function
        partnership = create_simple_partnership(
            gp_name="Helper GP",
            gp_share=0.30,
            lp_name="Helper LP",
            lp_share=0.70,
            distribution_method="pari_passu",
        )

        # Validate partnership structure
        assert partnership.partner_count == 2
        assert partnership.gp_total_share == 0.30
        assert partnership.lp_total_share == 0.70
        assert partnership.distribution_method == "pari_passu"

        # Validate individual partners
        gp_partner = partnership.get_partner_by_name("Helper GP")
        assert gp_partner is not None
        assert gp_partner.kind == "GP"
        assert gp_partner.share == 0.30

        lp_partner = partnership.get_partner_by_name("Helper LP")
        assert lp_partner is not None
        assert lp_partner.kind == "LP"
        assert lp_partner.share == 0.70

        # Test with waterfall distribution method
        waterfall_partnership = create_simple_partnership(
            gp_name="Waterfall GP",
            gp_share=0.15,
            lp_name="Waterfall LP",
            lp_share=0.85,
            distribution_method="waterfall",
        )

        assert waterfall_partnership.distribution_method == "waterfall"
        assert waterfall_partnership.gp_total_share == 0.15
        assert waterfall_partnership.lp_total_share == 0.85


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_waterfall_without_promote_structure(self):
        """Test that waterfall distribution requires a promote structure."""
        # Create partnership without promote structure
        gp = Partner(name="GP", kind="GP", share=0.20)
        lp = Partner(name="LP", kind="LP", share=0.80)
        partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="waterfall",  # No promote specified
        )

        # Create timeline and cash flows
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=2)
        cash_flows = pd.Series([-1000000, 1200000], index=timeline.period_index)

        # Should raise ValueError when trying waterfall without promote
        calculator = DistributionCalculator(partnership)
        with pytest.raises(
            ValueError, match="Waterfall distribution requires a promote structure"
        ):
            calculator.calculate_waterfall_distribution(cash_flows, timeline)

    def test_waterfall_without_gp_partners(self):
        """Test that waterfall distribution requires at least one GP partner."""
        # Create partnership with only LP partners (no GPs)
        lp1 = Partner(name="LP1", kind="LP", share=0.60)
        lp2 = Partner(name="LP2", kind="LP", share=0.40)
        partnership = PartnershipStructure(
            partners=[lp1, lp2],
            distribution_method="waterfall",
            promote=CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.20),
        )

        # Create timeline and cash flows
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=2)
        cash_flows = pd.Series([-1000000, 1200000], index=timeline.period_index)

        # Should raise ValueError when no GP partners exist
        calculator = DistributionCalculator(partnership)
        with pytest.raises(
            ValueError, match="Carry promote requires at least one GP partner"
        ):
            calculator.calculate_waterfall_distribution(cash_flows, timeline)

    def test_unknown_distribution_method_error(self):
        """Test error handling for unknown distribution method."""
        # Create a mock partnership with invalid distribution method
        gp = Partner(name="GP", kind="GP", share=0.20)
        lp = Partner(name="LP", kind="LP", share=0.80)

        # Create a mock partnership that bypasses Pydantic validation
        mock_partnership = Mock()
        mock_partnership.partners = [gp, lp]
        mock_partnership.distribution_method = "invalid_method"
        mock_partnership.has_promote = False

        # Create timeline and cash flows
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=2)
        cash_flows = pd.Series([-1000000, 1200000], index=timeline.period_index)

        # Should raise ValueError for unknown method
        calculator = DistributionCalculator(mock_partnership)
        with pytest.raises(
            ValueError, match="Unknown distribution method: invalid_method"
        ):
            calculator.calculate_distributions(cash_flows, timeline)

    def test_irr_calculation_edge_cases(self):
        """Test IRR calculation edge cases that can return None."""
        # Create partnership for waterfall testing
        gp = Partner(name="GP", kind="GP", share=0.20)
        lp = Partner(name="LP", kind="LP", share=0.80)
        partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="waterfall",
            promote=CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.20),
        )

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=3)

        # Test case 1: Only positive cash flows (no investment) - should not crash
        only_positive_flows = pd.Series(
            [1000000, 500000, 300000], index=timeline.period_index
        )

        calculator = DistributionCalculator(partnership)
        # This should complete without error even though IRR calculation may fail
        result1 = calculator.calculate_waterfall_distribution(
            only_positive_flows, timeline
        )
        assert result1 is not None
        assert "partner_distributions" in result1

        # Test case 2: Only negative cash flows (no returns) - should not crash
        only_negative_flows = pd.Series(
            [-1000000, -500000, -300000], index=timeline.period_index
        )

        # This should complete without error even though IRR calculation may fail
        result2 = calculator.calculate_waterfall_distribution(
            only_negative_flows, timeline
        )
        assert result2 is not None
        assert "partner_distributions" in result2

        # Test case 3: Extreme values that might cause XIRR to fail - should not crash
        # Create cash flows with very large numbers that might cause numerical issues
        extreme_flows = pd.Series([-1e15, 1e15, 1e15], index=timeline.period_index)

        # This should complete without error even if XIRR calculation throws an exception
        result3 = calculator.calculate_waterfall_distribution(extreme_flows, timeline)
        assert result3 is not None
        assert "partner_distributions" in result3

        # Test case 4: Very small positive returns (realistic edge case)
        minimal_profit_flows = pd.Series(
            [-1000000, 0, 1000001], index=timeline.period_index  # Tiny $1 profit
        )

        # This should complete successfully with minimal profit distribution
        result4 = calculator.calculate_waterfall_distribution(minimal_profit_flows, timeline)
        assert result4 is not None
        assert "partner_distributions" in result4
        
        # With minimal profit, most distributions should go to capital return
        total_metrics = result4["total_metrics"]
        assert total_metrics["net_profit"] == 1  # $1 profit
        assert total_metrics["equity_multiple"] > 1.0  # But still profitable

    def test_zero_cash_flows(self):
        """Test handling of zero cash flows."""
        # Create partnership
        partnership = create_simple_partnership("GP", 0.20, "LP", 0.80)

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=2)

        # Create zero cash flows
        cash_flows = pd.Series([0, 0], index=timeline.period_index)

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate results
        assert results["total_metrics"]["total_investment"] == 0
        assert results["total_metrics"]["total_distributions"] == 0
        assert results["total_metrics"]["net_profit"] == 0
        assert results["total_metrics"]["equity_multiple"] == 0

    def test_only_negative_cash_flows(self):
        """Test handling of only negative cash flows (loss scenario)."""
        # Create partnership
        partnership = create_simple_partnership("GP", 0.25, "LP", 0.75)

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=2)

        # Create only negative cash flows
        cash_flows = pd.Series([-1_000_000, -500_000], index=timeline.period_index)

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate results
        assert results["total_metrics"]["total_investment"] == 1_500_000
        assert results["total_metrics"]["total_distributions"] == 0
        assert results["total_metrics"]["net_profit"] == -1_500_000
        assert results["total_metrics"]["equity_multiple"] == 0

        # Validate partner results
        gp_results = results["partner_distributions"]["GP"]
        assert gp_results["total_investment"] == 375_000  # 25% of $1.5M
        assert gp_results["total_distributions"] == 0
        assert gp_results["net_profit"] == -375_000
        assert gp_results["equity_multiple"] == 0

    def test_unknown_distribution_method(self):
        """Test handling of unknown distribution method."""
        # Test that the PartnershipStructure validation prevents invalid distribution methods
        gp = Partner(name="GP", kind="GP", share=0.20)
        lp = Partner(name="LP", kind="LP", share=0.80)

        # Test valid distribution methods work
        valid_partnership = PartnershipStructure(
            partners=[gp, lp], distribution_method="pari_passu"
        )
        assert valid_partnership.distribution_method == "pari_passu"

        valid_partnership_waterfall = PartnershipStructure(
            partners=[gp, lp], distribution_method="waterfall"
        )
        assert valid_partnership_waterfall.distribution_method == "waterfall"

        # Test invalid distribution method raises validation error during creation
        with pytest.raises(Exception):  # Pydantic will raise validation error
            PartnershipStructure(
                partners=[gp, lp],
                distribution_method="unknown_method",  # type: ignore
            )


class TestWaterfallDistributions:
    """Test waterfall distribution calculations with promotes."""

    def test_simple_carry_promote_distribution(self):
        """Test simple carry promote distribution (pref + fixed carry)."""
        # Create partnership with simple carry promote: 8% pref, 20% carry
        gp = Partner(name="GP", kind="GP", share=0.20)
        lp = Partner(name="LP", kind="LP", share=0.80)

        carry_promote = CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.20)

        partnership = PartnershipStructure(
            partners=[gp, lp], distribution_method="waterfall", promote=carry_promote
        )

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=3)

        # Create cash flows: $10M investment, $15M return (50% return)
        cash_flows = pd.Series(
            [
                -10_000_000,  # Investment
                0,  # Hold period
                15_000_000,  # Return
            ],
            index=timeline.period_index,
        )

        # Calculate waterfall distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate results structure - CarryPromote returns 'carry_promote' method
        assert results["distribution_method"] == "carry_promote"
        assert "partner_distributions" in results
        assert "total_metrics" in results

        # Validate total metrics
        total_metrics = results["total_metrics"]
        assert total_metrics["total_investment"] == 10_000_000
        assert total_metrics["total_distributions"] == 15_000_000
        assert total_metrics["net_profit"] == 5_000_000
        assert total_metrics["equity_multiple"] == 1.5

        # Validate partner distributions
        gp_results = results["partner_distributions"]["GP"]
        lp_results = results["partner_distributions"]["LP"]

        # GP should get 20% of investment
        assert gp_results["total_investment"] == 2_000_000  # 20% of $10M
        assert gp_results["ownership_percentage"] == 0.20

        # LP should get 80% of investment
        assert lp_results["total_investment"] == 8_000_000  # 80% of $10M
        assert lp_results["ownership_percentage"] == 0.80

        # With 50% return and 8% pref hurdle, there should be carry
        # GP should get more than 20% of distributions due to carry
        assert gp_results["total_distributions"] > 3_000_000  # More than 20% of $15M
        assert lp_results["total_distributions"] < 12_000_000  # Less than 80% of $15M

        # Both partners should have positive returns
        assert gp_results["net_profit"] > 0
        assert lp_results["net_profit"] > 0
        assert gp_results["equity_multiple"] > 1.0
        assert lp_results["equity_multiple"] > 1.0

        # Validate waterfall details
        assert results["waterfall_details"]["promote_structure"] == "CarryPromote"

    def test_sophisticated_waterfall_promote_distribution(self):
        """Test sophisticated multi-tier waterfall promote distribution."""
        # Create partnership with sophisticated waterfall promote
        gp = Partner(name="Development GP", kind="GP", share=0.25)
        lp = Partner(name="Institutional LP", kind="LP", share=0.75)

        # Create sophisticated waterfall promote structure
        # 8% pref, then 10% promote at 12% IRR, then 20% promote at 15% IRR, then 30% final
        waterfall_promote = WaterfallPromote(
            pref_hurdle_rate=0.08,
            tiers=[
                WaterfallTier(tier_hurdle_rate=0.12, promote_rate=0.10),
                WaterfallTier(tier_hurdle_rate=0.15, promote_rate=0.20),
            ],
            final_promote_rate=0.30,
        )

        partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="waterfall",
            promote=waterfall_promote,
        )

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=24)

        # Create cash flows: $20M investment, $40M return (100% return)
        cash_flows = pd.Series(
            [
                -20_000_000,  # Investment
                *[0] * 22,  # Hold periods
                40_000_000,  # Return
            ],
            index=timeline.period_index,
        )

        # Calculate waterfall distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate results structure
        assert results["distribution_method"] == "waterfall"
        assert "partner_distributions" in results
        assert "total_metrics" in results

        # Validate total metrics
        total_metrics = results["total_metrics"]
        assert total_metrics["total_investment"] == 20_000_000
        assert total_metrics["total_distributions"] == 40_000_000
        assert total_metrics["net_profit"] == 20_000_000
        assert total_metrics["equity_multiple"] == 2.0

        # Validate partner distributions
        gp_results = results["partner_distributions"]["Development GP"]
        lp_results = results["partner_distributions"]["Institutional LP"]

        # GP should get 25% of investment
        assert gp_results["total_investment"] == 5_000_000  # 25% of $20M
        assert gp_results["ownership_percentage"] == 0.25

        # LP should get 75% of investment
        assert lp_results["total_investment"] == 15_000_000  # 75% of $20M
        assert lp_results["ownership_percentage"] == 0.75

        # With 100% return and sophisticated waterfall, GP should get significant promote
        # GP should get much more than 25% of distributions
        assert gp_results["total_distributions"] > 10_000_000  # More than 25% of $40M
        assert lp_results["total_distributions"] < 30_000_000  # Less than 75% of $40M

        # GP should have higher equity multiple than LP due to promote
        assert gp_results["equity_multiple"] > lp_results["equity_multiple"]

        # Both partners should have positive returns
        assert gp_results["net_profit"] > 0
        assert lp_results["net_profit"] > 0
        assert gp_results["equity_multiple"] > 1.0
        assert lp_results["equity_multiple"] > 1.0

        # Validate waterfall details - Now returns the new polymorphic class name
        assert (
            results["waterfall_details"]["promote_structure"] == "IRRWaterfallPromote"
        )
        assert len(results["waterfall_details"]["tiers_used"]) == 3  # Pref + 2 tiers
        assert results["waterfall_details"]["final_promote_rate"] == 0.30

    def test_carry_promote_below_preferred_return(self):
        """Test carry promote when returns are below preferred return."""
        # Create partnership with carry promote: 12% pref, 20% carry
        gp = Partner(name="GP", kind="GP", share=0.30)
        lp = Partner(name="LP", kind="LP", share=0.70)

        carry_promote = CarryPromote(pref_hurdle_rate=0.12, promote_rate=0.20)

        partnership = PartnershipStructure(
            partners=[gp, lp], distribution_method="waterfall", promote=carry_promote
        )

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=12)

        # Create cash flows: $10M investment, $11M return (10% return, below 12% pref)
        cash_flows = pd.Series(
            [
                -10_000_000,  # Investment
                *[0] * 10,  # Hold periods
                11_000_000,  # Return (below preferred)
            ],
            index=timeline.period_index,
        )

        # Calculate waterfall distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate results structure - CarryPromote returns 'carry_promote' method
        assert results["distribution_method"] == "carry_promote"

        # Validate total metrics
        total_metrics = results["total_metrics"]
        assert total_metrics["total_investment"] == 10_000_000
        assert total_metrics["total_distributions"] == 11_000_000
        assert total_metrics["net_profit"] == 1_000_000
        assert total_metrics["equity_multiple"] == 1.1

        # Validate partner distributions
        gp_results = results["partner_distributions"]["GP"]
        lp_results = results["partner_distributions"]["LP"]

        # With returns below preferred, distribution should be close to pro rata
        # (since no carry is earned)
        expected_gp_distribution = 11_000_000 * 0.30  # 30% of $11M
        expected_lp_distribution = 11_000_000 * 0.70  # 70% of $11M

        # Allow for small variations due to waterfall logic
        assert (
            abs(gp_results["total_distributions"] - expected_gp_distribution) < 100_000
        )
        assert (
            abs(lp_results["total_distributions"] - expected_lp_distribution) < 100_000
        )

        # Validate waterfall details
        assert results["waterfall_details"]["promote_structure"] == "CarryPromote"

    def test_waterfall_promote_with_multi_period_cash_flows(self):
        """Test waterfall promote with multiple investment and return periods."""
        # Create partnership with sophisticated waterfall promote
        gp = Partner(name="GP", kind="GP", share=0.20)
        lp = Partner(name="LP", kind="LP", share=0.80)

        waterfall_promote = WaterfallPromote(
            pref_hurdle_rate=0.10,
            tiers=[WaterfallTier(tier_hurdle_rate=0.15, promote_rate=0.25)],
            final_promote_rate=0.40,
        )

        partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="waterfall",
            promote=waterfall_promote,
        )

        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=6)

        # Create cash flows: staggered investment and returns
        cash_flows = pd.Series(
            [
                -5_000_000,  # Period 1: Initial investment
                -3_000_000,  # Period 2: Additional investment
                0,  # Period 3: Hold
                2_000_000,  # Period 4: Partial return
                0,  # Period 5: Hold
                8_000_000,  # Period 6: Final return
            ],
            index=timeline.period_index,
        )

        # Calculate waterfall distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate results structure
        assert results["distribution_method"] == "waterfall"

        # Validate total metrics
        total_metrics = results["total_metrics"]
        assert total_metrics["total_investment"] == 8_000_000  # $5M + $3M
        assert total_metrics["total_distributions"] == 10_000_000  # $2M + $8M
        assert total_metrics["net_profit"] == 2_000_000
        assert total_metrics["equity_multiple"] == 1.25

        # Validate partner cash flows are properly allocated
        gp_results = results["partner_distributions"]["GP"]
        lp_results = results["partner_distributions"]["LP"]

        gp_cash_flows = gp_results["cash_flows"]
        lp_cash_flows = lp_results["cash_flows"]

        # Validate that investments are allocated proportionally
        assert gp_cash_flows.iloc[0] == -1_000_000  # 20% of -$5M
        assert gp_cash_flows.iloc[1] == -600_000  # 20% of -$3M
        assert lp_cash_flows.iloc[0] == -4_000_000  # 80% of -$5M
        assert lp_cash_flows.iloc[1] == -2_400_000  # 80% of -$3M

        # Validate that returns are allocated according to waterfall
        # (exact amounts depend on waterfall calculation, but should be positive)
        assert gp_cash_flows.iloc[3] > 0  # GP gets some of the $2M return
        assert gp_cash_flows.iloc[5] > 0  # GP gets some of the $8M return
        assert lp_cash_flows.iloc[3] > 0  # LP gets some of the $2M return
        assert lp_cash_flows.iloc[5] > 0  # LP gets some of the $8M return

        # Validate that all cash flows sum correctly
        assert gp_cash_flows.sum() + lp_cash_flows.sum() == cash_flows.sum()

        # Validate waterfall details - Now returns the new polymorphic class name
        assert (
            results["waterfall_details"]["promote_structure"] == "IRRWaterfallPromote"
        )

    def test_carry_vs_waterfall_promote_comparison(self):
        """Test comparing carry vs waterfall promote structures."""
        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=24)

        # Create cash flows: $10M investment, $20M return (100% return)
        cash_flows = pd.Series(
            [
                -10_000_000,  # Investment
                *[0] * 22,  # Hold periods
                20_000_000,  # Return
            ],
            index=timeline.period_index,
        )

        # Test 1: Simple carry promote (pref + fixed carry)
        carry_partnership = PartnershipStructure(
            partners=[
                Partner(name="GP", kind="GP", share=0.20),
                Partner(name="LP", kind="LP", share=0.80),
            ],
            distribution_method="waterfall",
            promote=CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.20),
        )

        calculator_carry = DistributionCalculator(carry_partnership)
        carry_results = calculator_carry.calculate_distributions(cash_flows, timeline)

        # Test 2: Sophisticated waterfall promote
        waterfall_partnership = PartnershipStructure(
            partners=[
                Partner(name="GP", kind="GP", share=0.20),
                Partner(name="LP", kind="LP", share=0.80),
            ],
            distribution_method="waterfall",
            promote=WaterfallPromote(
                pref_hurdle_rate=0.08,
                tiers=[
                    WaterfallTier(tier_hurdle_rate=0.12, promote_rate=0.15),
                    WaterfallTier(tier_hurdle_rate=0.18, promote_rate=0.25),
                ],
                final_promote_rate=0.35,
            ),
        )

        calculator_waterfall = DistributionCalculator(waterfall_partnership)
        waterfall_results = calculator_waterfall.calculate_distributions(
            cash_flows, timeline
        )

        # Compare results
        carry_gp = carry_results["partner_distributions"]["GP"]
        carry_lp = carry_results["partner_distributions"]["LP"]
        waterfall_gp = waterfall_results["partner_distributions"]["GP"]
        waterfall_lp = waterfall_results["partner_distributions"]["LP"]

        # Both should have same investments
        assert carry_gp["total_investment"] == waterfall_gp["total_investment"]
        assert carry_lp["total_investment"] == waterfall_lp["total_investment"]

        # With high returns, waterfall should give GP more than simple carry
        # (because it has higher final promote rate)
        assert waterfall_gp["total_distributions"] > carry_gp["total_distributions"]
        assert waterfall_lp["total_distributions"] < carry_lp["total_distributions"]

        # GP should have higher equity multiple in waterfall
        assert waterfall_gp["equity_multiple"] > carry_gp["equity_multiple"]
        assert waterfall_lp["equity_multiple"] < carry_lp["equity_multiple"]

        # Both methods should have same total metrics
        assert (
            carry_results["total_metrics"]["total_investment"]
            == waterfall_results["total_metrics"]["total_investment"]
        )
        assert (
            carry_results["total_metrics"]["total_distributions"]
            == waterfall_results["total_metrics"]["total_distributions"]
        )

        # Validate promote structure types - using new polymorphic class names
        assert carry_results["waterfall_details"]["promote_structure"] == "CarryPromote"
        assert (
            waterfall_results["waterfall_details"]["promote_structure"]
            == "IRRWaterfallPromote"
        )

    def test_waterfall_vs_pari_passu_comparison(self):
        """Test comparing waterfall vs pari passu distributions with same partnership."""
        # Create timeline
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=24)

        # Create cash flows: $10M investment, $20M return (100% return)
        cash_flows = pd.Series(
            [
                -10_000_000,  # Investment
                *[0] * 22,  # Hold periods
                20_000_000,  # Return
            ],
            index=timeline.period_index,
        )

        # Test 1: Pari passu distribution
        pari_passu_partnership = PartnershipStructure(
            partners=[
                Partner(name="GP", kind="GP", share=0.20),
                Partner(name="LP", kind="LP", share=0.80),
            ],
            distribution_method="pari_passu",
        )

        calculator_pari = DistributionCalculator(pari_passu_partnership)
        pari_results = calculator_pari.calculate_distributions(cash_flows, timeline)

        # Test 2: Waterfall distribution with carry promote
        waterfall_partnership = PartnershipStructure(
            partners=[
                Partner(name="GP", kind="GP", share=0.20),
                Partner(name="LP", kind="LP", share=0.80),
            ],
            distribution_method="waterfall",
            promote=CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.20),
        )

        calculator_waterfall = DistributionCalculator(waterfall_partnership)
        waterfall_results = calculator_waterfall.calculate_distributions(
            cash_flows, timeline
        )

        # Compare results
        pari_gp = pari_results["partner_distributions"]["GP"]
        pari_lp = pari_results["partner_distributions"]["LP"]
        waterfall_gp = waterfall_results["partner_distributions"]["GP"]
        waterfall_lp = waterfall_results["partner_distributions"]["LP"]

        # In pari passu, GP gets exactly 20% of distributions
        assert pari_gp["total_distributions"] == 4_000_000  # 20% of $20M
        assert pari_lp["total_distributions"] == 16_000_000  # 80% of $20M

        # In waterfall with high returns, GP should get more than 20% due to carry
        assert waterfall_gp["total_distributions"] > 4_000_000
        assert waterfall_lp["total_distributions"] < 16_000_000

        # GP should have higher equity multiple in waterfall
        assert waterfall_gp["equity_multiple"] > pari_gp["equity_multiple"]
        assert waterfall_lp["equity_multiple"] < pari_lp["equity_multiple"]

        # Both methods should have same total metrics
        assert (
            pari_results["total_metrics"]["total_investment"]
            == waterfall_results["total_metrics"]["total_investment"]
        )
        assert (
            pari_results["total_metrics"]["total_distributions"]
            == waterfall_results["total_metrics"]["total_distributions"]
        )

    def test_waterfall_distribution_method_validation(self):
        """Test that waterfall distribution method is properly validated."""
        # Create partnership with waterfall method
        partnership = PartnershipStructure(
            partners=[
                Partner(name="GP", kind="GP", share=0.25),
                Partner(name="LP", kind="LP", share=0.75),
            ],
            distribution_method="waterfall",
            promote=CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.20),
        )

        # Create timeline and cash flows
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=2)

        cash_flows = pd.Series(
            [
                -5_000_000,  # Investment
                6_000_000,  # Return
            ],
            index=timeline.period_index,
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Validate that waterfall method is properly handled - CarryPromote returns 'carry_promote'
        assert results["distribution_method"] == "carry_promote"
        assert "partner_distributions" in results
        assert "total_metrics" in results

        # Validate that calculator correctly identifies waterfall method
        assert calculator.partnership.distribution_method == "waterfall"
        assert calculator.partnership.has_promote is True

        # Validate that waterfall calculation was actually performed
        # (as opposed to falling back to pari passu)
        gp_results = results["partner_distributions"]["GP"]

        # With 20% return and 8% pref hurdle, GP should get some carry
        expected_pari_passu = 6_000_000 * 0.25  # 25% of $6M
        assert gp_results["total_distributions"] != expected_pari_passu
