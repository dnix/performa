# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Test validation logic in deal.analyze() for ledger parameters.

This test suite verifies that deal.analyze() properly handles all combinations
of asset_analysis and ledger parameters, including validation of
conflicting inputs.
"""

from datetime import date

import pytest

from performa.analysis import run as analyze_asset
from performa.asset.office import (
    OfficeExpenses,
    OfficeLosses,
    OfficeProperty,
    OfficeRentRoll,
)
from performa.core.ledger import Ledger
from performa.core.primitives import GlobalSettings, Timeline
from performa.deal import Deal
from performa.deal import analyze as analyze_deal
from performa.deal.acquisition import AcquisitionTerms


class TestDealAnalyzeValidation:
    """Test validation logic for deal.analyze() parameters."""

    @pytest.fixture
    def timeline(self):
        """Standard test timeline."""
        return Timeline.from_dates("2024-01-01", "2024-12-31")

    @pytest.fixture
    def settings(self):
        """Standard test settings."""
        return GlobalSettings()

    @pytest.fixture
    def simple_office_property(self):
        """Create a minimal office property for testing."""
        return OfficeProperty(
            name="Test Office",
            gross_area=100000,
            net_rentable_area=90000,
            rent_roll=OfficeRentRoll(
                leases=[], vacant_suites=[]
            ),  # Empty for simplicity
            expenses=OfficeExpenses(opex_psf=15.0),
            losses=OfficeLosses(),
        )

    @pytest.fixture
    def simple_deal(self, simple_office_property, timeline):
        """Create a simple deal for testing."""
        return Deal(
            name="Test Deal",
            asset=simple_office_property,
            acquisition=AcquisitionTerms(
                name="Test Acquisition",
                timeline=timeline,
                value=10_000_000,
                purchase_price=10_000_000,
                acquisition_date=date(2024, 1, 1),
            ),
        )

    def test_case_1_neither_provided(self, simple_deal, timeline, settings):
        """Test Case 1: Neither asset_analysis nor ledger provided."""
        # Should create new ledger builder internally
        result = analyze_deal(
            deal=simple_deal,
            timeline=timeline,
            settings=settings,
        )

        # Should succeed without error
        assert result is not None
        assert result.deal_summary is not None

    def test_case_2_only_ledger_provided(self, simple_deal, timeline, settings):
        """Test Case 2: Only ledger provided."""
        custom_ledger = Ledger()

        result = analyze_deal(
            deal=simple_deal,
            timeline=timeline,
            settings=settings,
            ledger=custom_ledger,
        )

        # Should succeed and use the custom ledger
        assert result is not None
        # Verify the custom ledger was used (has transactions)
        assert len(custom_ledger.ledger_df()) > 0

    def test_case_3_only_asset_analysis_provided(self, simple_deal, timeline, settings):
        """Test Case 3: Only asset_analysis provided."""
        # First run asset analysis
        asset_result = analyze_asset(
            model=simple_deal.asset,
            timeline=timeline,
            settings=settings,
        )

        # Then use it in deal analysis
        result = analyze_deal(
            deal=simple_deal,
            timeline=timeline,
            settings=settings,
            asset_analysis=asset_result,
        )

        # Should succeed and reuse the asset analysis through the ledger mechanism
        assert result is not None
        # In the new architecture, asset_analysis is wrapped in an adapter
        # but the underlying ledger should be reused from the asset_result
        assert hasattr(result.asset_analysis, "get_ledger_queries")
        # Verify that the analysis succeeded by checking we have valid queries
        assert result.asset_analysis.get_ledger_queries() is not None

    def test_case_4a_both_provided_same_instance(self, simple_deal, timeline, settings):
        """Test Case 4a: Both provided with SAME ledger instance - should succeed."""
        # Run asset analysis first
        asset_result = analyze_asset(
            model=simple_deal.asset,
            timeline=timeline,
            settings=settings,
        )

        # Use the SAME ledger builder instance
        same_ledger = asset_result.ledger

        # This should succeed (explicit validation)
        result = analyze_deal(
            deal=simple_deal,
            timeline=timeline,
            settings=settings,
            asset_analysis=asset_result,
            ledger=same_ledger,  # Same instance
        )

        assert result is not None
        # In the new architecture, asset_analysis is wrapped in an adapter
        # but the underlying ledger should be reused from the asset_result
        assert hasattr(result.asset_analysis, "get_ledger_queries")
        # Verify that the analysis succeeded by checking we have valid queries
        assert result.asset_analysis.get_ledger_queries() is not None

    def test_case_4b_both_provided_different_instances(
        self, simple_deal, timeline, settings
    ):
        """Test Case 4b: Both provided with DIFFERENT ledger instances - should raise ValueError."""
        # Run asset analysis first
        asset_result = analyze_asset(
            model=simple_deal.asset,
            timeline=timeline,
            settings=settings,
        )

        # Create a DIFFERENT ledger builder instance
        different_ledger = Ledger()

        # This should raise ValueError
        with pytest.raises(ValueError, match="Conflicting ledgers provided"):
            analyze_deal(
                deal=simple_deal,
                timeline=timeline,
                settings=settings,
                asset_analysis=asset_result,
                ledger=different_ledger,  # Different instance
            )

    def test_error_message_clarity(self, simple_deal, timeline, settings):
        """Test that error message provides clear guidance."""
        # Run asset analysis first
        asset_result = analyze_asset(
            model=simple_deal.asset,
            timeline=timeline,
            settings=settings,
        )

        # Create different ledger
        different_ledger = Ledger()

        # Verify error message content
        with pytest.raises(ValueError) as exc_info:
            analyze_deal(
                deal=simple_deal,
                timeline=timeline,
                settings=settings,
                asset_analysis=asset_result,
                ledger=different_ledger,
            )

        error_msg = str(exc_info.value)
        assert "Conflicting ledgers" in error_msg
        assert "same instance" in error_msg
        assert "asset_analysis" in error_msg
        assert "ledger" in error_msg
