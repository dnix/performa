# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for acquisition patterns.
"""

from datetime import date

import pytest

from performa.core.primitives import Timeline
from performa.deal import analyze
from performa.patterns import create_stabilized_acquisition_deal


class TestStabilizedAcquisitionPattern:
    """Test the stabilized acquisition Pattern."""

    def test_create_stabilized_acquisition_deal_basic_residential(self):
        """Test basic creation of stabilized residential acquisition deal."""
        deal = create_stabilized_acquisition_deal(
            property_name="Maple Ridge Apartments",
            acquisition_date=date(2024, 1, 1),
            purchase_price=10_000_000,
            closing_costs_rate=0.025,
            asset_type="residential",
            property_spec={
                "unit_mix": [
                    {
                        "unit_type_name": "1BR",
                        "unit_count": 50,
                        "current_avg_monthly_rent": 1800,
                        "avg_area_sf": 650,
                        "lease_start_date": date(2023, 1, 1),
                    },
                    {
                        "unit_type_name": "2BR",
                        "unit_count": 30,
                        "current_avg_monthly_rent": 2200,
                        "avg_area_sf": 900,
                        "lease_start_date": date(2023, 1, 1),
                    },
                ]
            },
            financing_terms={
                "ltv_ratio": 0.75,
                "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.06}},
                "loan_term_years": 10,
                "amortization_years": 30,
            },
            partnership_terms={
                "distribution_method": "pari_passu",
                "gp_share": 0.1,
                "lp_share": 0.9,
            },
            hold_period_months=60,
            exit_cap_rate=0.055,
            exit_transaction_costs_rate=0.015,
        )

        # Verify deal structure
        assert deal.name == "Maple Ridge Apartments Stabilized Acquisition"
        assert deal.acquisition.value == 10_000_000
        assert deal.acquisition.acquisition_date == date(2024, 1, 1)
        assert deal.financing is not None
        assert deal.asset.name == "Maple Ridge Apartments"
        assert deal.asset.unit_count == 80  # 50 + 30 units
        assert deal.equity_partners is not None
        assert deal.exit_valuation is not None

    def test_stabilized_acquisition_analysis_integration(self):
        """Test that the stabilized pattern creates a deal that can be analyzed."""
        deal = create_stabilized_acquisition_deal(
            property_name="Analysis Test Property",
            acquisition_date=date(2024, 1, 1),
            purchase_price=5_000_000,
            closing_costs_rate=0.025,
            asset_type="residential",
            property_spec={
                "unit_mix": [
                    {
                        "unit_type_name": "1BR",
                        "unit_count": 40,
                        "current_avg_monthly_rent": 1500,
                        "avg_area_sf": 600,
                        "lease_start_date": date(2023, 1, 1),
                    }
                ]
            },
            financing_terms={
                "ltv_ratio": 0.70,
                "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.055}},
                "loan_term_years": 10,
            },
            partnership_terms={
                "distribution_method": "pari_passu",
                "gp_share": 0.15,
                "lp_share": 0.85,
            },
            hold_period_months=60,
            exit_cap_rate=0.06,
            exit_transaction_costs_rate=0.02,
        )

        # Create analysis timeline
        timeline = Timeline.from_dates("2024-01-01", "2029-12-31")

        # Should be able to analyze without errors
        results = analyze(deal, timeline)

        # Verify we get results
        assert results is not None
        assert results.deal_summary is not None
        assert results.deal_summary.deal_name == deal.name
        assert results.asset_analysis is not None
        assert results.levered_cash_flows is not None

    def test_stabilized_acquisition_office_not_implemented(self):
        """Test that office asset type raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Office property support"):
            create_stabilized_acquisition_deal(
                property_name="Test Office",
                acquisition_date=date(2024, 1, 1),
                purchase_price=5_000_000,
                closing_costs_rate=0.025,
                asset_type="office",  # This should raise NotImplementedError
                property_spec={"net_rentable_area": 50000, "rent_roll": []},
                financing_terms={
                    "ltv_ratio": 0.75,
                    "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.06}},
                    "loan_term_years": 10,
                },
                partnership_terms={
                    "distribution_method": "pari_passu",
                    "gp_share": 0.1,
                    "lp_share": 0.9,
                },
                hold_period_months=60,
                exit_cap_rate=0.055,
                exit_transaction_costs_rate=0.015,
            )
