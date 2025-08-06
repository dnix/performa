# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration test for dual-entry fee orchestration.

This test validates that DealCalculator properly handles fees with:
1. Dual-entry accounting (fees as both project debit and partner credit)
2. Priority payment logic (fees paid before equity waterfall)
3. Payee-specific allocation (not pro-rata GP allocation)
4. Proper partner results with fee vs. waterfall breakdown
"""

from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from performa.core.primitives.settings import GlobalSettings
from performa.core.primitives.timeline import Timeline
from performa.deal.fees import DealFee
from performa.deal.orchestrator import DealCalculator
from performa.deal.partnership import CarryPromote, Partner, PartnershipStructure


class TestDualEntryFeeOrchestration:
    """Test dual-entry fee orchestration with DealCalculator."""
    
    @pytest.fixture
    def timeline(self):
        """Create a test timeline."""
        return Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
    
    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return GlobalSettings()
    
    @pytest.fixture
    def developer_partner(self):
        """Create a developer (GP) partner."""
        return Partner(
            name="Developer",
            kind="GP",
            share=0.20
        )
    
    @pytest.fixture
    def investor_partner(self):
        """Create an investor (LP) partner."""
        return Partner(
            name="Investor",
            kind="LP",
            share=0.80
        )
    
    @pytest.fixture
    def partnership_structure(self, developer_partner, investor_partner):
        """Create a partnership structure with waterfall."""
        return PartnershipStructure(
            partners=[developer_partner, investor_partner],
            distribution_method="waterfall",
            promote=CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.20)
        )
    
    @pytest.fixture
    def development_fee(self, developer_partner, timeline):
        """Create a development fee paid to the developer partner."""
        return DealFee.create_upfront_fee(
            name="Development Fee",
            value=500_000,
            payee=developer_partner,
            timeline=timeline,
            fee_type="Developer"
        )
    
    @pytest.fixture
    def asset_management_fee(self, developer_partner, timeline):
        """Create an asset management fee paid to the developer partner."""
        return DealFee.create_uniform_fee(
            name="Asset Management Fee",
            value=240_000,  # $20k per month for 12 months
            payee=developer_partner,
            timeline=timeline,
            fee_type="Asset Management"
        )
    
    @pytest.fixture
    def mock_deal(self, development_fee, asset_management_fee, partnership_structure):
        """Create a mock deal with fees and partnership structure."""
        deal = Mock()
        deal.name = "Test Development Deal"
        deal.deal_type = "development"
        deal.deal_fees = [development_fee, asset_management_fee]
        deal.has_equity_partners = True
        deal.equity_partners = partnership_structure
        deal.financing = None
        deal.disposition = None
        deal.acquisition = None
        deal.asset = Mock()
        deal.asset.property_type = Mock()
        deal.asset.property_type.value = "office"
        deal.is_development_deal = True
        
        return deal
    
    @pytest.fixture
    def mock_levered_cash_flows(self, timeline):
        """Create mock levered cash flows for testing."""
        # Simulate positive cash flows that can pay fees
        cash_flows = pd.Series(0.0, index=timeline.period_index)
        cash_flows.iloc[0] = -2_000_000  # Initial investment
        cash_flows.iloc[6] = 1_000_000   # Mid-project distribution
        cash_flows.iloc[11] = 2_500_000  # Final distribution
        return cash_flows
    
    def test_dual_entry_fee_processing(self, mock_deal, timeline, settings, mock_levered_cash_flows):
        """Test that fees are processed with dual-entry accounting."""
        
        # Create calculator
        calculator = DealCalculator(
            deal=mock_deal,
            timeline=timeline,
            settings=settings
        )
        
        # Mock the levered cash flows to simulate actual deal results
        calculator.levered_cash_flows = Mock()
        calculator.levered_cash_flows.levered_cash_flows = mock_levered_cash_flows
        
        # Call the fee processing method directly
        fee_details = calculator._calculate_fee_distributions(mock_levered_cash_flows)
        
        # Validate dual-entry structure
        assert "total_partner_fees" in fee_details
        assert "partner_fees_by_partner" in fee_details
        assert "fee_details_by_partner" in fee_details
        assert "fee_cash_flows_by_partner" in fee_details
        assert "remaining_cash_flows_after_fee" in fee_details
        
        # Validate total fee amount
        expected_total = 500_000 + 240_000  # Development fee + Asset management fee
        assert fee_details["total_partner_fees"] == expected_total
        
        # Validate that fees are allocated to correct payee (Developer)
        assert fee_details["partner_fees_by_partner"]["Developer"] == expected_total
        assert fee_details["partner_fees_by_partner"]["Investor"] == 0.0
        
        # Validate fee details tracking
        developer_fee_details = fee_details["fee_details_by_partner"]["Developer"]
        assert len(developer_fee_details) == 2  # Two fees
        
        fee_names = list(developer_fee_details.keys())
        assert "Development Fee" in fee_names
        assert "Asset Management Fee" in fee_names
        
        # Validate that cash flows are reduced by fee amounts
        remaining_cf = fee_details["remaining_cash_flows_after_fee"]
        original_total = mock_levered_cash_flows.sum()
        remaining_total = remaining_cf.sum()
        assert remaining_total <= original_total  # Should be reduced by fees
    
    def test_fee_priority_payment_logic(self, mock_deal, timeline, settings):
        """Test that fees are paid as priority distributions before waterfall."""
        
        calculator = DealCalculator(
            deal=mock_deal,
            timeline=timeline,
            settings=settings
        )
        
        # Create cash flows with positive distributions in all periods where fees occur
        # This ensures fees can actually be deducted
        cash_flows = pd.Series(100_000.0, index=timeline.period_index)  # $100k positive each period
        cash_flows.iloc[0] = 600_000  # Enough to cover $520k upfront fee + buffer
        
        # Now we have sufficient positive cash flows in all periods to cover fees:
        # Period 0: $600k (covers $520k upfront + monthly fee)
        # Periods 1-11: $100k each (covers $20k monthly fees)
        
        # Process fees
        fee_details = calculator._calculate_fee_distributions(cash_flows)
        
        # Validate priority payment logic
        original_positive_cf = cash_flows[cash_flows > 0].sum()
        remaining_positive_cf = fee_details["remaining_cash_flows_after_fee"][fee_details["remaining_cash_flows_after_fee"] > 0].sum()
        
        fee_reduction = original_positive_cf - remaining_positive_cf
        
        # Fee reduction should equal the total fees that could be deducted
        # In this case, all fees should be deductible since we have sufficient positive cash flows
        assert fee_reduction == fee_details["total_partner_fees"]
    
    def test_fee_timing_with_draw_schedules(self, mock_deal, timeline, settings):
        """Test that fee timing follows the draw schedules."""
        
        calculator = DealCalculator(
            deal=mock_deal,
            timeline=timeline,
            settings=settings
        )
        
        # Create uniform cash flows for testing
        uniform_cash_flows = pd.Series(100_000.0, index=timeline.period_index)
        
        # Process fees
        fee_details = calculator._calculate_fee_distributions(uniform_cash_flows)
        
        # Validate fee timing
        developer_fee_cf = fee_details["fee_cash_flows_by_partner"]["Developer"]
        
        # Development fee should be upfront (FirstOnlyDrawSchedule)
        # Asset management fee should be uniform (UniformDrawSchedule)
        
        # Development fee (upfront): $500k + Asset management fee ($20k) = $520k in first period
        expected_first_period = 500_000 + (240_000 / 12)  # $520k
        assert developer_fee_cf.iloc[0] == expected_first_period
        
        # Asset management fee (uniform): $20k per month across all periods (including first)
        monthly_asset_mgmt = 240_000 / 12  # $20k per month
        for i in range(len(developer_fee_cf)):
            # Each period should have asset management fee
            if i == 0:
                # First period has both upfront + uniform
                assert abs(developer_fee_cf.iloc[i] - expected_first_period) < 1.0
            else:
                # Other periods have only uniform fee
                assert abs(developer_fee_cf.iloc[i] - monthly_asset_mgmt) < 1.0
    
    def test_payee_validation(self, timeline, settings, development_fee):
        """Test that fees are only allocated to actual deal partners."""
        
        # Create a deal with different partners than the fee payee
        different_partner = Partner(name="Different GP", kind="GP", share=0.30)
        other_partner = Partner(name="Other LP", kind="LP", share=0.70)
        
        partnership = PartnershipStructure(
            partners=[different_partner, other_partner],
            distribution_method="waterfall",
            promote=CarryPromote()
        )
        
        mock_deal = Mock()
        mock_deal.deal_fees = [development_fee]  # Fee payee is "Developer" but not in partnership
        mock_deal.has_equity_partners = True
        mock_deal.equity_partners = partnership
        
        calculator = DealCalculator(
            deal=mock_deal,
            timeline=timeline,
            settings=settings
        )
        
        # Create test cash flows
        cash_flows = pd.Series(100_000.0, index=timeline.period_index)
        
        # Process fees
        fee_details = calculator._calculate_fee_distributions(cash_flows)
        
        # Fee should be skipped since payee is not a deal partner
        assert fee_details["total_partner_fees"] == 0.0
        assert fee_details["partner_fees_by_partner"]["Different GP"] == 0.0
        assert fee_details["partner_fees_by_partner"]["Other LP"] == 0.0
    
    def test_combination_logic(self, mock_deal, timeline, settings, mock_levered_cash_flows):
        """Test that fee and waterfall results are properly combined."""
        
        calculator = DealCalculator(
            deal=mock_deal,
            timeline=timeline,
            settings=settings
        )
        
        # Mock fee processing results
        fee_details = {
            "total_partner_fees": 740_000,
            "partner_fees_by_partner": {"Developer": 740_000, "Investor": 0.0},
            "fee_details_by_partner": {
                "Developer": {
                    "Development Fee": 500_000,
                    "Asset Management Fee": 240_000
                },
                "Investor": {}
            },
            "fee_cash_flows_by_partner": {
                "Developer": pd.Series([500_000] + [20_000] * 11, index=timeline.period_index),
                "Investor": pd.Series(0.0, index=timeline.period_index)
            },
            "remaining_cash_flows_after_fee": mock_levered_cash_flows - 740_000
        }
        
        # Mock waterfall results
        waterfall_results = {
            "distribution_method": "waterfall",
            "total_metrics": {
                "total_investment": 2_000_000,
                "total_distributions": 2_760_000,  # After fees
                "equity_multiple": 1.38,
                "irr": 0.15
            },
            "partner_distributions": {
                "Developer": {
                    "cash_flows": pd.Series([0, 0, 0, 0, 0, 0, 200_000, 0, 0, 0, 0, 500_000], index=timeline.period_index),
                    "total_distributions": 700_000,
                    "total_investment": 400_000,
                    "net_profit": 300_000,
                    "equity_multiple": 1.75,
                    "irr": 0.18
                },
                "Investor": {
                    "cash_flows": pd.Series([0, 0, 0, 0, 0, 0, 800_000, 0, 0, 0, 0, 2_000_000], index=timeline.period_index),
                    "total_distributions": 2_800_000,
                    "total_investment": 1_600_000,
                    "net_profit": 1_200_000,
                    "equity_multiple": 1.75,
                    "irr": 0.15
                }
            }
        }
        
        # Combine results
        combined = calculator._combine_fee_and_waterfall_results(fee_details, waterfall_results)
        
        # Validate combined structure
        assert combined["distribution_method"] == "waterfall"
        assert combined["total_distributions"] == 3_500_000  # Waterfall + fees
        
        # Validate developer results
        developer_result = combined["waterfall_details"]["partner_results"]["Developer"]
        assert developer_result["distributions_from_waterfall"] == 700_000
        assert developer_result["distributions_from_fees"] == 740_000
        assert developer_result["total_distributions"] == 1_440_000  # 700k + 740k
        assert developer_result["fee_count"] == 2
        
        # Validate investor results (no fees)
        investor_result = combined["waterfall_details"]["partner_results"]["Investor"]
        assert investor_result["distributions_from_waterfall"] == 2_800_000
        assert investor_result["distributions_from_fees"] == 0.0
        assert investor_result["total_distributions"] == 2_800_000
        assert investor_result["fee_count"] == 0
    
    def test_multiple_fees_same_payee(self, timeline, settings):
        """Test handling of multiple fees to the same payee."""
        
        # Create multiple fees to the same partner
        developer = Partner(name="Developer", kind="GP", share=0.25)
        
        fee1 = DealFee.create_upfront_fee(
            name="Development Fee",
            value=500_000,
            payee=developer,
            timeline=timeline
        )
        
        fee2 = DealFee.create_completion_fee(
            name="Asset Management Fee",
            value=300_000,
            payee=developer,
            timeline=timeline
        )
        
        fee3 = DealFee.create_split_fee(
            name="Acquisition Fee",
            value=200_000,
            payee=developer,
            timeline=timeline,
            first_percentage=0.5
        )
        
        # Create partnership and deal
        partnership = PartnershipStructure(
            partners=[developer, Partner(name="LP", kind="LP", share=0.75)],
            distribution_method="pari_passu"
        )
        
        mock_deal = Mock()
        mock_deal.deal_fees = [fee1, fee2, fee3]
        mock_deal.has_equity_partners = True
        mock_deal.equity_partners = partnership
        
        calculator = DealCalculator(
            deal=mock_deal,
            timeline=timeline,
            settings=settings
        )
        
        # Test cash flows
        cash_flows = pd.Series(200_000.0, index=timeline.period_index)
        
        # Process fees
        fee_details = calculator._calculate_fee_distributions(cash_flows)
        
        # Validate multiple fees to same payee
        assert fee_details["total_partner_fees"] == 1_000_000  # 500k + 300k + 200k
        assert fee_details["partner_fees_by_partner"]["Developer"] == 1_000_000
        assert len(fee_details["fee_details_by_partner"]["Developer"]) == 3
    
    def test_insufficient_cash_flow_scenario(self, timeline, settings):
        """Test handling of fees when insufficient positive cash flows are available."""
        
        # Create a simple fee and partnership
        developer = Partner(name="Developer", kind="GP", share=0.30)
        
        large_fee = DealFee.create_upfront_fee(
            name="Large Development Fee",
            value=1_000_000,
            payee=developer,
            timeline=timeline
        )
        
        partnership = PartnershipStructure(
            partners=[developer, Partner(name="LP", kind="LP", share=0.70)],
            distribution_method="pari_passu"
        )
        
        mock_deal = Mock()
        mock_deal.deal_fees = [large_fee]
        mock_deal.has_equity_partners = True
        mock_deal.equity_partners = partnership
        
        calculator = DealCalculator(
            deal=mock_deal,
            timeline=timeline,
            settings=settings
        )
        
                # Create cash flows with insufficient positive cash flows for the full fee
        cash_flows = pd.Series(0.0, index=timeline.period_index)
        cash_flows.iloc[0] = -2_000_000  # Initial investment
        cash_flows.iloc[6] = 500_000     # Only $500k positive (less than $1M fee)
        
        # Process fees
        fee_details = calculator._calculate_fee_distributions(cash_flows)
        
        # Validate insufficient cash flow handling
        original_positive_cf = cash_flows[cash_flows > 0].sum()  # $500k
        remaining_positive_cf = fee_details["remaining_cash_flows_after_fee"][fee_details["remaining_cash_flows_after_fee"] > 0].sum()
        
        fee_reduction = original_positive_cf - remaining_positive_cf
        
        # Only a portion of the fee should be deductible
        assert fee_reduction < fee_details["total_partner_fees"]  # Partial deduction
        assert fee_reduction <= original_positive_cf  # Can't exceed available cash flow
        assert remaining_positive_cf >= 0  # No negative cash flows
        
        # The amount deducted should equal the available positive cash flow in the period with the fee
        # Since the fee is upfront (period 0) but positive cash flow is in period 6, no fee should be deducted
        assert fee_reduction == 0  # No deduction possible due to timing mismatch 