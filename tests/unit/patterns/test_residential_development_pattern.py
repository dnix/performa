# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for ResidentialDevelopmentPattern.

Tests the residential development pattern class for proper instantiation,
validation, and Deal creation.
"""

from datetime import date

import pytest

from performa.patterns import ResidentialDevelopmentPattern


class TestResidentialDevelopmentPattern:
    """Test ResidentialDevelopmentPattern class functionality."""

    def test_pattern_creation_with_valid_parameters(self):
        """Test creating pattern with valid parameters."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Garden Apartments",
            acquisition_date=date(2024, 1, 1),
            land_cost=3_000_000,
            total_units=120,
            unit_mix=[
                {"unit_type": "1BR", "count": 60, "avg_sf": 650, "target_rent": 1800},
                {"unit_type": "2BR", "count": 60, "avg_sf": 950, "target_rent": 2400},
            ],
            construction_cost_per_unit=180_000,
            hold_period_years=7,
            exit_cap_rate=0.055,
            exit_costs_rate=0.025,
            # Financing parameters
            construction_interest_rate=0.08,
            construction_ltc_ratio=0.75,
            construction_fee_rate=0.02,
            permanent_interest_rate=0.065,
            permanent_ltv_ratio=0.70,
            permanent_loan_term_years=10,
            permanent_amortization_years=30,
            # Partnership parameters
            distribution_method="waterfall",
            gp_share=0.20,
            lp_share=0.80,
            preferred_return=0.08,
            promote_tier_1=0.25,
        )

        assert pattern.project_name == "Garden Apartments"
        assert pattern.total_units == 120
        assert len(pattern.unit_mix) == 2
        assert pattern.avg_unit_sf_computed == 800.0  # (60*650 + 60*950) / 120

    def test_unit_mix_validation(self):
        """Test that unit_mix validation works properly."""
        with pytest.raises(ValueError, match="unit_mix items must include"):
            ResidentialDevelopmentPattern(
                project_name="Invalid Pattern",
                acquisition_date=date(2024, 1, 1),
                land_cost=3_000_000,
                total_units=120,
                unit_mix=[
                    {"unit_type": "1BR", "count": 60}  # Missing required fields
                ],
                construction_cost_per_unit=180_000,
            )

    def test_total_units_validation(self):
        """Test that total_units must match unit_mix counts."""
        with pytest.raises(
            ValueError, match="total_units .* must equal sum of unit_mix counts"
        ):
            ResidentialDevelopmentPattern(
                project_name="Invalid Pattern",
                acquisition_date=date(2024, 1, 1),
                land_cost=3_000_000,
                total_units=100,  # Doesn't match sum of unit counts (120)
                unit_mix=[
                    {
                        "unit_type": "1BR",
                        "count": 60,
                        "avg_sf": 650,
                        "target_rent": 1800,
                    },
                    {
                        "unit_type": "2BR",
                        "count": 60,
                        "avg_sf": 950,
                        "target_rent": 2400,
                    },
                ],
                construction_cost_per_unit=180_000,
            )

    def test_computed_properties(self):
        """Test computed properties work correctly."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Test Property",
            acquisition_date=date(2024, 1, 1),
            land_cost=3_000_000,
            total_units=100,
            unit_mix=[
                {"unit_type": "1BR", "count": 50, "avg_sf": 600, "target_rent": 1500},
                {"unit_type": "2BR", "count": 50, "avg_sf": 900, "target_rent": 2000},
            ],
            construction_cost_per_unit=200_000,
        )

        # Test computed properties
        assert pattern.avg_unit_sf_computed == 750.0  # (50*600 + 50*900) / 100
        assert pattern.total_rentable_area == 75_000.0  # 50*600 + 50*900
        assert (
            pattern.gross_building_area == 75_000.0 / 0.85
        )  # Using default efficiency
        assert (
            pattern.total_construction_cost == 100 * 200_000 * 1.15
        )  # Units * cost/unit * (1 + soft costs rate)

    def test_deal_creation_success(self):
        """Test that create() method produces a valid Deal."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Garden Apartments",
            acquisition_date=date(2024, 1, 1),
            land_cost=3_000_000,
            total_units=120,
            unit_mix=[
                {"unit_type": "1BR", "count": 60, "avg_sf": 650, "target_rent": 1800},
                {"unit_type": "2BR", "count": 60, "avg_sf": 950, "target_rent": 2400},
            ],
            construction_cost_per_unit=180_000,
            hold_period_years=7,
            exit_cap_rate=0.055,
            exit_costs_rate=0.025,
            # Financing parameters
            construction_interest_rate=0.08,
            construction_ltc_ratio=0.75,
            construction_fee_rate=0.02,
            permanent_interest_rate=0.065,
            permanent_ltv_ratio=0.70,
            permanent_loan_term_years=10,
            permanent_amortization_years=30,
            # Partnership parameters
            distribution_method="waterfall",
            gp_share=0.20,
            lp_share=0.80,
            preferred_return=0.08,
            promote_tier_1=0.25,
        )

        # Test Deal creation
        deal = pattern.create()

        assert deal.name == "Garden Apartments Development"
        assert deal.asset is not None
        assert deal.acquisition is not None
        assert deal.financing is not None
        assert deal.equity_partners is not None
        assert deal.exit_valuation is not None

        # Test specific components
        assert deal.asset.property_type.value == "multifamily"
        assert len(deal.financing.facilities) == 2  # Construction + permanent
        assert deal.acquisition.value == 3_000_000  # Land cost

    def test_pari_passu_partnership_creation(self):
        """Test pari passu partnership creation."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Test Property",
            acquisition_date=date(2024, 1, 1),
            land_cost=2_000_000,
            total_units=80,
            unit_mix=[
                {"unit_type": "1BR", "count": 80, "avg_sf": 700, "target_rent": 1600}
            ],
            construction_cost_per_unit=150_000,
            distribution_method="pari_passu",  # Different distribution method
            gp_share=0.10,
            lp_share=0.90,
        )

        deal = pattern.create()

        # Should create simple partnership, not waterfall
        assert deal.equity_partners is not None
        # Note: We can't easily test the internal structure without more access to the partnership object

    def test_timeline_derivation(self):
        """Test that timeline derivation works correctly."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Test Property",
            acquisition_date=date(2024, 1, 1),
            land_cost=1_000_000,
            total_units=50,
            unit_mix=[
                {"unit_type": "1BR", "count": 50, "avg_sf": 600, "target_rent": 1400}
            ],
            construction_cost_per_unit=160_000,
            absorption_pace_units_per_month=5,
            hold_period_years=5,
        )

        timeline = pattern._derive_timeline()

        # Should be reasonable duration (construction + lease-up + stabilization + hold)
        # With hold period of 5 years = 60 months, timeline matches hold period
        assert timeline.duration_months >= 60  # At least the hold period
        # Timeline.start_date is a Period, need to convert to date for comparison
        assert timeline.start_date.to_timestamp().date() == pattern.acquisition_date

    @pytest.mark.parametrize(
        "invalid_unit_mix",
        [
            [],  # Empty unit mix
            [{"unit_type": "1BR"}],  # Missing required fields
            [
                {
                    "unit_type": "1BR",
                    "count": "not_a_number",
                    "avg_sf": 600,
                    "target_rent": 1500,
                }
            ],  # Invalid types
        ],
    )
    def test_invalid_unit_mix_scenarios(self, invalid_unit_mix):
        """Test various invalid unit mix scenarios."""
        with pytest.raises((ValueError, TypeError)):
            ResidentialDevelopmentPattern(
                project_name="Invalid Pattern",
                acquisition_date=date(2024, 1, 1),
                land_cost=1_000_000,
                total_units=len(invalid_unit_mix) * 50 if invalid_unit_mix else 50,
                unit_mix=invalid_unit_mix,
                construction_cost_per_unit=150_000,
            )
