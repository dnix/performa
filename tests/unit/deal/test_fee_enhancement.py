# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Test suite for DealFee model with payee Partner field.

This test suite validates that the DealFee model has been successfully updated
with Partner payee information and fee type categorization.
"""

from datetime import date

import pytest

from performa.core.primitives.timeline import Timeline
from performa.deal.fees import DealFee
from performa.deal.partnership import Partner


class TestDealFee:
    """Test suite for DealFee model."""
    
    @pytest.fixture
    def sample_partner(self):
        """Create a sample partner for testing."""
        return Partner(
            name="Developer",
            kind="GP",
            share=0.25
        )
    
    @pytest.fixture
    def sample_timeline(self):
        """Create a sample timeline for testing."""
        return Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
    
    def test_dealfee_requires_payee(self, sample_timeline):
        """Test that DealFee requires a payee Partner."""
        with pytest.raises(ValueError, match="Field required"):
            DealFee(
                name="Test Fee",
                value=100000,
                timeline=sample_timeline
                # Missing payee field
            )
    
    def test_dealfee_with_payee_and_fee_type(self, sample_partner, sample_timeline):
        """Test DealFee creation with payee and fee type."""
        fee = DealFee(
            name="Development Fee",
            value=500000,
            payee=sample_partner,
            timeline=sample_timeline,
            fee_type="Developer"
        )
        
        assert fee.name == "Development Fee"
        assert fee.value == 500000
        assert fee.payee == sample_partner
        assert fee.fee_type == "Developer"
        assert fee.timeline == sample_timeline
    
    def test_dealfee_optional_fee_type(self, sample_partner, sample_timeline):
        """Test DealFee creation with optional fee type."""
        fee = DealFee(
            name="Asset Management Fee",
            value=250000,
            payee=sample_partner,
            timeline=sample_timeline
            # No fee_type specified
        )
        
        assert fee.name == "Asset Management Fee"
        assert fee.value == 250000
        assert fee.payee == sample_partner
        assert fee.fee_type is None
    
    def test_upfront_fee_factory(self, sample_partner, sample_timeline):
        """Test create_upfront_fee factory method."""
        fee = DealFee.create_upfront_fee(
            name="Upfront Dev Fee",
            value=300000,
            payee=sample_partner,
            timeline=sample_timeline,
            fee_type="Developer"
        )
        
        assert fee.name == "Upfront Dev Fee"
        assert fee.value == 300000
        assert fee.payee == sample_partner
        assert fee.fee_type == "Developer"
        assert fee.upfront_amount() == 300000
        assert fee.completion_amount() == 0
    
    def test_completion_fee_factory(self, sample_partner, sample_timeline):
        """Test create_completion_fee factory method."""
        fee = DealFee.create_completion_fee(
            name="Completion Dev Fee",
            value=400000,
            payee=sample_partner,
            timeline=sample_timeline,
            fee_type="Developer"
        )
        
        assert fee.name == "Completion Dev Fee"
        assert fee.value == 400000
        assert fee.payee == sample_partner
        assert fee.fee_type == "Developer"
        assert fee.upfront_amount() == 0
        assert fee.completion_amount() == 400000
    
    def test_split_fee_factory(self, sample_partner, sample_timeline):
        """Test create_split_fee factory method."""
        fee = DealFee.create_split_fee(
            name="Split Dev Fee",
            value=600000,
            payee=sample_partner,
            timeline=sample_timeline,
            first_percentage=0.3,
            fee_type="Developer"
        )
        
        assert fee.name == "Split Dev Fee"
        assert fee.value == 600000
        assert fee.payee == sample_partner
        assert fee.fee_type == "Developer"
        assert fee.upfront_amount() == 180000  # 30% of 600k
        assert fee.completion_amount() == 420000  # 70% of 600k
    
    def test_uniform_fee_factory(self, sample_partner, sample_timeline):
        """Test create_uniform_fee factory method."""
        fee = DealFee.create_uniform_fee(
            name="Uniform Dev Fee",
            value=240000,
            payee=sample_partner,
            timeline=sample_timeline,
            fee_type="Developer"
        )
        
        assert fee.name == "Uniform Dev Fee"
        assert fee.value == 240000
        assert fee.payee == sample_partner
        assert fee.fee_type == "Developer"
        
        # Uniform fee should distribute evenly across timeline
        cash_flows = fee.compute_cf()
        assert len(cash_flows) == 12  # 12 months
        assert all(cf == 20000 for cf in cash_flows)  # 240k / 12 months = 20k per month
    
    def test_str_representation(self, sample_partner, sample_timeline):
        """Test string representation with payee information."""
        fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=500000,
            payee=sample_partner,
            timeline=sample_timeline
        )
        
        str_repr = str(fee)
        assert "Development Fee" in str_repr
        assert "$500,000" in str_repr
        assert "Developer" in str_repr
        assert "(GP)" in str_repr
    
    def test_different_partner_types(self, sample_timeline):
        """Test fees with different partner types."""
        gp_partner = Partner(name="General Partner", kind="GP", share=0.20)
        lp_partner = Partner(name="Limited Partner", kind="LP", share=0.80)
        
        gp_fee = DealFee.create_upfront_fee(
            name="GP Fee",
            value=100000,
            payee=gp_partner,
            timeline=sample_timeline
        )
        
        lp_fee = DealFee.create_upfront_fee(
            name="LP Fee",
            value=50000,
            payee=lp_partner,
            timeline=sample_timeline
        )
        
        assert gp_fee.payee.kind == "GP"
        assert lp_fee.payee.kind == "LP"
        assert "General Partner" in str(gp_fee)
        assert "Limited Partner" in str(lp_fee)
    
    def test_factory_methods_require_payee(self, sample_timeline):
        """Test that all factory methods require payee parameter."""
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'payee'"):
            DealFee.create_upfront_fee(
                name="Test Fee",
                value=100000,
                timeline=sample_timeline
                # Missing payee
            )
        
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'payee'"):
            DealFee.create_completion_fee(
                name="Test Fee",
                value=100000,
                timeline=sample_timeline
                # Missing payee
            )
        
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'payee'"):
            DealFee.create_split_fee(
                name="Test Fee",
                value=100000,
                timeline=sample_timeline,
                first_percentage=0.5
                # Missing payee
            )
        
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'payee'"):
            DealFee.create_uniform_fee(
                name="Test Fee",
                value=100000,
                timeline=sample_timeline
                # Missing payee
            ) 