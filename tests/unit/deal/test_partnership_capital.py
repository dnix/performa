# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for PartnershipStructure capital planning functionality.

Tests the enhanced PartnershipStructure model including automatic mode detection,
capital shares calculation, and commitment validation.
"""

import pytest

from performa.deal.entities import Partner
from performa.deal.partnership import PartnershipStructure


class TestPartnershipCapitalMode:
    """Test PartnershipStructure capital mode detection and logic."""
    
    def test_derived_mode_detection(self):
        """Test automatic detection of derived mode (no commitments)."""
        gp = Partner(name="GP", kind="GP", share=0.25)
        lp = Partner(name="LP", kind="LP", share=0.75)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Should detect derived mode
        assert not partnership.has_explicit_commitments
        assert partnership.total_committed_capital is None
        
        # Capital shares should equal ownership shares in derived mode
        expected_shares = {"GP": 0.25, "LP": 0.75}
        assert partnership.capital_shares == expected_shares
        
    def test_explicit_mode_detection(self):
        """Test automatic detection of explicit mode (all have commitments)."""
        gp = Partner(name="GP", kind="GP", share=0.20, capital_commitment=5_000_000)
        lp = Partner(name="LP", kind="LP", share=0.80, capital_commitment=45_000_000)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Should detect explicit mode
        assert partnership.has_explicit_commitments
        assert partnership.total_committed_capital == 50_000_000
        
        # Capital shares should be based on commitments in explicit mode
        expected_shares = {"GP": 0.10, "LP": 0.90}  # 5M/50M = 0.10, 45M/50M = 0.90
        assert partnership.capital_shares == expected_shares
        
    def test_mixed_mode_rejection(self):
        """Test that mixed mode (some with commitments, some without) is rejected."""
        gp = Partner(name="GP", kind="GP", share=0.30, capital_commitment=10_000_000)
        lp = Partner(name="LP", kind="LP", share=0.70)  # No commitment
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Should raise error when accessing has_explicit_commitments
        with pytest.raises(ValueError) as exc_info:
            _ = partnership.has_explicit_commitments
            
        assert "Mixed capital commitment mode not supported" in str(exc_info.value)
        assert "Either all partners must have explicit commitments or none" in str(exc_info.value)
        
    def test_mixed_mode_rejection_other_way(self):
        """Test mixed mode rejection when LP has commitment but GP doesn't."""
        gp = Partner(name="GP", kind="GP", share=0.15)  # No commitment
        lp = Partner(name="LP", kind="LP", share=0.85, capital_commitment=40_000_000)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Should raise error
        with pytest.raises(ValueError) as exc_info:
            _ = partnership.has_explicit_commitments
            
        assert "Mixed capital commitment mode not supported" in str(exc_info.value)


class TestPartnershipCapitalShares:
    """Test capital shares calculation in different modes."""
    
    def test_capital_shares_derived_mode(self):
        """Test capital shares calculation in derived mode."""
        gp = Partner(name="Sponsor GP", kind="GP", share=0.10)
        lp = Partner(name="Fund LP", kind="LP", share=0.90)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # In derived mode, capital shares = ownership shares
        expected = {"Sponsor GP": 0.10, "Fund LP": 0.90}
        assert partnership.capital_shares == expected
        
    def test_capital_shares_explicit_mode_equal_split(self):
        """Test capital shares when commitments are equal."""
        gp = Partner(name="GP", kind="GP", share=0.50, capital_commitment=25_000_000)
        lp = Partner(name="LP", kind="LP", share=0.50, capital_commitment=25_000_000)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Should be 50/50 split
        expected = {"GP": 0.50, "LP": 0.50}
        assert partnership.capital_shares == expected
        
    def test_capital_shares_explicit_mode_sweat_equity(self):
        """Test capital shares in GP sweat equity scenario."""
        # GP gets 20% profits but only commits 5% of capital (sweat equity)
        gp = Partner(name="Developer GP", kind="GP", share=0.20, capital_commitment=5_000_000)
        lp = Partner(name="Capital LP", kind="LP", share=0.80, capital_commitment=95_000_000)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Capital shares should reflect actual capital contribution
        expected = {"Developer GP": 0.05, "Capital LP": 0.95}  # 5M/100M, 95M/100M
        assert partnership.capital_shares == expected
        
        # But ownership shares remain different
        assert gp.share == 0.20
        assert lp.share == 0.80
        
    def test_capital_shares_zero_commitment(self):
        """Test capital shares when one partner has zero commitment."""
        gp = Partner(name="GP", kind="GP", share=0.25, capital_commitment=0.0)
        lp = Partner(name="LP", kind="LP", share=0.75, capital_commitment=100_000_000)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # GP gets 0% of capital share, LP gets 100%
        expected = {"GP": 0.0, "LP": 1.0}
        assert partnership.capital_shares == expected


class TestPartnershipCommitmentValidation:
    """Test commitment validation functionality."""
    
    def test_validate_commitments_sufficient_capital(self):
        """Test validation when commitments meet requirements."""
        gp = Partner(name="GP", kind="GP", share=0.30, capital_commitment=15_000_000)
        lp = Partner(name="LP", kind="LP", share=0.70, capital_commitment=35_000_000)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Should not raise error when commitments are sufficient
        partnership.validate_commitments(required_equity=40_000_000)  # Need 40M, have 50M
        partnership.validate_commitments(required_equity=50_000_000)  # Exact match
        
    def test_validate_commitments_insufficient_capital(self):
        """Test validation when commitments fall short."""
        gp = Partner(name="GP", kind="GP", share=0.20, capital_commitment=8_000_000)
        lp = Partner(name="LP", kind="LP", share=0.80, capital_commitment=32_000_000)
        
        partnership = PartnershipStructure(partners=[gp, lp])  # Total: 40M
        
        # Should raise clear error when commitments are insufficient
        with pytest.raises(ValueError) as exc_info:
            partnership.validate_commitments(required_equity=60_000_000)
            
        error_msg = str(exc_info.value)
        assert "Capital commitments ($40,000,000) fall short" in error_msg
        assert "required equity ($60,000,000)" in error_msg  
        assert "by $20,000,000" in error_msg
        
    def test_validate_commitments_derived_mode_no_validation(self):
        """Test that validation is skipped in derived mode."""
        gp = Partner(name="GP", kind="GP", share=0.30)
        lp = Partner(name="LP", kind="LP", share=0.70)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Should not raise error in derived mode (validation is skipped)
        partnership.validate_commitments(required_equity=1_000_000_000)
        
    def test_total_committed_capital_explicit_mode(self):
        """Test total committed capital calculation."""
        partners = [
            Partner(name="GP1", kind="GP", share=0.10, capital_commitment=3_000_000),
            Partner(name="GP2", kind="GP", share=0.05, capital_commitment=2_000_000),
            Partner(name="LP1", kind="LP", share=0.60, capital_commitment=45_000_000),
            Partner(name="LP2", kind="LP", share=0.25, capital_commitment=20_000_000),
        ]
        
        partnership = PartnershipStructure(partners=partners)
        
        assert partnership.total_committed_capital == 70_000_000
        assert partnership.has_explicit_commitments
        
    def test_total_committed_capital_derived_mode(self):
        """Test total committed capital is None in derived mode."""
        gp = Partner(name="GP", kind="GP", share=0.25)
        lp = Partner(name="LP", kind="LP", share=0.75)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        assert partnership.total_committed_capital is None
        assert not partnership.has_explicit_commitments


class TestPartnershipIntegrationWithExistingFeatures:
    """Test that capital features integrate with existing partnership functionality."""
    
    def test_existing_properties_still_work_derived_mode(self):
        """Test existing partnership properties work in derived mode."""
        gp = Partner(name="Test GP", kind="GP", share=0.35)
        lp = Partner(name="Test LP", kind="LP", share=0.65)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Existing properties should work
        assert partnership.partner_count == 2
        assert partnership.gp_total_share == 0.35
        assert partnership.lp_total_share == 0.65
        assert len(partnership.gp_partners) == 1
        assert len(partnership.lp_partners) == 1
        assert not partnership.has_promote
        
    def test_existing_properties_still_work_explicit_mode(self):
        """Test existing partnership properties work in explicit mode."""
        gp = Partner(name="Rich GP", kind="GP", share=0.15, capital_commitment=5_000_000)
        lp = Partner(name="Richer LP", kind="LP", share=0.85, capital_commitment=45_000_000)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        # Existing properties should work normally
        assert partnership.partner_count == 2
        assert partnership.gp_total_share == 0.15
        assert partnership.lp_total_share == 0.85
        assert len(partnership.gp_partners) == 1
        assert len(partnership.lp_partners) == 1
        
        # New properties should also work
        assert partnership.has_explicit_commitments
        assert partnership.total_committed_capital == 50_000_000
        
    def test_get_partner_by_name_still_works(self):
        """Test that get_partner_by_name works with commitments."""
        gp = Partner(name="Specific GP", kind="GP", share=0.40, capital_commitment=12_000_000)
        lp = Partner(name="Specific LP", kind="LP", share=0.60, capital_commitment=18_000_000)
        
        partnership = PartnershipStructure(partners=[gp, lp])
        
        found_gp = partnership.get_partner_by_name("Specific GP")
        found_lp = partnership.get_partner_by_name("Specific LP")
        not_found = partnership.get_partner_by_name("Non-existent")
        
        assert found_gp is not None
        assert found_gp.capital_commitment == 12_000_000
        assert found_lp is not None 
        assert found_lp.capital_commitment == 18_000_000
        assert not_found is None
