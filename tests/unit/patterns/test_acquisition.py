# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for acquisition patterns.
"""

from datetime import date

from performa.core.primitives import Timeline
from performa.deal import analyze
from performa.patterns import (
    OfficeStabilizedAcquisitionPattern,
    StabilizedAcquisitionPattern,
)


class TestStabilizedAcquisitionPattern:
    """Test the stabilized acquisition Pattern."""

    def test_create_stabilized_acquisition_deal_basic_residential(self):
        """Test basic creation of stabilized residential acquisition deal."""
        # Use pattern class instead of legacy function
        pattern = StabilizedAcquisitionPattern(
            property_name="Maple Ridge Apartments",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=10_000_000,
            closing_costs_rate=0.025,
            total_units=80,
            avg_unit_sf=775,  # (650*50 + 900*30) / 80
            current_avg_rent=1900,  # Approximate average
            initial_vacancy_rate=0.05,
            annual_rent_growth=0.03,
            annual_expense_growth=0.025,
            operating_expense_ratio=0.35,
            ltv_ratio=0.75,
            interest_rate=0.06,
            loan_term_years=10,
            amortization_years=30,
            distribution_method="pari_passu",
            gp_share=0.1,
            lp_share=0.9,
            hold_period_years=5,
            exit_cap_rate=0.055,
            exit_costs_rate=0.015,
        )

        deal = pattern.create()

        # Verify deal structure
        assert "Maple Ridge Apartments" in deal.name  # Pattern adds suffix
        assert deal.acquisition.value == 10_000_000
        assert deal.acquisition.acquisition_date == date(2024, 1, 1)
        assert deal.financing is not None
        assert deal.asset.name == "Maple Ridge Apartments"
        # Check key properties exist
        assert deal.equity_partners is not None
        assert deal.exit_valuation is not None

    def test_stabilized_acquisition_analysis_integration(self):
        """Test that the stabilized pattern creates a deal that can be analyzed."""
        pattern = StabilizedAcquisitionPattern(
            property_name="Analysis Test Property",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=5_000_000,
            closing_costs_rate=0.025,
            total_units=40,
            avg_unit_sf=600,
            current_avg_rent=1500,
            initial_vacancy_rate=0.05,
            annual_rent_growth=0.03,
            annual_expense_growth=0.025,
            operating_expense_ratio=0.35,
            ltv_ratio=0.70,
            interest_rate=0.055,
            loan_term_years=10,
            amortization_years=30,
            distribution_method="pari_passu",
            gp_share=0.15,
            lp_share=0.85,
            hold_period_years=5,
            exit_cap_rate=0.06,
            exit_costs_rate=0.02,
        )

        deal = pattern.create()

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

    def test_stabilized_acquisition_office_works(self):
        """Test that office asset type now works (no longer raises NotImplementedError)."""
        pattern = OfficeStabilizedAcquisitionPattern(
            property_name="Test Office",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=5_000_000,
            closing_costs_rate=0.025,
            net_rentable_area=50_000,
            current_occupancy=0.85,
            current_rent_psf=30.0,  # Add required current rent
            market_rent_psf=35.0,
            operating_expense_psf=12.0,
            hold_period_years=5,
            exit_cap_rate=0.055,
            ltv_ratio=0.75,
            interest_rate=0.06,
            loan_term_years=10,
            amortization_years=30,
            distribution_method="pari_passu",
            gp_share=0.1,
            lp_share=0.9,
        )

        deal = pattern.create()

        # Verify the deal was created successfully
        assert "Test Office" in deal.name  # Pattern adds suffix
        assert deal.asset is not None
        assert deal.financing is not None
        # Note: Partnership may be None depending on implementation
