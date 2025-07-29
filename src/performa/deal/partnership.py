# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Partnership Models for Equity Waterfall and Distribution

This module defines partner structures and distribution logic for equity partnerships
in real estate deals. It supports both simple pari passu distributions and
sophisticated EUROPEAN-STYLE waterfall structures with IRR-based promotes.

Key Features:
- Partner modeling with GP/LP classification and ownership percentages
- Pari passu (proportional) distribution calculations
- Multi-tier waterfall distributions with IRR-based promotes
- Comprehensive validation of partnership structures and promote logic
- Industry-standard defaults for common carry structures

Example:
    ```python
    # Create a simple carry promote structure (uses industry standard defaults)
    carry = CarryPromote()  # 8% pref, 20% carry
    
    # Create partnership with waterfall distribution
    partnership = PartnershipStructure(
        partners=[
            Partner(name="Developer", kind="GP", share=0.25),
            Partner(name="Investor", kind="LP", share=0.75)
        ],
        distribution_method="waterfall",
        promote=carry
    )
    ```
"""

from typing import List, Literal, Optional, Union

from pydantic import Field, field_validator

from ..core.primitives import FloatBetween0And1, Model, PositiveFloat
from .entities import Partner


class WaterfallTier(Model):
    """
    Represents a tier in a waterfall promote structure.
    
    Each tier defines an IRR hurdle rate and the promote percentage 
    that GPs receive above that hurdle.
    
    TODO: Add support for equity multiple hurdles in addition to IRR hurdles
    Currently only IRR hurdles are supported, but industry practice also uses
    equity multiple hurdles (e.g., 2.0x equity multiple hurdle). This would
    require:
    - Adding back `metric: Literal["IRR", "EM"]` field
    - Updating waterfall algorithm to handle EM-based hurdles
    - Adding validation for EM hurdle values (should be > 1.0)
    - Testing both IRR and EM hurdle scenarios
    See also: WaterfallPromote.all_tiers property for integration points
    """
    tier_hurdle_rate: PositiveFloat = Field(..., description="IRR hurdle rate for this tier (e.g., 0.15 for 15%)")
    promote_rate: FloatBetween0And1 = Field(..., description="Percentage of distributions above hurdle going to GP")


class WaterfallPromote(Model):
    """
    Multi-tier waterfall promote structure.
    
    This structure defines multiple IRR hurdles with different promote rates,
    allowing for sophisticated institutional-grade waterfall distributions.
    """
    pref_hurdle_rate: PositiveFloat = Field(..., description="Preferred return hurdle rate (e.g., 0.08 for 8%)")
    tiers: List[WaterfallTier] = Field(..., description="List of promote tiers with increasing hurdle rates")
    final_promote_rate: FloatBetween0And1 = Field(..., description="Promote rate for distributions above all tiers")
    
    @field_validator("tiers")
    @classmethod
    def validate_tier_ordering(cls, v: List[WaterfallTier]) -> List[WaterfallTier]:
        """Validate that tiers are in ascending order of hurdle rates."""
        if len(v) > 1:
            hurdle_rates = [tier.tier_hurdle_rate for tier in v]
            if hurdle_rates != sorted(hurdle_rates):
                raise ValueError("Waterfall tiers must be in ascending order of hurdle rates")
        return v
    
    @property
    def all_tiers(self) -> tuple[List[tuple[float, float]], float]:
        """
        Get all tiers formatted for distribution calculation.
        
        Returns:
            Tuple of (tier_list, final_promote_rate) where tier_list contains
            (hurdle_rate, promote_rate) tuples in ascending order
        """
        sorted_tiers = sorted(self.tiers, key=lambda x: x.tier_hurdle_rate)
        tier_list = [(self.pref_hurdle_rate, 0.0)]  # Preferred return tier with 0% promote
        tier_list.extend((t.tier_hurdle_rate, t.promote_rate) for t in sorted_tiers)
        return tier_list, self.final_promote_rate


class CarryPromote(Model):
    """
    Simple carry promote structure.
    
    This structure defines a preferred return followed by a fixed promote rate
    for all distributions above the preferred return.
    
    Industry standard parameters:
    - 8% preferred return (pref_hurdle_rate=0.08)
    - 20% carry above preferred return (promote_rate=0.20)
    """
    pref_hurdle_rate: PositiveFloat = Field(
        default=0.08, 
        description="Preferred return hurdle rate (e.g., 0.08 for 8%)"
    )
    promote_rate: FloatBetween0And1 = Field(
        default=0.20, 
        description="Fixed promote rate for GP above preferred return"
    )

    @property
    def all_tiers(self) -> tuple[List[tuple[float, float]], float]:
        """
        Get all tiers formatted for distribution calculation.
        
        Returns:
            Tuple of (tier_list, final_promote_rate) where tier_list contains
            (hurdle_rate, promote_rate) tuples
        """
        tier_list = [(self.pref_hurdle_rate, 0.0)]  # Preferred return tier with 0% promote
        return tier_list, self.promote_rate


# Note: CarryPromote now has sensible defaults (8% pref, 20% carry)
# You can create standard carry structures with just: CarryPromote()


# Union type for all promote structures
PromoteStructure = Union[WaterfallPromote, CarryPromote]


class PartnershipStructure(Model):
    """
    Represents the complete partnership structure for a deal.
    
    This model manages the collection of partners and validates that
    the partnership structure is valid (shares sum to 100%, etc.).
    """
    
    # Core Components
    partners: List[Partner] = Field(..., description="List of equity partners")
    
    # Distribution Settings
    distribution_method: Literal["pari_passu", "waterfall"] = Field(
        default="pari_passu", 
        description="Distribution method for equity returns"
    )
    
    # Optional Promote Structure
    promote: Optional[PromoteStructure] = Field(
        default=None, 
        description="Promote structure for waterfall distributions"
    )
    
    @field_validator("partners")
    @classmethod
    def validate_partner_structure(cls, v: List[Partner]) -> List[Partner]:
        """Validate that partner structure is valid."""
        if not v:
            raise ValueError("Partnership must have at least one partner")
        
        # Check that shares sum to 100%
        total_shares = sum(partner.share for partner in v)
        if abs(total_shares - 1.0) > 0.001:  # Allow small floating point rounding errors
            raise ValueError(f"Partner shares must sum to 100%, got {total_shares:.3%}")
        
        # Check for duplicate partner names
        partner_names = [partner.name for partner in v]
        if len(partner_names) != len(set(partner_names)):
            raise ValueError("Partner names must be unique")
        
        return v
    
    @field_validator("promote")
    @classmethod
    def validate_promote_structure(cls, v: Optional[PromoteStructure], info) -> Optional[PromoteStructure]:
        """Validate promote structure compatibility with distribution method."""
        # Get the distribution_method from the data being validated
        if info.data is None:
            return v
        
        distribution_method = info.data.get("distribution_method")
        
        if distribution_method == "waterfall" and v is None:
            raise ValueError("Waterfall distribution method requires a promote structure")
        
        if distribution_method == "pari_passu" and v is not None:
            raise ValueError("Pari passu distribution method cannot have a promote structure")
        
        return v
    
    @property
    def gp_partners(self) -> List[Partner]:
        """Get all General Partners."""
        return [p for p in self.partners if p.kind == "GP"]
    
    @property
    def lp_partners(self) -> List[Partner]:
        """Get all Limited Partners."""
        return [p for p in self.partners if p.kind == "LP"]
    
    @property
    def gp_total_share(self) -> float:
        """Get total GP ownership percentage."""
        return sum(p.share for p in self.gp_partners)
    
    @property
    def lp_total_share(self) -> float:
        """Get total LP ownership percentage."""
        return sum(p.share for p in self.lp_partners)
    
    @property
    def partner_count(self) -> int:
        """Get total number of partners."""
        return len(self.partners)
    
    @property
    def has_promote(self) -> bool:
        """Check if partnership has a promote structure."""
        return self.promote is not None
    
    def get_partner_by_name(self, name: str) -> Optional[Partner]:
        """Get partner by name."""
        for partner in self.partners:
            if partner.name == name:
                return partner
        return None
    
    def __str__(self) -> str:
        gp_count = len(self.gp_partners)
        lp_count = len(self.lp_partners)
        promote_info = f", {type(self.promote).__name__}" if self.promote else ""
        return f"Partnership: {gp_count} GP(s), {lp_count} LP(s), {self.distribution_method} distribution{promote_info}"


# Export the main classes
__all__ = [
    "Partner",
    "PartnershipStructure", 
    "WaterfallTier",
    "WaterfallPromote",
    "CarryPromote",
    "PromoteStructure",
] 