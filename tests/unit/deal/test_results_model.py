# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for Results Model with Dual-Entry Fee Accounting

This test suite validates the results model implementation that supports
dual-entry fee accounting with detailed waterfall vs. fee breakdown tracking.

Key Features Tested:
- PartnerMetrics with distributions_from_waterfall and distributions_from_fees
- DeveloperFeeDetails with dual-entry tracking structures
- Proper fee vs. waterfall attribution in results
- Backward compatibility with existing fields
- Comprehensive audit trail functionality
"""

from decimal import Decimal
from unittest.mock import Mock

import pandas as pd
import pytest

from performa.core.primitives import GlobalSettings, Timeline
from performa.deal import Deal
from performa.deal.fees import DealFee
from performa.deal.orchestrator import DealCalculator
from performa.deal.partnership import CarryPromote, Partner, PartnershipStructure


class TestResultsModel:
    """Test suite for dual-entry fee accounting results model."""

    @pytest.fixture
    def timeline(self):
        """Create a 36-month timeline for testing."""
        return Timeline.from_dates(start_date="2024-01-01", end_date="2026-12-31")

    @pytest.fixture
    def settings(self):
        """Create global settings for testing."""
        return GlobalSettings()

    @pytest.fixture
    def partners(self):
        """Create test partnership structure."""
        gp = Partner(name="Developer GP", kind="GP", share=0.2)

        lp = Partner(name="Investor LP", kind="LP", share=0.8)

        return PartnershipStructure(
            partners=[gp, lp],
            distribution_method="waterfall",
            promote=CarryPromote(),  # Standard 8% pref, 20% carry
        )

    @pytest.fixture
    def deal_fees(self, partners, timeline):
        """Create test deal fees with specific payees."""

        # Development fee to GP
        dev_fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=Decimal("500000"),
            payee=partners.partners[0],  # GP
            timeline=timeline,
            fee_type="Developer",
        )

        # Asset management fee to GP (spread over construction)
        mgmt_fee = DealFee.create_uniform_fee(
            name="Asset Management Fee",
            value=Decimal("120000"),
            payee=partners.partners[0],  # GP
            timeline=timeline,
            fee_type="Asset Management",
        )

        # Consultant fee to LP (unusual but tests system)
        consultant_fee = DealFee.create_completion_fee(
            name="Consultant Fee",
            value=Decimal("50000"),
            payee=partners.partners[1],  # LP
            timeline=timeline,
            fee_type="Professional Services",
        )

        return [dev_fee, mgmt_fee, consultant_fee]

    @pytest.fixture
    def mock_deal(self, partners, deal_fees):
        """Create mock deal with partnership structure and fees."""
        deal = Mock(spec=Deal)
        deal.name = "Test Deal"
        deal.deal_type = "development"
        deal.equity_partners = partners
        deal.deal_fees = deal_fees
        deal.has_equity_partners = True
        deal.financing = None
        deal.acquisition = None
        deal.disposition = None
        deal.asset = Mock()
        deal.asset.property_type = Mock()
        deal.asset.property_type.value = "office"
        deal.is_development_deal = True
        return deal

    def test_partner_metrics_fields(self, mock_deal, timeline, settings):
        """Test that PartnerMetrics includes all dual-entry fields."""
        # Create positive cash flows for distribution (increased to cover fees)
        positive_cash_flows = pd.Series(
            [0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index
        )
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})

        # Create orchestrator with mock analysis
        calculator = DealCalculator(mock_deal, timeline, settings)

        # Mock the unlevered analysis
        calculator.unlevered_analysis.cash_flows = cash_flows_df

        # Mock the levered cash flows to simulate real analysis
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows

        # Calculate partner distributions
        calculator._calculate_partner_distributions()

        # Verify that we have waterfall distribution results
        assert calculator.partner_distributions is not None
        assert hasattr(calculator.partner_distributions, "waterfall_details")

        # Get partner results
        partner_results = (
            calculator.partner_distributions.waterfall_details.partner_results
        )
        assert len(partner_results) == 2  # GP and LP

        # Test dual-entry fields in GP partner metrics
        gp_result = partner_results["Developer GP"]

        # Test new dual-entry fields
        assert hasattr(gp_result, "distributions_from_waterfall")
        assert hasattr(gp_result, "distributions_from_fees")
        assert hasattr(gp_result, "fee_details")
        assert hasattr(gp_result, "fee_cash_flows")

        # Test that distributions_from_fees > 0 for GP (fee recipient)
        assert gp_result.distributions_from_fees > 0

        # Test that fee_details is a dict with fee breakdown
        assert isinstance(gp_result.fee_details, dict)
        assert len(gp_result.fee_details) > 0

        # Test that fee_cash_flows is a pandas Series
        assert isinstance(gp_result.fee_cash_flows, pd.Series)

        # Test LP partner metrics
        lp_result = partner_results["Investor LP"]

        # LP should have consultant fee
        assert lp_result.distributions_from_fees > 0  # Consultant fee
        assert "Consultant Fee" in lp_result.fee_details

        # Test backward compatibility field
        assert hasattr(gp_result, "developer_fee")
        assert gp_result.developer_fee == gp_result.distributions_from_fees

    def test_fee_accounting_details_fields(self, mock_deal, timeline, settings):
        """Test that DeveloperFeeDetails includes all dual-entry tracking fields."""
        # Create positive cash flows (increased to cover fees)
        positive_cash_flows = pd.Series(
            [0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index
        )
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})

        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows

        # Calculate partner distributions
        calculator._calculate_partner_distributions()

        # Get fee accounting details
        fee_details = calculator.partner_distributions.fee_accounting_details

        # Test dual-entry tracking fields
        assert hasattr(fee_details, "fee_details_by_partner")
        assert hasattr(fee_details, "fee_cash_flows_by_partner")
        assert hasattr(fee_details, "total_fees_by_type")
        assert hasattr(fee_details, "fee_timing_summary")

        # Test fee_details_by_partner structure
        assert isinstance(fee_details.fee_details_by_partner, dict)
        assert len(fee_details.fee_details_by_partner) > 0

        # Test fee_cash_flows_by_partner structure
        assert isinstance(fee_details.fee_cash_flows_by_partner, dict)
        for partner_name, cash_flows in fee_details.fee_cash_flows_by_partner.items():
            assert isinstance(cash_flows, pd.Series)

        # Test total_fees_by_type structure
        assert isinstance(fee_details.total_fees_by_type, dict)
        assert "Developer" in fee_details.total_fees_by_type
        assert "Asset Management" in fee_details.total_fees_by_type

        # Test fee_timing_summary structure
        assert isinstance(fee_details.fee_timing_summary, dict)

    def test_fee_vs_waterfall_attribution(self, mock_deal, timeline, settings):
        """Test that fee vs. waterfall attribution is accurate."""
        # Create substantial positive cash flows to ensure waterfall distributions
        positive_cash_flows = pd.Series(
            [0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index
        )
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})

        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows

        # Calculate partner distributions
        calculator._calculate_partner_distributions()

        # Get partner results
        partner_results = (
            calculator.partner_distributions.waterfall_details.partner_results
        )
        gp_result = partner_results["Developer GP"]

        # GP should have both waterfall and fee distributions
        assert gp_result.distributions_from_waterfall > 0
        assert gp_result.distributions_from_fees > 0

        # Total should equal sum of both sources
        expected_total = (
            gp_result.distributions_from_waterfall + gp_result.distributions_from_fees
        )
        assert (
            abs(gp_result.total_distributions - expected_total) < 1.0
        )  # Allow for small rounding

        # Test LP distributions
        lp_result = partner_results["Investor LP"]

        # LP should have waterfall distributions and consultant fee
        assert lp_result.distributions_from_waterfall > 0
        assert lp_result.distributions_from_fees > 0  # Consultant fee

        # LP should have less fee income than GP (only consultant fee)
        assert lp_result.distributions_from_fees < gp_result.distributions_from_fees

        # Test deal-level totals
        deal_total = calculator.partner_distributions.total_distributions
        partner_total = sum(p.total_distributions for p in partner_results.values())

        assert abs(deal_total - partner_total) < 1.0  # Should match

    def test_backward_compatibility(self, mock_deal, timeline, settings):
        """Test that deprecated fields still work for backward compatibility."""
        # Create positive cash flows (increased to cover fees)
        positive_cash_flows = pd.Series(
            [0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index
        )
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})

        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows

        # Calculate partner distributions
        calculator._calculate_partner_distributions()

        # Get partner results
        partner_results = (
            calculator.partner_distributions.waterfall_details.partner_results
        )
        gp_result = partner_results["Developer GP"]

        # Test that deprecated developer_fee field exists and matches new field
        assert hasattr(gp_result, "developer_fee")
        assert gp_result.developer_fee == gp_result.distributions_from_fees

        # Test that existing total_distributions field still works
        assert hasattr(gp_result, "total_distributions")
        assert gp_result.total_distributions > 0

    def test_comprehensive_audit_trail(self, mock_deal, timeline, settings):
        """Test comprehensive audit trail functionality."""
        # Create positive cash flows (increased to cover fees)
        positive_cash_flows = pd.Series(
            [0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index
        )
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})

        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows

        # Calculate partner distributions
        calculator._calculate_partner_distributions()

        # Get results
        partner_results = (
            calculator.partner_distributions.waterfall_details.partner_results
        )
        fee_details = calculator.partner_distributions.fee_accounting_details

        # Test partner-level audit trail
        gp_result = partner_results["Developer GP"]

        # GP should have detailed fee breakdown
        assert len(gp_result.fee_details) >= 2  # Dev fee + Mgmt fee
        assert "Development Fee" in gp_result.fee_details
        assert "Asset Management Fee" in gp_result.fee_details

        # Test deal-level audit trail
        assert "Developer GP" in fee_details.fee_details_by_partner
        assert "Investor LP" in fee_details.fee_details_by_partner

        # Test fee type aggregation
        assert "Developer" in fee_details.total_fees_by_type
        assert "Asset Management" in fee_details.total_fees_by_type
        assert "Professional Services" in fee_details.total_fees_by_type

        # Test cash flow tracking
        assert "Developer GP" in fee_details.fee_cash_flows_by_partner
        assert isinstance(
            fee_details.fee_cash_flows_by_partner["Developer GP"], pd.Series
        )

    def test_zero_fees_handling(self, partners, timeline, settings):
        """Test that results work correctly with zero fees."""
        # Create deal with no fees
        deal = Mock(spec=Deal)
        deal.name = "No Fees Deal"
        deal.deal_type = "acquisition"
        deal.equity_partners = partners
        deal.deal_fees = []  # No fees
        deal.has_equity_partners = True
        deal.financing = None
        deal.acquisition = None
        deal.disposition = None
        deal.asset = Mock()
        deal.asset.property_type = Mock()
        deal.asset.property_type.value = "office"
        deal.is_development_deal = False

        # Create positive cash flows (increased to cover fees)
        positive_cash_flows = pd.Series(
            [0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index
        )
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})

        # Create orchestrator
        calculator = DealCalculator(deal, timeline, settings)
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows

        # Calculate partner distributions
        calculator._calculate_partner_distributions()

        # Get partner results
        partner_results = (
            calculator.partner_distributions.waterfall_details.partner_results
        )

        # All distributions should be from waterfall only
        for partner_name, partner_result in partner_results.items():
            assert partner_result.distributions_from_fees == 0.0
            assert partner_result.distributions_from_waterfall > 0
            assert (
                partner_result.total_distributions
                == partner_result.distributions_from_waterfall
            )
            assert len(partner_result.fee_details) == 0

    def test_results_model_validation(self, mock_deal, timeline, settings):
        """Test that results models pass Pydantic validation."""
        # Create positive cash flows (increased to cover fees)
        positive_cash_flows = pd.Series(
            [0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index
        )
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})

        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows

        # Calculate partner distributions
        calculator._calculate_partner_distributions()

        # Test that all results validate
        assert calculator.partner_distributions is not None

        # Test PartnerMetrics validation
        partner_results = (
            calculator.partner_distributions.waterfall_details.partner_results
        )
        for partner_name, partner_result in partner_results.items():
            # Should not raise validation errors
            assert partner_result.total_distributions >= 0
            assert partner_result.distributions_from_waterfall >= 0
            assert partner_result.distributions_from_fees >= 0
            assert isinstance(partner_result.fee_details, dict)
            assert isinstance(partner_result.fee_cash_flows, pd.Series)

        # Test FeeAccountingDetails validation
        fee_details = calculator.partner_distributions.fee_accounting_details
        assert isinstance(fee_details.fee_details_by_partner, dict)
        assert isinstance(fee_details.fee_cash_flows_by_partner, dict)
        assert isinstance(fee_details.total_fees_by_type, dict)
        assert isinstance(fee_details.fee_timing_summary, dict)

    def test_complex_fee_structure(self, partners, timeline, settings):
        """Test results with complex fee structures."""
        # Create complex fee structure

        fees = [
            # Multiple fees to same partner
            DealFee.create_upfront_fee(
                name="Acquisition Fee",
                value=100000,
                payee=partners.partners[0],  # GP
                timeline=timeline,
                fee_type="Acquisition",
            ),
            DealFee.create_uniform_fee(
                name="Asset Management Fee",
                value=60000,
                payee=partners.partners[0],  # GP
                timeline=timeline,
                fee_type="Asset Management",
            ),
            DealFee.create_completion_fee(
                name="Disposition Fee",
                value=75000,
                payee=partners.partners[0],  # GP
                timeline=timeline,
                fee_type="Disposition",
            ),
            # Fee to different partner
            DealFee.create_upfront_fee(
                name="Legal Fee",
                value=25000,
                payee=partners.partners[1],  # LP
                timeline=timeline,
                fee_type="Legal",
            ),
        ]

        # Create deal with complex fee structure
        deal = Mock(spec=Deal)
        deal.name = "Complex Fees Deal"
        deal.deal_type = "acquisition"
        deal.equity_partners = partners
        deal.deal_fees = fees
        deal.has_equity_partners = True
        deal.financing = None
        deal.acquisition = None
        deal.disposition = None
        deal.asset = Mock()
        deal.asset.property_type = Mock()
        deal.asset.property_type.value = "office"
        deal.is_development_deal = False

        # Create positive cash flows (increased to cover fees)
        positive_cash_flows = pd.Series(
            [0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index
        )
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})

        # Create orchestrator
        calculator = DealCalculator(deal, timeline, settings)
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows

        # Calculate partner distributions
        calculator._calculate_partner_distributions()

        # Get results
        partner_results = (
            calculator.partner_distributions.waterfall_details.partner_results
        )
        fee_details = calculator.partner_distributions.fee_accounting_details

        # Test GP gets multiple fees
        gp_result = partner_results["Developer GP"]
        assert (
            len(gp_result.fee_details) == 3
        )  # Acquisition, Asset Management, Disposition
        assert "Acquisition Fee" in gp_result.fee_details
        assert "Asset Management Fee" in gp_result.fee_details
        assert "Disposition Fee" in gp_result.fee_details

        # Test LP gets single fee
        lp_result = partner_results["Investor LP"]
        assert len(lp_result.fee_details) == 1  # Legal
        assert "Legal Fee" in lp_result.fee_details

        # Test fee type aggregation
        assert "Acquisition" in fee_details.total_fees_by_type
        assert "Asset Management" in fee_details.total_fees_by_type
        assert "Disposition" in fee_details.total_fees_by_type
        assert "Legal" in fee_details.total_fees_by_type

        # Test totals
        expected_gp_fees = (
            100000 + 60000 + 75000
        )  # Acquisition + Asset Management + Disposition
        expected_lp_fees = 25000  # Legal

        assert gp_result.distributions_from_fees == expected_gp_fees
        assert lp_result.distributions_from_fees == expected_lp_fees
