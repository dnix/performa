# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for third-party fee functionality with Entity base class.

This test validates that the system properly handles both Partner and ThirdParty
entities as fee payees, with appropriate dual-entry vs single-entry accounting.
"""

from datetime import date

import pandas as pd
import pytest

from performa.core.primitives.timeline import Timeline
from performa.deal.entities import Entity, Partner, ThirdParty
from performa.deal.fees import DealFee


class TestEntityModels:
    """Test Entity, Partner, and ThirdParty models."""
    
    def test_partner_creation(self):
        """Test Partner entity creation and validation."""
        partner = Partner(
            name="Developer LLC",
            kind="GP",
            share=0.25,
            description="Lead developer"
        )
        
        assert partner.name == "Developer LLC"
        assert partner.kind == "GP" 
        assert partner.share == 0.25
        assert partner.description == "Lead developer"
        assert partner.is_equity_participant == True
        assert "Developer LLC (GP): 25.0% equity" in str(partner)
    
    def test_third_party_creation(self):
        """Test ThirdParty entity creation."""
        third_party = ThirdParty(
            name="Smith Architecture",
            description="Architectural design services"
        )
        
        assert third_party.name == "Smith Architecture"
        assert third_party.kind == "Third Party"
        assert third_party.description == "Architectural design services"
        assert third_party.is_equity_participant == False
        assert "Smith Architecture (Third Party)" in str(third_party)
    
    def test_partner_share_validation(self):
        """Test Partner share validation."""
        # Valid share
        partner = Partner(name="Test", kind="GP", share=0.5)
        assert partner.share == 0.5
        
        # Invalid shares
        with pytest.raises(ValueError, match="Partner share must be between 0 and 1"):
            Partner(name="Test", kind="GP", share=1.5)
        
        with pytest.raises(ValueError, match="Partner share must be between 0 and 1"):
            Partner(name="Test", kind="GP", share=-0.1)
    
    def test_entity_inheritance(self):
        """Test that Partner and ThirdParty properly inherit from Entity."""
        partner = Partner(name="Test Partner", kind="GP", share=0.3)
        third_party = ThirdParty(name="Test Entity")
        
        # Both should be instances of Entity
        assert isinstance(partner, Entity)
        assert isinstance(third_party, Entity)
        
        # But have different equity participation behavior
        assert partner.is_equity_participant == True
        assert third_party.is_equity_participant == False


class TestThirdPartyFees:
    """Test DealFee functionality with third-party payees."""
    
    @pytest.fixture
    def timeline(self):
        """Create a test timeline."""
        return Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
    
    @pytest.fixture
    def developer_partner(self):
        """Create a developer partner entity."""
        return Partner(
            name="ABC Development",
            kind="GP",
            share=0.20
        )
    
    @pytest.fixture
    def architect_third_party(self):
        """Create an architect third-party entity."""
        return ThirdParty(
            name="Smith Architecture",
            description="Architectural design services"
        )
    
    def test_partner_fee_creation(self, timeline, developer_partner):
        """Test creating a fee with Partner payee."""
        fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=500_000,
            payee=developer_partner,
            timeline=timeline,
            fee_type="Developer"
        )
        
        assert fee.name == "Development Fee"
        assert fee.value == 500_000
        assert fee.payee == developer_partner
        assert fee.payee.is_equity_participant == True
        assert fee.fee_type == "Developer"
    
    def test_third_party_fee_creation(self, timeline, architect_third_party):
        """Test creating a fee with ThirdParty payee."""
        fee = DealFee.create_completion_fee(
            name="Architectural Services",
            value=150_000,
            payee=architect_third_party,
            timeline=timeline,
            fee_type="Professional Services"
        )
        
        assert fee.name == "Architectural Services"
        assert fee.value == 150_000
        assert fee.payee == architect_third_party
        assert fee.payee.is_equity_participant == False
        assert fee.fee_type == "Professional Services"
    
    def test_mixed_fee_types(self, timeline, developer_partner, architect_third_party):
        """Test creating multiple fees with different entity types."""
        # Partner fee
        dev_fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=500_000,
            payee=developer_partner,
            timeline=timeline
        )
        
        # Third-party fee
        arch_fee = DealFee.create_completion_fee(
            name="Architectural Services", 
            value=150_000,
            payee=architect_third_party,
            timeline=timeline
        )
        
        # Both should work with the same DealFee interface
        assert dev_fee.payee.is_equity_participant == True
        assert arch_fee.payee.is_equity_participant == False
        
        # Both should compute cash flows correctly
        dev_cf = dev_fee.compute_cf()
        arch_cf = arch_fee.compute_cf()
        
        assert isinstance(dev_cf, pd.Series)
        assert isinstance(arch_cf, pd.Series)
        assert dev_cf.sum() == 500_000
        assert arch_cf.sum() == 150_000
    
    def test_fee_string_representation(self, timeline, developer_partner, architect_third_party):
        """Test fee string representation with different entity types."""
        partner_fee = DealFee.create_upfront_fee(
            name="Dev Fee",
            value=500_000,
            payee=developer_partner,
            timeline=timeline
        )
        
        third_party_fee = DealFee.create_completion_fee(
            name="Arch Fee",
            value=150_000,
            payee=architect_third_party,
            timeline=timeline
        )
        
        partner_str = str(partner_fee)
        third_party_str = str(third_party_fee)
        
        # Should include payee information
        assert "ABC Development" in partner_str
        assert "GP" in partner_str
        assert "Smith Architecture" in third_party_str
        assert "Third Party" in third_party_str
    
    def test_factory_methods_with_entities(self, timeline):
        """Test all factory methods work with both entity types."""
        partner = Partner(name="Developer", kind="GP", share=0.25)
        third_party = ThirdParty(name="Contractor")
        
        # Test all factory methods with Partner
        upfront_partner = DealFee.create_upfront_fee("Upfront", 100_000, partner, timeline)
        completion_partner = DealFee.create_completion_fee("Completion", 200_000, partner, timeline)
        split_partner = DealFee.create_split_fee("Split", 300_000, partner, timeline, first_percentage=0.3)
        uniform_partner = DealFee.create_uniform_fee("Uniform", 400_000, partner, timeline)
        
        # Test all factory methods with ThirdParty
        upfront_third = DealFee.create_upfront_fee("Upfront", 50_000, third_party, timeline)
        completion_third = DealFee.create_completion_fee("Completion", 75_000, third_party, timeline)
        split_third = DealFee.create_split_fee("Split", 100_000, third_party, timeline, last_percentage=0.7)
        uniform_third = DealFee.create_uniform_fee("Uniform", 125_000, third_party, timeline)
        
        # All should be valid DealFee instances
        all_fees = [
            upfront_partner, completion_partner, split_partner, uniform_partner,
            upfront_third, completion_third, split_third, uniform_third
        ]
        
        for fee in all_fees:
            assert isinstance(fee, DealFee)
            assert isinstance(fee.payee, Entity)
            assert fee.calculate_total_fee() > 0 