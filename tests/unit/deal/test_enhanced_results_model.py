"""
Tests for Enhanced Results Model (Phase 3) 

This test suite validates the enhanced results model implementation that supports
dual-entry fee accounting with detailed waterfall vs. fee breakdown tracking.

Key Features Tested:
- Enhanced PartnerMetrics with distributions_from_waterfall and distributions_from_fees
- Enhanced DeveloperFeeDetails with dual-entry tracking structures
- Proper fee vs. waterfall attribution in results
- Backward compatibility with existing fields
- Comprehensive audit trail functionality
"""

from decimal import Decimal
from unittest.mock import Mock

import pandas as pd
import pytest

from performa.core.primitives import GlobalSettings, Timeline
from performa.deal.deal import Deal
from performa.deal.entities import Partner
from performa.deal.fees import DealFee
from performa.deal.orchestrator import DealCalculator
from performa.deal.partnership import PartnershipStructure


class TestEnhancedResultsModel:
    """Test suite for enhanced results model implementation."""

    @pytest.fixture
    def timeline(self):
        """Create a 36-month timeline for testing."""
        return Timeline.from_dates(
            start_date="2024-01-01",
            end_date="2026-12-31"
        )

    @pytest.fixture
    def settings(self):
        """Create global settings for testing."""
        return GlobalSettings()

    @pytest.fixture
    def partners(self):
        """Create test partners for dual-entry fee accounting."""
        gp = Partner(
            name="Developer GP",
            kind="GP",
            share=0.20
        )
        
        lp = Partner(
            name="Investor LP",
            kind="LP",
            share=0.80
        )
        
        from performa.deal.partnership import CarryPromote
        
        return PartnershipStructure(
            partners=[gp, lp],
            distribution_method="waterfall",
            promote=CarryPromote()  # Standard 8% pref, 20% carry
        )

    @pytest.fixture
    def deal_fees(self, partners, timeline):
        """Create test deal fees with specific payees."""
        from performa.core.primitives import FirstOnlyDrawSchedule, UniformDrawSchedule
        
        # Development fee to GP
        dev_fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=Decimal("500000"),
            payee=partners.partners[0],  # GP
            timeline=timeline,
            fee_type="Developer"
        )
        
        # Asset management fee to GP (spread over construction)
        mgmt_fee = DealFee.create_uniform_fee(
            name="Asset Management Fee",
            value=Decimal("120000"),
            payee=partners.partners[0],  # GP
            timeline=timeline,
            fee_type="Asset Management"
        )
        
        # Consultant fee to LP (unusual but tests system)
        consultant_fee = DealFee.create_completion_fee(
            name="Consultant Fee",
            value=Decimal("50000"),
            payee=partners.partners[1],  # LP
            timeline=timeline,
            fee_type="Professional Services"
        )
        
        return [dev_fee, mgmt_fee, consultant_fee]

    @pytest.fixture
    def mock_deal(self, partners, deal_fees):
        """Create a mock deal with fees and partners."""
        deal = Mock(spec=Deal)
        deal.name = "Test Enhanced Results Deal"
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

    def test_enhanced_partner_metrics_fields(self, mock_deal, timeline, settings):
        """Test that PartnerMetrics includes all enhanced fields."""
        # Create positive cash flows for distribution (increased to cover fees)
        positive_cash_flows = pd.Series([0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index)
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
        assert hasattr(calculator.partner_distributions, 'waterfall_details')
        
        # Get partner results
        partner_results = calculator.partner_distributions.waterfall_details.partner_results
        assert len(partner_results) == 2  # GP and LP
        
        # Test enhanced fields in GP partner metrics
        gp_result = partner_results["Developer GP"]
        
        # Test new dual-entry fields
        assert hasattr(gp_result, 'distributions_from_waterfall')
        assert hasattr(gp_result, 'distributions_from_fees')
        assert hasattr(gp_result, 'fee_details')
        assert hasattr(gp_result, 'fee_cash_flows')
        
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
        assert hasattr(gp_result, 'developer_fee')
        assert gp_result.developer_fee == gp_result.distributions_from_fees

    def test_enhanced_fee_accounting_details_fields(self, mock_deal, timeline, settings):
        """Test that DeveloperFeeDetails includes all enhanced tracking fields."""
        # Create positive cash flows (increased to cover fees)
        positive_cash_flows = pd.Series([0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index)
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})
        
        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows
        
        # Calculate partner distributions
        calculator._calculate_partner_distributions()
        
        # Get fee accounting details
        fee_details = calculator.partner_distributions.fee_accounting_details
        
        # Test enhanced dual-entry tracking fields
        assert hasattr(fee_details, 'fee_details_by_partner')
        assert hasattr(fee_details, 'fee_cash_flows_by_partner')
        assert hasattr(fee_details, 'total_fees_by_type')
        assert hasattr(fee_details, 'fee_timing_summary')
        
        # Test fee_details_by_partner structure
        assert isinstance(fee_details.fee_details_by_partner, dict)
        assert "Developer GP" in fee_details.fee_details_by_partner
        assert "Investor LP" in fee_details.fee_details_by_partner
        
        # Test that GP has multiple fees
        gp_fees = fee_details.fee_details_by_partner["Developer GP"]
        assert len(gp_fees) >= 2  # Development + Asset Management fees
        
        # Test fee_cash_flows_by_partner
        assert isinstance(fee_details.fee_cash_flows_by_partner, dict)
        for partner_name, cash_flows in fee_details.fee_cash_flows_by_partner.items():
            assert isinstance(cash_flows, pd.Series)
            assert len(cash_flows) == len(timeline.period_index)
        
        # Test total_fees_by_type aggregation
        assert isinstance(fee_details.total_fees_by_type, dict)
        assert "Developer" in fee_details.total_fees_by_type
        assert "Asset Management" in fee_details.total_fees_by_type
        assert "Professional Services" in fee_details.total_fees_by_type
        
        # Test fee amounts
        assert fee_details.total_fees_by_type["Developer"] == 500000
        assert fee_details.total_fees_by_type["Asset Management"] == 120000
        assert fee_details.total_fees_by_type["Professional Services"] == 50000
        
        # Test fee_timing_summary
        assert isinstance(fee_details.fee_timing_summary, dict)
        
        # Test total fee amount
        expected_total = 500000 + 120000 + 50000  # All fees
        assert fee_details.total_partner_fees == expected_total

    def test_fee_vs_waterfall_attribution(self, mock_deal, timeline, settings):
        """Test that fee vs. waterfall attribution is accurate."""
        # Create substantial positive cash flows to ensure waterfall distributions
        positive_cash_flows = pd.Series([0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index)
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})
        
        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows
        
        # Calculate partner distributions
        calculator._calculate_partner_distributions()
        
        # Get results
        partner_results = calculator.partner_distributions.waterfall_details.partner_results
        
        # Test GP distributions
        gp_result = partner_results["Developer GP"]
        
        # GP should have both waterfall and fee distributions
        assert gp_result.distributions_from_waterfall > 0
        assert gp_result.distributions_from_fees > 0
        
        # Total should equal sum of both sources
        expected_total = gp_result.distributions_from_waterfall + gp_result.distributions_from_fees
        assert abs(gp_result.total_distributions - expected_total) < 1.0  # Allow for small rounding
        
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
        # Create positive cash flows
        positive_cash_flows = pd.Series([0, 0, 0, 50000, 50000, 50000] + [0] * 30, index=timeline.period_index)
        
        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows
        
        # Calculate partner distributions
        calculator._calculate_partner_distributions()
        
        # Test that deprecated developer_fee field still exists
        partner_results = calculator.partner_distributions.waterfall_details.partner_results
        
        for partner_name, partner_result in partner_results.items():
            assert hasattr(partner_result, 'developer_fee')
            
            # Should equal distributions_from_fees for backward compatibility
            assert partner_result.developer_fee == partner_result.distributions_from_fees

    def test_comprehensive_audit_trail(self, mock_deal, timeline, settings):
        """Test comprehensive audit trail functionality."""
        # Create positive cash flows (increased to cover fees)
        positive_cash_flows = pd.Series([0, 0, 0] + [100000] * 12 + [0] * 21, index=timeline.period_index)
        
        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows
        
        # Calculate partner distributions
        calculator._calculate_partner_distributions()
        
        # Get fee details
        fee_details = calculator.partner_distributions.fee_accounting_details
        
        # Test comprehensive audit trail
        total_tracked_fees = 0
        
        # Verify each fee is tracked individually
        for partner_name, partner_fees in fee_details.fee_details_by_partner.items():
            for fee_name, fee_amount in partner_fees.items():
                assert isinstance(fee_name, str)
                assert isinstance(fee_amount, (int, float))
                
                total_tracked_fees += fee_amount
        
        # Total tracked fees should equal total partner fees
        assert total_tracked_fees == fee_details.total_partner_fees
        
        # Test cash flow tracking
        total_cash_flows = pd.Series(0.0, index=timeline.period_index)
        for partner_cf in fee_details.fee_cash_flows_by_partner.values():
            total_cash_flows += partner_cf
        
        # Total cash flows should have positive values in expected periods
        assert total_cash_flows.sum() > 0
        
        # Test fee timing summary
        assert len(fee_details.fee_timing_summary) > 0
        
        # Verify timing matches cash flows (allow for cash flow constraints)
        for partner_name, timing in fee_details.fee_timing_summary.items():
            if timing:  # If partner has fees
                partner_cf = fee_details.fee_cash_flows_by_partner[partner_name]
                total_from_timing = sum(timing.values())
                total_from_cf = partner_cf.sum()
                
                # Allow for cases where fees couldn't be fully deducted due to cash flow constraints
                # The cash flows should be less than or equal to the planned timing
                assert total_from_cf <= total_from_timing + 1.0  # Allow small tolerance

    def test_zero_fees_handling(self, partners, timeline, settings):
        """Test that enhanced results work correctly with zero fees."""
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
        
        # Create positive cash flows
        positive_cash_flows = pd.Series([0, 0, 0, 50000, 50000, 50000] + [0] * 30, index=timeline.period_index)
        
        # Create orchestrator
        calculator = DealCalculator(deal, timeline, settings)
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows
        
        # Calculate partner distributions
        calculator._calculate_partner_distributions()
        
        # Test that enhanced fields exist but are empty/zero
        partner_results = calculator.partner_distributions.waterfall_details.partner_results
        
        for partner_name, partner_result in partner_results.items():
            assert partner_result.distributions_from_fees == 0.0
            assert partner_result.distributions_from_waterfall > 0  # Should have waterfall
            assert partner_result.total_distributions == partner_result.distributions_from_waterfall
            assert partner_result.fee_details == {}
            assert isinstance(partner_result.fee_cash_flows, pd.Series)
            assert partner_result.fee_cash_flows.sum() == 0.0
        
        # Test fee details are empty
        fee_details = calculator.partner_distributions.fee_accounting_details
        assert fee_details.total_partner_fees == 0.0
        assert fee_details.total_fees_by_type == {}
        assert all(len(fees) == 0 for fees in fee_details.fee_details_by_partner.values())

    def test_results_model_validation(self, mock_deal, timeline, settings):
        """Test that enhanced results models pass Pydantic validation."""
        # Create positive cash flows
        positive_cash_flows = pd.Series([0, 0, 0, 50000, 50000, 50000] + [0] * 30, index=timeline.period_index)
        
        # Create orchestrator
        calculator = DealCalculator(mock_deal, timeline, settings)
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows
        
        # Calculate partner distributions - this will trigger Pydantic validation
        calculator._calculate_partner_distributions()
        
        # Test that the result models validate successfully
        assert calculator.partner_distributions is not None
        
        # Test specific model validation
        from performa.deal.results import (
            FeeAccountingDetails,
            WaterfallDistributionResult,
        )
        
        # Test that the result is a valid WaterfallDistributionResult
        assert isinstance(calculator.partner_distributions, WaterfallDistributionResult)
        
        # Test that FeeAccountingDetails validates
        assert isinstance(calculator.partner_distributions.fee_accounting_details, FeeAccountingDetails)
        
        # Test enhanced fields are accessible
        fee_details = calculator.partner_distributions.fee_accounting_details
        assert hasattr(fee_details, 'fee_details_by_partner')
        assert hasattr(fee_details, 'fee_cash_flows_by_partner')
        assert hasattr(fee_details, 'total_fees_by_type')
        assert hasattr(fee_details, 'fee_timing_summary')
        
        # Test fee_cash_flows_by_partner validation
        for partner_name, cash_flows in fee_details.fee_cash_flows_by_partner.items():
            assert isinstance(cash_flows, pd.Series)
        
        # Test that all fields are properly typed
        assert isinstance(fee_details.total_fees_by_type, dict)
        assert isinstance(fee_details.fee_timing_summary, dict)
        assert isinstance(fee_details.fee_details_by_partner, dict)

    def test_complex_fee_structure(self, partners, timeline, settings):
        """Test enhanced results with complex fee structures."""
        # Create complex fee structure
        from performa.core.primitives import (
            FirstOnlyDrawSchedule,
            UniformDrawSchedule,
        )
        
        fees = [
            DealFee.create_upfront_fee(
                name="Acquisition Fee", 
                value=Decimal("250000"), 
                payee=partners.partners[0], 
                timeline=timeline,
                fee_type="Acquisition"
            ),
            DealFee.create_completion_fee(
                name="Disposition Fee", 
                value=Decimal("300000"), 
                payee=partners.partners[0], 
                timeline=timeline,
                fee_type="Disposition"
            ),
            DealFee.create_uniform_fee(
                name="Management Fee", 
                value=Decimal("240000"), 
                payee=partners.partners[0], 
                timeline=timeline,
                fee_type="Asset Management"
            ),
            DealFee.create_split_fee(
                name="Consultant Fee", 
                value=Decimal("100000"), 
                payee=partners.partners[1], 
                timeline=timeline,
                first_percentage=0.3,
                fee_type="Professional Services"
            ),
        ]
        
        # Create deal with complex fees
        deal = Mock(spec=Deal)
        deal.name = "Complex Fees Deal"
        deal.deal_type = "development"
        deal.equity_partners = partners
        deal.deal_fees = fees
        deal.has_equity_partners = True
        deal.financing = None
        deal.acquisition = None
        deal.disposition = None
        deal.asset = Mock()
        deal.asset.property_type = Mock()
        deal.asset.property_type.value = "office"
        deal.is_development_deal = True
        
        # Create substantial positive cash flows
        positive_cash_flows = pd.Series([0, 0, 0] + [200000] * 12 + [0] * 21, index=timeline.period_index)
        
        # Create orchestrator
        calculator = DealCalculator(deal, timeline, settings)
        cash_flows_df = pd.DataFrame({"net_cash_flow": positive_cash_flows})
        calculator.unlevered_analysis.cash_flows = cash_flows_df
        calculator.levered_cash_flows.levered_cash_flows = positive_cash_flows
        
        # Calculate partner distributions
        calculator._calculate_partner_distributions()
        
        # Test complex fee tracking
        fee_details = calculator.partner_distributions.fee_accounting_details
        
        # Test all fee types are tracked
        assert "Acquisition" in fee_details.total_fees_by_type
        assert "Disposition" in fee_details.total_fees_by_type
        assert "Asset Management" in fee_details.total_fees_by_type
        assert "Professional Services" in fee_details.total_fees_by_type
        
        # Test GP gets most fees
        gp_fees = fee_details.fee_details_by_partner["Developer GP"]
        assert len(gp_fees) >= 3  # Should have 3+ fees
        
        # Test LP gets consultant fee
        lp_fees = fee_details.fee_details_by_partner["Investor LP"]
        assert len(lp_fees) == 1  # Should have consultant fee only
        # Check for consultant fee by name
        assert "Consultant Fee" in lp_fees
        
        # Test total fee amounts
        expected_total = 250000 + 300000 + 240000 + 100000  # All fees
        assert fee_details.total_partner_fees == expected_total
        
        # Test partner attribution is correct
        partner_results = calculator.partner_distributions.waterfall_details.partner_results
        
        gp_fee_total = sum(gp_fees.values())
        lp_fee_total = sum(lp_fees.values())
        
        assert partner_results["Developer GP"].distributions_from_fees == gp_fee_total
        assert partner_results["Investor LP"].distributions_from_fees == lp_fee_total 