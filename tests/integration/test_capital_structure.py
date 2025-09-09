# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for capital structure functionality.

Tests the complete capital structure system including Partner commitments,
PartnershipStructure mode detection, CashFlowEngine integration, and 
DistributionCalculator allocation logic.
"""

import pytest

from performa.deal.constructs import create_gp_lp_waterfall, create_simple_partnership
from performa.deal.entities import Partner
from performa.deal.partnership import PartnershipStructure


class TestCapitalStructureIntegration:
    """Test complete capital structure integration scenarios."""
    
    def test_derived_mode_end_to_end(self):
        """Test complete derived mode scenario (current behavior)."""
        # Create partnership without capital commitments
        partnership = create_simple_partnership(
            gp_name="Development GP",
            gp_share=0.25,
            lp_name="Pension Fund LP", 
            lp_share=0.75
        )
        
        # Should be in derived mode
        assert not partnership.has_explicit_commitments
        assert partnership.total_committed_capital is None
        
        # Capital shares should equal ownership shares
        expected_capital_shares = {
            "Development GP": 0.25,
            "Pension Fund LP": 0.75
        }
        assert partnership.capital_shares == expected_capital_shares
        
        # Should not validate commitments in derived mode
        partnership.validate_commitments(1_000_000_000)  # Should not raise
        
    def test_explicit_mode_end_to_end(self):
        """Test complete explicit mode scenario with commitments."""
        # Create partnership with explicit capital commitments
        partnership = create_simple_partnership(
            gp_name="Developer GP",
            gp_share=0.20,
            lp_name="Institutional LP",
            lp_share=0.80,
            gp_capital=4_000_000,
            lp_capital=36_000_000
        )
        
        # Should be in explicit mode
        assert partnership.has_explicit_commitments
        assert partnership.total_committed_capital == 40_000_000
        
        # Capital shares should be based on commitments, not ownership
        expected_capital_shares = {
            "Developer GP": 0.10,      # 4M / 40M = 0.10
            "Institutional LP": 0.90   # 36M / 40M = 0.90
        }
        assert partnership.capital_shares == expected_capital_shares
        
        # But ownership shares remain different
        gp = partnership.get_partner_by_name("Developer GP")
        lp = partnership.get_partner_by_name("Institutional LP")
        assert gp.share == 0.20  # 20% ownership
        assert lp.share == 0.80  # 80% ownership
        
        # Should validate commitments
        partnership.validate_commitments(35_000_000)  # Should pass
        
        with pytest.raises(ValueError) as exc_info:
            partnership.validate_commitments(50_000_000)  # Should fail
        assert "$40,000,000" in str(exc_info.value)
        assert "$50,000,000" in str(exc_info.value)
        
    def test_gp_sweat_equity_scenario(self):
        """Test realistic GP sweat equity scenario."""
        # Typical institutional structure:
        # GP gets 10% ownership but only puts in 3% of capital
        partnership = create_gp_lp_waterfall(
            gp_share=0.10,           # 10% ownership
            lp_share=0.90,           # 90% ownership
            pref_return=0.08,        # 8% preferred return
            promote_tiers=[(0.15, 0.20)],  # 20% promote above 15% IRR
            final_promote_rate=0.30,  # 30% promote at highest tier
            gp_capital=3_000_000,    # $3M commitment (3%)
            lp_capital=97_000_000    # $97M commitment (97%)
        )
        
        # Mode detection
        assert partnership.has_explicit_commitments
        assert partnership.total_committed_capital == 100_000_000
        
        # Capital shares vs ownership shares
        gp_capital_share = partnership.capital_shares["GP"]  # 3%
        lp_capital_share = partnership.capital_shares["LP"]  # 97%
        
        gp = partnership.get_partner_by_name("GP")
        lp = partnership.get_partner_by_name("LP")
        gp_ownership_share = gp.share  # 10%
        lp_ownership_share = lp.share  # 90%
        
        # Capital contributions proportional to commitments
        assert abs(gp_capital_share - 0.03) < 0.001  # 3M/100M = 3%
        assert abs(lp_capital_share - 0.97) < 0.001  # 97M/100M = 97%
        
        # But profit distributions proportional to ownership
        assert gp_ownership_share == 0.10  # 10% ownership
        assert lp_ownership_share == 0.90  # 90% ownership
        
        # This creates GP leverage: 10% profits on 3% capital
        leverage_multiple = gp_ownership_share / gp_capital_share
        assert abs(leverage_multiple - 3.33) < 0.1  # ~3.33x leverage
        
    def test_mixed_mode_rejection_integration(self):
        """Test that mixed mode is rejected in integration scenario."""
        # Create partners with mixed commitment structure  
        gp_with_commitment = Partner(
            name="Committed GP", 
            kind="GP", 
            share=0.30,
            capital_commitment=15_000_000
        )
        lp_without_commitment = Partner(
            name="Uncommitted LP",
            kind="LP",
            share=0.70
            # No capital_commitment
        )
        
        partnership = PartnershipStructure(
            partners=[gp_with_commitment, lp_without_commitment]
        )
        
        # Should fail when trying to determine mode
        with pytest.raises(ValueError) as exc_info:
            _ = partnership.has_explicit_commitments
            
        assert "Mixed capital commitment mode not supported" in str(exc_info.value)
        
        # Should also fail when trying to get capital shares
        with pytest.raises(ValueError):
            _ = partnership.capital_shares
            
        # Should also fail when trying to get total committed capital
        with pytest.raises(ValueError):
            _ = partnership.total_committed_capital
            
    def test_zero_commitment_edge_case(self):
        """Test edge case where one partner has zero commitment."""
        partnership = create_simple_partnership(
            gp_name="Zero GP",
            gp_share=0.15,
            lp_name="Full LP", 
            lp_share=0.85,
            gp_capital=0.0,         # Zero commitment
            lp_capital=50_000_000   # Full commitment
        )
        
        # Should still be explicit mode
        assert partnership.has_explicit_commitments
        assert partnership.total_committed_capital == 50_000_000
        
        # GP gets 0% of capital shares, LP gets 100%
        expected_capital_shares = {
            "Zero GP": 0.0,
            "Full LP": 1.0
        }
        assert partnership.capital_shares == expected_capital_shares
        
        # But ownership shares remain as specified
        gp = partnership.get_partner_by_name("Zero GP")
        lp = partnership.get_partner_by_name("Full LP")
        assert gp.share == 0.15
        assert lp.share == 0.85
        
    def test_equal_capital_and_ownership_scenario(self):
        """Test scenario where capital % equals ownership % (pari passu)."""
        partnership = create_simple_partnership(
            gp_name="Equal GP",
            gp_share=0.40,
            lp_name="Equal LP",
            lp_share=0.60, 
            gp_capital=20_000_000,  # 40% of 50M
            lp_capital=30_000_000   # 60% of 50M
        )
        
        # Mode detection
        assert partnership.has_explicit_commitments
        assert partnership.total_committed_capital == 50_000_000
        
        # Capital shares should equal ownership shares in this case
        expected_capital_shares = {
            "Equal GP": 0.40,  # 20M/50M = 40%
            "Equal LP": 0.60   # 30M/50M = 60%
        }
        assert partnership.capital_shares == expected_capital_shares
        
        # Ownership shares
        gp = partnership.get_partner_by_name("Equal GP")
        lp = partnership.get_partner_by_name("Equal LP")
        assert gp.share == 0.40
        assert lp.share == 0.60
        
        # In this case, capital shares == ownership shares
        assert partnership.capital_shares["Equal GP"] == gp.share
        assert partnership.capital_shares["Equal LP"] == lp.share


class TestHelperFunctionsCapitalSupport:
    """Test that helper functions properly support capital commitments."""
    
    def test_create_gp_lp_waterfall_without_capital(self):
        """Test waterfall creation without capital commitments (derived mode)."""
        partnership = create_gp_lp_waterfall(
            gp_share=0.20,
            lp_share=0.80,
            pref_return=0.08,
            promote_tiers=[(0.12, 0.15), (0.18, 0.25)],
            final_promote_rate=0.35
        )
        
        assert not partnership.has_explicit_commitments
        assert partnership.total_committed_capital is None
        assert partnership.distribution_method == "waterfall"
        assert partnership.has_promote
        
    def test_create_gp_lp_waterfall_with_capital(self):
        """Test waterfall creation with capital commitments (explicit mode)."""
        partnership = create_gp_lp_waterfall(
            gp_share=0.25,
            lp_share=0.75,
            pref_return=0.08,
            promote_tiers=[(0.15, 0.20)],
            final_promote_rate=0.30,
            gp_capital=10_000_000,
            lp_capital=40_000_000
        )
        
        assert partnership.has_explicit_commitments  
        assert partnership.total_committed_capital == 50_000_000
        assert partnership.distribution_method == "waterfall"
        assert partnership.has_promote
        
        # Check capital vs ownership split
        assert partnership.capital_shares["GP"] == 0.20    # 10M/50M
        assert partnership.capital_shares["LP"] == 0.80    # 40M/50M
        
        gp = partnership.get_partner_by_name("GP")
        lp = partnership.get_partner_by_name("LP")  
        assert gp.share == 0.25  # Ownership
        assert lp.share == 0.75  # Ownership
        
    def test_create_simple_partnership_without_capital(self):
        """Test simple partnership creation without capital (derived mode)."""
        partnership = create_simple_partnership(
            gp_name="Simple GP",
            gp_share=0.30,
            lp_name="Simple LP",
            lp_share=0.70
        )
        
        assert not partnership.has_explicit_commitments
        assert partnership.distribution_method == "pari_passu"
        assert not partnership.has_promote
        
    def test_create_simple_partnership_with_capital(self):
        """Test simple partnership creation with capital (explicit mode).""" 
        partnership = create_simple_partnership(
            gp_name="Capital GP",
            gp_share=0.25,
            lp_name="Capital LP", 
            lp_share=0.75,
            gp_capital=12_500_000,
            lp_capital=37_500_000
        )
        
        assert partnership.has_explicit_commitments
        assert partnership.total_committed_capital == 50_000_000
        assert partnership.distribution_method == "pari_passu"
        
        # Should have proportional capital and ownership in this case
        assert partnership.capital_shares["Capital GP"] == 0.25
        assert partnership.capital_shares["Capital LP"] == 0.75
        
    def test_backward_compatibility_no_breaking_changes(self):
        """Test that existing code without capital parameters still works."""
        # This should work exactly as before (derived mode)
        partnership = create_gp_lp_waterfall(
            gp_share=0.15,
            lp_share=0.85, 
            pref_return=0.08,
            promote_tiers=[(0.12, 0.20)],
            final_promote_rate=0.25
            # No capital parameters provided - should default to None
        )
        
        # Should behave exactly as before
        assert not partnership.has_explicit_commitments
        assert partnership.total_committed_capital is None
        assert partnership.capital_shares["GP"] == 0.15   # == ownership share
        assert partnership.capital_shares["LP"] == 0.85   # == ownership share
        
        # All existing functionality should work
        assert partnership.partner_count == 2
        assert partnership.gp_total_share == 0.15
        assert partnership.lp_total_share == 0.85
        assert partnership.has_promote
