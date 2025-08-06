# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Test third-party fee processing in the orchestrator.

This test validates that the orchestrator correctly processes third-party fees
with single-entry accounting (project cost only) vs partner fees with dual-entry
accounting (project cost + partner income).
"""

from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from performa.core.primitives.settings import GlobalSettings
from performa.core.primitives.timeline import Timeline
from performa.deal.entities import Partner, ThirdParty
from performa.deal.fees import DealFee
from performa.deal.orchestrator import DealCalculator


class TestThirdPartyOrchestration:
    """Test orchestrator processing of third-party fees."""

    @pytest.fixture
    def timeline(self):
        """Create a test timeline."""
        return Timeline.from_dates(
            start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)
        )

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return GlobalSettings()

    @pytest.fixture
    def developer_partner(self):
        """Create a developer partner."""
        return Partner(name="Developer", kind="GP", share=0.25)

    @pytest.fixture
    def investor_partner(self):
        """Create an investor partner."""
        return Partner(name="Investor", kind="LP", share=0.75)

    @pytest.fixture
    def architect_third_party(self):
        """Create an architect third party."""
        return ThirdParty(name="Smith Architecture", description="Design services")

    @pytest.fixture
    def broker_third_party(self):
        """Create a broker third party."""
        return ThirdParty(name="CBRE", description="Leasing services")

    def test_mixed_fee_processing(
        self,
        timeline,
        settings,
        developer_partner,
        investor_partner,
        architect_third_party,
        broker_third_party,
    ):
        """Test that orchestrator handles both partner and third-party fees correctly."""

        # Create fees with mixed payee types
        partner_fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=500_000,
            payee=developer_partner,
            timeline=timeline,
            fee_type="Developer",
        )

        architect_fee = DealFee.create_completion_fee(
            name="Architectural Services",
            value=150_000,
            payee=architect_third_party,
            timeline=timeline,
            fee_type="Professional Services",
        )

        broker_fee = DealFee.create_uniform_fee(
            name="Leasing Commission",
            value=120_000,  # $10k per month
            payee=broker_third_party,
            timeline=timeline,
            fee_type="Brokerage",
        )

        # Create mock partnership with only the actual partners
        partnership = Mock()
        partnership.partners = [developer_partner, investor_partner]

        # Create mock deal
        deal = Mock()
        deal.deal_fees = [partner_fee, architect_fee, broker_fee]
        deal.has_equity_partners = True
        deal.equity_partners = partnership

        # Create calculator
        calculator = DealCalculator(deal=deal, timeline=timeline, settings=settings)

        # Create test cash flows
        cash_flows = pd.Series(100_000.0, index=timeline.period_index)

        # Process fees
        fee_details = calculator._calculate_fee_distributions(cash_flows)

        # Validate total fees
        expected_total_fees = 500_000 + 150_000 + 120_000  # 770k total
        total_project_cost = (
            fee_details["total_partner_fees"] + fee_details["total_third_party_fees"]
        )
        assert total_project_cost == expected_total_fees

        # Validate partner fees (dual-entry)
        assert fee_details["total_partner_fees"] == 500_000  # Only partner fee
        assert fee_details["partner_fees_by_partner"]["Developer"] == 500_000
        assert fee_details["partner_fees_by_partner"]["Investor"] == 0.0

        # Validate third-party fees (single-entry)
        assert fee_details["total_third_party_fees"] == 270_000  # Architect + Broker
        assert fee_details["third_party_fees"]["Smith Architecture"] == 150_000
        assert fee_details["third_party_fees"]["CBRE"] == 120_000

        # Validate fee details tracking
        assert len(fee_details["fee_details_by_partner"]["Developer"]) == 1
        assert len(fee_details["third_party_fee_details"]["Smith Architecture"]) == 1
        assert len(fee_details["third_party_fee_details"]["CBRE"]) == 1

        # Validate that all fees reduce cash flow equally
        original_cf_sum = cash_flows.sum()
        remaining_cf_sum = fee_details["remaining_cash_flows_after_fee"].sum()
        total_fee_reduction = original_cf_sum - remaining_cf_sum

        # All fees should reduce cash flow (project cost impact)
        assert (
            total_fee_reduction <= expected_total_fees
        )  # May be limited by available cash flow

    def test_third_party_only_fees(
        self, timeline, settings, developer_partner, architect_third_party
    ):
        """Test processing when all fees are third-party (no partner fees)."""

        # Create only third-party fees
        architect_fee = DealFee.create_upfront_fee(
            name="Architectural Services",
            value=200_000,
            payee=architect_third_party,
            timeline=timeline,
        )

        # Create partnership (but no fees to partners)
        partnership = Mock()
        partnership.partners = [developer_partner]

        deal = Mock()
        deal.deal_fees = [architect_fee]
        deal.has_equity_partners = True
        deal.equity_partners = partnership

        calculator = DealCalculator(deal=deal, timeline=timeline, settings=settings)
        cash_flows = pd.Series(50_000.0, index=timeline.period_index)

        fee_details = calculator._calculate_fee_distributions(cash_flows)

        # No partner fees
        assert fee_details["total_partner_fees"] == 0.0
        assert fee_details["partner_fees_by_partner"]["Developer"] == 0.0

        # Only third-party fees
        assert fee_details["total_third_party_fees"] == 200_000
        assert fee_details["third_party_fees"]["Smith Architecture"] == 200_000

    def test_partner_only_fees(
        self, timeline, settings, developer_partner, architect_third_party
    ):
        """Test processing when all fees are partner fees (no third-party fees)."""

        # Create only partner fees
        dev_fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=300_000,
            payee=developer_partner,
            timeline=timeline,
        )

        partnership = Mock()
        partnership.partners = [developer_partner]

        deal = Mock()
        deal.deal_fees = [dev_fee]
        deal.has_equity_partners = True
        deal.equity_partners = partnership

        calculator = DealCalculator(deal=deal, timeline=timeline, settings=settings)
        cash_flows = pd.Series(50_000.0, index=timeline.period_index)

        fee_details = calculator._calculate_fee_distributions(cash_flows)

        # Only partner fees
        assert fee_details["total_partner_fees"] == 300_000
        assert fee_details["partner_fees_by_partner"]["Developer"] == 300_000

        # No third-party fees
        assert fee_details["total_third_party_fees"] == 0.0
        assert len(fee_details["third_party_fees"]) == 0
