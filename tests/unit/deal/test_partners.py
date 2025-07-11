"""
Tests for Partnership Models

This module tests the partner structure and validation logic for equity partnerships.
"""

import pytest
from pydantic import ValidationError

from performa.deal.partnership import (
    CarryPromote,
    Partner,
    PartnershipStructure,
    WaterfallPromote,
    WaterfallTier,
)


class TestPartner:
    """Tests for the Partner model."""
    
    def test_partner_creation(self):
        """Test basic partner creation."""
        partner = Partner(
            name="ABC Development",
            kind="GP",
            share=0.20,
            description="Development sponsor"
        )
        
        assert partner.name == "ABC Development"
        assert partner.kind == "GP"
        assert partner.share == 0.20
        assert partner.description == "Development sponsor"
        assert partner.uid is not None
    
    def test_partner_string_representation(self):
        """Test partner string representation."""
        partner = Partner(name="Test GP", kind="GP", share=0.15)
        assert str(partner) == "Test GP (GP): 15.0% equity"
    
    def test_partner_validation(self):
        """Test partner validation rules."""
        # Valid partner
        partner = Partner(name="Valid Partner", kind="LP", share=0.80)
        assert partner.share == 0.80
        
        # Invalid share (> 1.0)
        with pytest.raises(ValidationError):
            Partner(name="Invalid Partner", kind="LP", share=1.5)
        
        # Invalid share (< 0.0)
        with pytest.raises(ValidationError):
            Partner(name="Invalid Partner", kind="LP", share=-0.1)
        
        # Invalid kind
        with pytest.raises(ValidationError):
            Partner(name="Invalid Partner", kind="INVALID", share=0.5)  # type: ignore


class TestPartnershipStructure:
    """Tests for the PartnershipStructure model."""
    
    def test_simple_partnership_creation(self):
        """Test creating a simple 2-partner structure."""
        gp = Partner(name="Development GP", kind="GP", share=0.20)
        lp = Partner(name="Institutional LP", kind="LP", share=0.80)
        
        partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="pari_passu"
        )
        
        assert partnership.partner_count == 2
        assert partnership.gp_total_share == 0.20
        assert partnership.lp_total_share == 0.80
        assert len(partnership.gp_partners) == 1
        assert len(partnership.lp_partners) == 1
    
    def test_partnership_validation_shares_sum(self):
        """Test that partner shares must sum to 100%."""
        # Valid: shares sum to 100%
        gp = Partner(name="GP", kind="GP", share=0.30)
        lp = Partner(name="LP", kind="LP", share=0.70)
        partnership = PartnershipStructure(partners=[gp, lp])
        assert partnership.partner_count == 2
        
        # Invalid: shares sum to more than 100%
        gp_invalid = Partner(name="GP", kind="GP", share=0.60)
        lp_invalid = Partner(name="LP", kind="LP", share=0.60)
        with pytest.raises(ValidationError) as exc_info:
            PartnershipStructure(partners=[gp_invalid, lp_invalid])
        assert "must sum to 100%" in str(exc_info.value)
        
        # Invalid: shares sum to less than 100%
        gp_low = Partner(name="GP", kind="GP", share=0.20)
        lp_low = Partner(name="LP", kind="LP", share=0.60)
        with pytest.raises(ValidationError) as exc_info:
            PartnershipStructure(partners=[gp_low, lp_low])
        assert "must sum to 100%" in str(exc_info.value)
    
    def test_partnership_validation_duplicate_names(self):
        """Test that partner names must be unique."""
        gp1 = Partner(name="Same Name", kind="GP", share=0.20)
        gp2 = Partner(name="Same Name", kind="GP", share=0.30)
        lp = Partner(name="Different Name", kind="LP", share=0.50)
        
        with pytest.raises(ValidationError) as exc_info:
            PartnershipStructure(partners=[gp1, gp2, lp])
        assert "must be unique" in str(exc_info.value)
    
    def test_partnership_validation_empty_partners(self):
        """Test that partnership must have at least one partner."""
        with pytest.raises(ValidationError) as exc_info:
            PartnershipStructure(partners=[])
        assert "at least one partner" in str(exc_info.value)
    
    def test_complex_partnership_structure(self):
        """Test a more complex partnership with multiple GPs and LPs."""
        gp1 = Partner(name="Lead GP", kind="GP", share=0.15)
        gp2 = Partner(name="Co-GP", kind="GP", share=0.05)
        lp1 = Partner(name="Institutional LP", kind="LP", share=0.60)
        lp2 = Partner(name="High Net Worth LP", kind="LP", share=0.20)
        
        partnership = PartnershipStructure(
            partners=[gp1, gp2, lp1, lp2],
            distribution_method="waterfall"
        )
        
        assert partnership.partner_count == 4
        assert partnership.gp_total_share == 0.20
        assert partnership.lp_total_share == 0.80
        assert len(partnership.gp_partners) == 2
        assert len(partnership.lp_partners) == 2
        assert partnership.distribution_method == "waterfall"
    
    def test_get_partner_by_name(self):
        """Test getting partner by name."""
        gp = Partner(name="Test GP", kind="GP", share=0.25)
        lp = Partner(name="Test LP", kind="LP", share=0.75)
        partnership = PartnershipStructure(partners=[gp, lp])
        
        found_gp = partnership.get_partner_by_name("Test GP")
        assert found_gp is not None
        assert found_gp.name == "Test GP"
        assert found_gp.kind == "GP"
        
        found_lp = partnership.get_partner_by_name("Test LP")
        assert found_lp is not None
        assert found_lp.name == "Test LP"
        assert found_lp.kind == "LP"
        
        not_found = partnership.get_partner_by_name("Nonexistent Partner")
        assert not_found is None
    
    def test_partnership_string_representation(self):
        """Test partnership string representation."""
        gp = Partner(name="GP", kind="GP", share=0.20)
        lp = Partner(name="LP", kind="LP", share=0.80)
        partnership = PartnershipStructure(partners=[gp, lp])
        
        expected = "Partnership: 1 GP(s), 1 LP(s), pari_passu distribution"
        assert str(partnership) == expected


class TestCarryPromote:
    """Test the CarryPromote structure (formerly SimplePromote)."""
    
    def test_carry_promote_creation(self):
        """Test creating a carry promote structure."""
        promote = CarryPromote(
            pref_hurdle_rate=0.08,
            promote_rate=0.20
        )
        
        assert promote.pref_hurdle_rate == 0.08
        assert promote.promote_rate == 0.20
    
    def test_carry_promote_validation(self):
        """Test promote validation rules."""
        # Valid promote
        promote = CarryPromote(pref_hurdle_rate=0.10, promote_rate=0.25)
        assert promote.pref_hurdle_rate == 0.10
        assert promote.promote_rate == 0.25
        
        # Test validation errors
        with pytest.raises(ValidationError):
            CarryPromote(pref_hurdle_rate=-0.05, promote_rate=0.20)  # Negative pref rate
        
        with pytest.raises(ValidationError):
            CarryPromote(pref_hurdle_rate=0.08, promote_rate=1.5)  # Promote rate > 1
    
    def test_carry_promote_all_tiers_property(self):
        """Test the all_tiers property for waterfall compatibility."""
        promote = CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.20)
        tiers, final_rate = promote.all_tiers
        
        # Should have one tier (preferred return) with 0% promote
        assert len(tiers) == 1
        assert tiers[0] == (0.08, 0.0)
        assert final_rate == 0.20
    
    def test_carry_promote_string_representation(self):
        """Test string representation of carry promote."""
        promote = CarryPromote(
            pref_hurdle_rate=0.08,
            promote_rate=0.20
        )
        
        promote_str = str(promote)
        # The __str__ method shows the field values
        assert "pref_hurdle_rate=0.08" in promote_str
        assert "promote_rate=0.2" in promote_str
        
        # The __repr__ method includes the class name
        promote_repr = repr(promote)
        assert "CarryPromote" in promote_repr
        assert "pref_hurdle_rate=0.08" in promote_repr
        assert "promote_rate=0.2" in promote_repr


class TestWaterfallPromote:
    """Test the WaterfallPromote structure."""
    
    def test_waterfall_promote_creation(self):
        """Test creating a waterfall promote structure."""
        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,
            tiers=[
                WaterfallTier(tier_hurdle_rate=0.12, promote_rate=0.10),
                WaterfallTier(tier_hurdle_rate=0.15, promote_rate=0.20),
            ],
            final_promote_rate=0.30
        )
        
        assert promote.pref_hurdle_rate == 0.08
        assert len(promote.tiers) == 2
        assert promote.final_promote_rate == 0.30
    
    def test_waterfall_promote_tier_ordering_validation(self):
        """Test that tiers must be in ascending order."""
        # Valid ordering
        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,
            tiers=[
                WaterfallTier(tier_hurdle_rate=0.12, promote_rate=0.10),
                WaterfallTier(tier_hurdle_rate=0.15, promote_rate=0.20),
            ],
            final_promote_rate=0.30
        )
        assert len(promote.tiers) == 2
        
        # Invalid ordering should raise validation error
        with pytest.raises(ValidationError):
            WaterfallPromote(
                pref_hurdle_rate=0.08,
                tiers=[
                    WaterfallTier(tier_hurdle_rate=0.15, promote_rate=0.20),
                    WaterfallTier(tier_hurdle_rate=0.12, promote_rate=0.10),  # Out of order
                ],
                final_promote_rate=0.30
            )
    
    def test_waterfall_promote_all_tiers_property(self):
        """Test the all_tiers property."""
        promote = WaterfallPromote(
            pref_hurdle_rate=0.08,
            tiers=[
                WaterfallTier(tier_hurdle_rate=0.12, promote_rate=0.10),
                WaterfallTier(tier_hurdle_rate=0.15, promote_rate=0.20),
            ],
            final_promote_rate=0.30
        )
        
        tiers, final_rate = promote.all_tiers
        
        # Should have preferred return tier plus the defined tiers
        assert len(tiers) == 3
        assert tiers[0] == (0.08, 0.0)  # Preferred return with 0% promote
        assert tiers[1] == (0.12, 0.10)
        assert tiers[2] == (0.15, 0.20)
        assert final_rate == 0.30


class TestPartnershipIntegration:
    """Integration tests for partnership components."""
    
    def test_typical_development_partnership(self):
        """Test a typical development partnership structure."""
        # Create typical development partnership: 20% GP, 80% LP
        gp = Partner(
            name="Development Sponsor",
            kind="GP",
            share=0.20,
            description="Development and asset management sponsor"
        )

        lp = Partner(
            name="Institutional Capital",
            kind="LP",
            share=0.80,
            description="Institutional equity capital provider"
        )

        partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="pari_passu"
        )

        promote = CarryPromote(
            pref_hurdle_rate=0.08,  # 8% preferred return
            promote_rate=0.20       # 20% promote after pref
        )

        # Test partnership properties
        assert partnership.partner_count == 2
        assert partnership.gp_total_share == 0.20
        assert partnership.lp_total_share == 0.80
        assert promote.pref_hurdle_rate == 0.08
        assert promote.promote_rate == 0.20
        
        # Test that we can create a waterfall partnership with promote
        waterfall_partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="waterfall",
            promote=promote
        )
        assert waterfall_partnership.has_promote
        assert waterfall_partnership.promote.pref_hurdle_rate == 0.08

    def test_institutional_partnership(self):
        """Test a typical institutional partnership structure."""
        # Create institutional partnership: 5% GP, 95% LP
        gp = Partner(name="Fund Manager", kind="GP", share=0.05)
        lp = Partner(name="Pension Fund", kind="LP", share=0.95)

        promote = CarryPromote(
            pref_hurdle_rate=0.06,  # 6% preferred return
            promote_rate=0.15       # 15% promote after pref
        )

        partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="waterfall",
            promote=promote
        )

        # Test institutional partnership specifics
        assert partnership.partner_count == 2
        assert partnership.gp_total_share == 0.05
        assert partnership.lp_total_share == 0.95
        assert partnership.distribution_method == "waterfall"
        assert promote.pref_hurdle_rate == 0.06
        assert promote.promote_rate == 0.15
        assert partnership.has_promote

    def test_waterfall_requires_promote(self):
        """Test that waterfall method requires promote structure."""
        gp = Partner(name="GP", kind="GP", share=0.25)
        lp = Partner(name="LP", kind="LP", share=0.75)
        
        # This should raise an error - waterfall requires promote
        with pytest.raises(ValidationError) as exc_info:
            PartnershipStructure(
                partners=[gp, lp],
                distribution_method="waterfall",
                promote=None
            )
        assert "requires a promote structure" in str(exc_info.value)

    def test_pari_passu_cannot_have_promote(self):
        """Test that pari passu method cannot have promote structure."""
        gp = Partner(name="GP", kind="GP", share=0.30)
        lp = Partner(name="LP", kind="LP", share=0.70)
        
        promote = CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.20)
        
        # This should raise an error - pari passu cannot have promote
        with pytest.raises(ValidationError) as exc_info:
            PartnershipStructure(
                partners=[gp, lp],
                distribution_method="pari_passu",
                promote=promote
            )
        assert "cannot have a promote structure" in str(exc_info.value)

    def test_clear_separation_of_distribution_methods(self):
        """Test that the two distribution methods are clearly separated."""
        gp = Partner(name="GP", kind="GP", share=0.20)
        lp = Partner(name="LP", kind="LP", share=0.80)
        
        # Pari passu: No promote, proportional distribution
        pari_passu_partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="pari_passu"
        )
        assert pari_passu_partnership.distribution_method == "pari_passu"
        assert not pari_passu_partnership.has_promote
        
        # Waterfall: Must have promote, sophisticated distribution
        promote = CarryPromote(pref_hurdle_rate=0.08, promote_rate=0.25)
        waterfall_partnership = PartnershipStructure(
            partners=[gp, lp],
            distribution_method="waterfall",
            promote=promote
        )
        assert waterfall_partnership.distribution_method == "waterfall"
        assert waterfall_partnership.has_promote
        assert waterfall_partnership.promote.pref_hurdle_rate == 0.08


class TestCarryPromoteDefaults:
    """Test CarryPromote default values."""
    
    def test_carry_promote_default_values(self):
        """Test that CarryPromote has sensible default values."""
        # Standard carry with defaults
        carry = CarryPromote()
        
        # Check industry standard defaults
        assert carry.pref_hurdle_rate == 0.08  # 8% preferred return
        assert carry.promote_rate == 0.20  # 20% carry
        
        # Check that it works in partnership
        partnership = PartnershipStructure(
            partners=[
                Partner(name="GP", kind="GP", share=0.25),
                Partner(name="LP", kind="LP", share=0.75)
            ],
            distribution_method="waterfall",
            promote=carry
        )
        
        assert partnership.has_promote
        assert partnership.promote.pref_hurdle_rate == 0.08
        assert partnership.promote.promote_rate == 0.20
    
    def test_carry_promote_custom_parameters(self):
        """Test CarryPromote with custom parameters."""
        # High-performance fund carry
        carry = CarryPromote(pref_hurdle_rate=0.06, promote_rate=0.25)
        
        assert carry.pref_hurdle_rate == 0.06
        assert carry.promote_rate == 0.25
        
        # Conservative fund carry
        carry = CarryPromote(pref_hurdle_rate=0.10, promote_rate=0.15)
        
        assert carry.pref_hurdle_rate == 0.10
        assert carry.promote_rate == 0.15 