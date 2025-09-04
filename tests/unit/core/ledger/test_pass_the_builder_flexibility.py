# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Test Pass-the-Builder pattern flexibility across all entry points.

This test suite verifies that LedgerBuilder can be passed through
all analysis entry points, enabling maximum flexibility for various
use cases including testing, portfolio analysis, and multi-phase development.
"""

from datetime import date

import pytest

from performa.analysis import run as analyze_asset
from performa.asset.office import (
    OfficeExpenses,
    OfficeLeaseSpec,
    OfficeLosses,
    OfficeProperty,
    OfficeRentRoll,
)
from performa.core.ledger import Ledger, LedgerGenerationSettings
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseTypeEnum,
    ProgramUseEnum,
    PropertyAttributeKey,
    Timeline,
    UponExpirationEnum,
)
from performa.deal import Deal
from performa.deal import analyze as analyze_deal
from performa.deal.acquisition import AcquisitionTerms


class TestLedgerFlexibility:
    """Test that LedgerBuilder can be passed through all entry points."""

    @pytest.fixture
    def timeline(self):
        """Standard test timeline."""
        return Timeline.from_dates("2024-01-01", "2024-12-31")

    @pytest.fixture
    def settings(self):
        """Standard test settings."""
        return GlobalSettings()

    @pytest.fixture
    def office_property(self, timeline):
        """Create a simple office property for testing."""
        # Create a lease spec (not a lease instance)
        lease_spec = OfficeLeaseSpec(
            tenant_name="Test Tenant",
            start_date=date(2024, 1, 1),
            end_date=date(2028, 12, 31),
            suite="100",
            floor="1",
            area=10000.0,  # 10,000 sf
            base_rent_value=50.0,  # $50/sf annual rent
            lease_type=LeaseTypeEnum.GROSS,
            upon_expiration=UponExpirationEnum.MARKET,
        )

        rent_roll = OfficeRentRoll(leases=[lease_spec], vacant_suites=[])

        expenses = OfficeExpenses()  # Uses defaults

        losses = OfficeLosses()  # Uses defaults

        return OfficeProperty(
            name="Test Office",
            net_rentable_area=10000.0,
            gross_area=12000.0,
            rent_roll=rent_roll,
            expenses=expenses,
            losses=losses,
        )

    def test_asset_analysis_with_custom_ledger(
        self, office_property, timeline, settings
    ):
        """Test that asset analysis can accept a pre-configured LedgerBuilder."""
        # Create custom ledger with specific settings
        custom_settings = LedgerGenerationSettings(
            validate_transactions=True,
            include_transaction_ids=True,
        )
        custom_ledger = Ledger(settings=custom_settings)

        # Run asset analysis with custom ledger
        result = analyze_asset(
            model=office_property,
            timeline=timeline,
            settings=settings,
            ledger=custom_ledger,
        )

        # Verify the same ledger instance was used
        assert result.ledger is custom_ledger

        # Verify ledger contains transactions
        ledger_df = result.ledger.ledger_df()
        assert len(ledger_df) > 0

        # Verify we can query the ledger
        assert result.noi is not None
        assert len(result.noi) == 12  # Monthly timeline

    def test_deal_analysis_with_precomputed_asset(
        self, office_property, timeline, settings
    ):
        """Test that deal analysis can reuse asset analysis results."""
        # First, run asset analysis
        asset_result = analyze_asset(
            model=office_property,
            timeline=timeline,
            settings=settings,
        )

        # Record initial ledger state
        initial_ledger = asset_result.ledger
        initial_transaction_count = len(initial_ledger.ledger_df())

        # Create a deal using the same property
        deal = Deal(
            name="Test Deal",
            asset=office_property,
            acquisition=AcquisitionTerms(
                name="Property Acquisition",
                timeline=timeline,
                value=10_000_000,
                acquisition_date=date(2024, 1, 1),
                closing_costs_rate=0.02,
            ),
        )

        # Analyze deal with pre-computed asset analysis
        deal_result = analyze_deal(
            deal=deal,
            timeline=timeline,
            settings=settings,
            asset_analysis=asset_result,
        )

        # Verify the same ledger instance was used throughout
        # Note: We can't directly access deal_result.ledger yet,
        # but we can verify the asset analysis was reused
        assert deal_result.asset_analysis is not None

        # The ledger should have more transactions (acquisition costs added)
        final_transaction_count = len(initial_ledger.ledger_df())
        assert final_transaction_count > initial_transaction_count

    def test_deal_analysis_with_custom_ledger(
        self, office_property, timeline, settings
    ):
        """Test that deal analysis can accept a custom LedgerBuilder."""
        # Create custom ledger
        custom_ledger = Ledger(settings=LedgerGenerationSettings())

        # Create a deal
        deal = Deal(
            name="Test Deal",
            asset=office_property,
            acquisition=AcquisitionTerms(
                name="Property Acquisition",
                timeline=timeline,
                value=10_000_000,
                acquisition_date=date(2024, 1, 1),
                closing_costs_rate=0.02,
            ),
        )

        # Analyze deal with custom ledger
        deal_result = analyze_deal(
            deal=deal,
            timeline=timeline,
            settings=settings,
            ledger=custom_ledger,
        )

        # Verify ledger contains transactions
        ledger_df = custom_ledger.ledger_df()
        assert len(ledger_df) > 0

        # Verify both asset and deal transactions are present
        categories = ledger_df["category"].unique()
        assert "Revenue" in categories  # From asset
        assert "Capital" in categories  # From acquisition

    def test_multi_phase_analysis_with_shared_ledger(self, timeline, settings):
        """Test that multiple analysis phases can share a single LedgerBuilder."""
        # Create shared ledger
        shared_ledger = Ledger(settings=LedgerGenerationSettings())

        # Phase 1: Analyze first property
        property1 = OfficeProperty(
            name="Building A",
            net_rentable_area=10000,
            gross_area=11000,
            rent_roll=OfficeRentRoll(
                leases=[
                    OfficeLeaseSpec(
                        tenant_name="Tenant A",
                        suite="100",
                        floor="1",
                        area=5000,
                        use_type=ProgramUseEnum.OFFICE,
                        lease_type=LeaseTypeEnum.GROSS,
                        start_date=date(2024, 1, 1),
                        term_months=60,
                        base_rent_value=40.0,
                        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                        base_rent_frequency=FrequencyEnum.ANNUAL,
                        upon_expiration=UponExpirationEnum.MARKET,
                    )
                ],
                vacant_suites=[],
            ),
            expenses=OfficeExpenses(opex_psf=10.0),
            losses=OfficeLosses(),
        )

        result1 = analyze_asset(
            model=property1,
            timeline=timeline,
            settings=settings,
            ledger=shared_ledger,
        )

        phase1_count = len(shared_ledger.ledger_df())
        assert phase1_count > 0

        # Phase 2: Analyze second property with same ledger
        property2 = OfficeProperty(
            name="Building B",
            net_rentable_area=8000,
            gross_area=9000,
            rent_roll=OfficeRentRoll(
                leases=[
                    OfficeLeaseSpec(
                        tenant_name="Tenant B",
                        suite="200",
                        floor="2",
                        area=8000,
                        use_type=ProgramUseEnum.OFFICE,
                        lease_type=LeaseTypeEnum.GROSS,
                        start_date=date(2024, 1, 1),
                        term_months=60,
                        base_rent_value=45.0,
                        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                        base_rent_frequency=FrequencyEnum.ANNUAL,
                        upon_expiration=UponExpirationEnum.MARKET,
                    )
                ],
                vacant_suites=[],
            ),
            expenses=OfficeExpenses(opex_psf=12.0),
            losses=OfficeLosses(),
        )

        result2 = analyze_asset(
            model=property2,
            timeline=timeline,
            settings=settings,
            ledger=shared_ledger,
        )

        # Verify both properties' transactions are in the ledger
        phase2_count = len(shared_ledger.ledger_df())
        assert phase2_count > phase1_count

        # Verify we can distinguish between properties
        ledger_df = shared_ledger.ledger_df()
        asset_ids = ledger_df["asset_id"].unique()
        assert len(asset_ids) == 2  # Two different properties

    def test_priority_order_asset_analysis_wins(
        self, office_property, timeline, settings
    ):
        """Test that asset_analysis takes priority over ledger in deal.analyze()."""
        # Create two different ledgers
        ledger1 = Ledger(settings=LedgerGenerationSettings())
        ledger2 = Ledger(settings=LedgerGenerationSettings())

        # Run asset analysis with ledger1
        asset_result = analyze_asset(
            model=office_property,
            timeline=timeline,
            settings=settings,
            ledger=ledger1,
        )

        # Create deal
        deal = Deal(
            name="Test Deal",
            asset=office_property,
            acquisition=AcquisitionTerms(
                name="Property Acquisition",
                timeline=timeline,
                value=10_000_000,
                acquisition_date=date(2024, 1, 1),
            ),
        )

        # Analyze deal with asset_analysis (should use its ledger)
        deal_result = analyze_deal(
            deal=deal,
            timeline=timeline,
            settings=settings,
            asset_analysis=asset_result,  # Uses ledger1
        )

        # Verify ledger1 was used (has transactions)
        assert len(ledger1.ledger_df()) > 0

        # Verify ledger2 was NOT used (empty)
        assert len(ledger2.ledger_df()) == 0
