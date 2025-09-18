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

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import Field, computed_field, field_validator

from ..core.primitives import FloatBetween0And1, Model, PositiveFloat
from .entities import Partner

# =============================================================================
# WATERFALL TIERS
# =============================================================================


class BaseWaterfallTier(Model):
    """
    Abstract base class for waterfall tiers.
    
    All tier types (IRR, EM, etc.) share a promote rate but have different
    hurdle metrics.
    """
    
    promote_rate: FloatBetween0And1 = Field(
        ..., description="Percentage of distributions above hurdle going to GP"
    )
    
    class Config:
        """Pydantic configuration."""
        extra = "forbid"  # No extra fields allowed


class IRRWaterfallTier(BaseWaterfallTier):
    """
    IRR-based waterfall tier.
    
    Defines an IRR hurdle rate and the promote percentage that GPs receive
    above that hurdle.
    """
    
    tier_hurdle_rate: PositiveFloat = Field(
        ..., description="IRR hurdle rate for this tier (e.g., 0.15 for 15%)"
    )


class EMWaterfallTier(BaseWaterfallTier):
    """
    Equity Multiple-based waterfall tier.
    
    Defines an equity multiple hurdle and the promote percentage that GPs
    receive above that hurdle.
    """
    
    tier_hurdle_multiple: float = Field(
        ..., 
        ge=1.0,
        description="Equity multiple hurdle for this tier (e.g., 1.5 for 1.5x)"
    )
    
    @field_validator("tier_hurdle_multiple")
    @classmethod
    def validate_multiple(cls, v: float) -> float:
        """Ensure equity multiple is at least 1.0x (return of capital)."""
        if v < 1.0:
            raise ValueError("Equity multiple hurdle must be at least 1.0x")
        return v


# Legacy alias for backward compatibility
WaterfallTier = IRRWaterfallTier


# =============================================================================
# WATERFALL PROMOTE STRUCTURES
# =============================================================================

class BaseWaterfallPromote(Model):
    """
    Abstract base class for waterfall promote structures.
    
    All waterfall types share a final promote rate but differ in their
    tier definitions and hurdle metrics.
    """
    
    final_promote_rate: FloatBetween0And1 = Field(
        ..., description="Promote rate for distributions above all tiers"
    )
    
    @property
    def promote_type(self) -> Literal["IRR", "EM", "Hybrid"]:
        """Get the type of promote structure for polymorphic handling."""
        if isinstance(self, IRRWaterfallPromote):
            return "IRR"
        elif isinstance(self, EMWaterfallPromote):
            return "EM"
        elif isinstance(self, HybridWaterfallPromote):
            return "Hybrid"
        else:
            raise ValueError(f"Unknown promote type: {type(self).__name__}")
    
    @property
    def all_tiers(self) -> tuple[List[tuple[float, float]], float]:
        """
        Get all tiers formatted for distribution calculation.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement all_tiers property")


class IRRWaterfallPromote(BaseWaterfallPromote):
    """
    IRR-based multi-tier waterfall promote structure.

    This structure defines multiple IRR hurdles with different promote rates,
    allowing for sophisticated institutional-grade waterfall distributions.
    """

    pref_hurdle_rate: PositiveFloat = Field(
        ..., description="Preferred return hurdle rate (e.g., 0.08 for 8%)"
    )
    tiers: List[IRRWaterfallTier] = Field(
        ..., description="List of promote tiers with increasing hurdle rates"
    )

    @field_validator("tiers")
    @classmethod
    def validate_tier_ordering(cls, v: List[IRRWaterfallTier]) -> List[IRRWaterfallTier]:
        """Validate that tiers are in ascending order of hurdle rates."""
        if len(v) > 1:
            hurdle_rates = [tier.tier_hurdle_rate for tier in v]
            if hurdle_rates != sorted(hurdle_rates):
                raise ValueError(
                    "Waterfall tiers must be in ascending order of hurdle rates"
                )
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
        tier_list = [
            (self.pref_hurdle_rate, 0.0)
        ]  # Preferred return tier with 0% promote
        tier_list.extend((t.tier_hurdle_rate, t.promote_rate) for t in sorted_tiers)
        return tier_list, self.final_promote_rate


class EMWaterfallPromote(BaseWaterfallPromote):
    """
    Equity Multiple-based multi-tier waterfall promote structure.
    
    This structure uses equity multiple hurdles instead of IRR hurdles,
    which is simpler to calculate and more predictable.
    """
    
    return_of_capital_multiple: float = Field(
        default=1.0,
        ge=1.0, 
        le=1.0,
        description="Return of capital multiple (always 1.0x)"
    )
    tiers: List[EMWaterfallTier] = Field(
        ..., description="List of promote tiers with increasing equity multiples"
    )
    
    @field_validator("tiers")
    @classmethod
    def validate_tier_ordering(cls, v: List[EMWaterfallTier]) -> List[EMWaterfallTier]:
        """Validate that tiers are in ascending order of equity multiples."""
        if len(v) > 1:
            multiples = [tier.tier_hurdle_multiple for tier in v]
            if multiples != sorted(multiples):
                raise ValueError(
                    "Waterfall tiers must be in ascending order of equity multiples"
                )
            # Ensure all tiers are above 1.0x
            if any(m <= 1.0 for m in multiples):
                raise ValueError(
                    "All tier multiples must be greater than 1.0x (return of capital)"
                )
        return v
    
    @property
    def all_tiers(self) -> tuple[List[tuple[float, float]], float]:
        """
        Get all tiers formatted for distribution calculation.
        
        Returns:
            Tuple of (tier_list, final_promote_rate) where tier_list contains
            (equity_multiple, promote_rate) tuples in ascending order
        """
        sorted_tiers = sorted(self.tiers, key=lambda x: x.tier_hurdle_multiple)
        tier_list = [
            (1.0, 0.0)  # Return of capital with 0% promote
        ]
        tier_list.extend((t.tier_hurdle_multiple, t.promote_rate) for t in sorted_tiers)
        return tier_list, self.final_promote_rate


class HybridWaterfallPromote(BaseWaterfallPromote):
    """
    Hybrid waterfall that combines IRR and EM hurdles.
    
    Can apply either the more restrictive (min) or less restrictive (max)
    of the two hurdle types at each tier.
    """
    
    irr_waterfall: IRRWaterfallPromote = Field(
        ..., description="IRR-based waterfall component"
    )
    em_waterfall: EMWaterfallPromote = Field(
        ..., description="Equity multiple-based waterfall component"
    )
    logic: Literal["min", "max"] = Field(
        default="min",
        description="How to combine hurdles: 'min' = more restrictive, 'max' = less restrictive"
    )
    
    @property
    def all_tiers(self) -> tuple[List[tuple[float, float]], float]:
        """
        Returns a combined view of both waterfall structures.
        
        Note: This is primarily for compatibility. The distribution calculator
        handles hybrid logic by calculating both waterfalls and applying the
        min/max logic to determine which result to use.
        
        Returns:
            IRR tiers as the primary structure since they're time-sensitive,
            but the actual distribution uses both waterfalls.
        """
        # Return IRR tiers as the primary structure
        # The distribution calculator will evaluate both waterfalls separately
        return self.irr_waterfall.all_tiers
    
    @property
    def hybrid_tiers(self) -> Dict[str, Any]:
        """
        Get complete tier information for hybrid waterfall.
        
        Returns:
            Dictionary containing both IRR and EM tier structures:
            {
                "irr_tiers": (tier_list, final_promote_rate),
                "em_tiers": (tier_list, final_promote_rate),
                "logic": "min" or "max"
            }
        """
        irr_tiers, irr_final = self.irr_waterfall.all_tiers
        em_tiers, em_final = self.em_waterfall.all_tiers
        
        return {
            "irr_tiers": (irr_tiers, irr_final),
            "em_tiers": (em_tiers, em_final),
            "logic": self.logic
        }


# NOTE: Backward compatibility alias
WaterfallPromote = IRRWaterfallPromote


# =============================================================================
# CARRY PROMOTE STRUCTURE
# =============================================================================

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
        default=0.08, description="Preferred return hurdle rate (e.g., 0.08 for 8%)"
    )
    promote_rate: FloatBetween0And1 = Field(
        default=0.20, description="Fixed promote rate for GP above preferred return"
    )

    @property
    def all_tiers(self) -> tuple[List[tuple[float, float]], float]:
        """
        Get all tiers formatted for distribution calculation.
        
        For carry promote:
        - A single tier at the pref hurdle where carry kicks in
        - Carry applies immediately at the preferred return hurdle

        Returns:
            Tuple of (tier_list, final_promote_rate) where tier_list contains
            (hurdle_rate, promote_rate) tuples
        """
        tier_list = [
            (self.pref_hurdle_rate, self.promote_rate)
        ]  # Carry kicks in at preferred return hurdle
        return tier_list, self.promote_rate


# Note: CarryPromote now has sensible defaults (8% pref, 20% carry)
# You can create standard carry structures with just: CarryPromote()


# Union type for all promote structures
# Type alias for all supported promote structures
PromoteStructure = Union[
    IRRWaterfallPromote,
    EMWaterfallPromote, 
    HybridWaterfallPromote,
    CarryPromote,
]


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
        default="pari_passu", description="Distribution method for equity returns"
    )

    # Optional Promote Structure
    promote: Optional[PromoteStructure] = Field(
        default=None, description="Promote structure for waterfall distributions"
    )

    @field_validator("partners")
    @classmethod
    def validate_partner_structure(cls, v: List[Partner]) -> List[Partner]:
        """Validate that partner structure is valid."""
        if not v:
            raise ValueError("Partnership must have at least one partner")

        # Check that shares sum to 100%
        total_shares = sum(partner.share for partner in v)
        if (
            abs(total_shares - 1.0) > 0.001
        ):  # Allow small floating point rounding errors
            raise ValueError(f"Partner shares must sum to 100%, got {total_shares:.3%}")

        # Check for duplicate partner names
        partner_names = [partner.name for partner in v]
        if len(partner_names) != len(set(partner_names)):
            raise ValueError("Partner names must be unique")

        return v

    @field_validator("promote")
    @classmethod
    def validate_promote_structure(
        cls, v: Optional[PromoteStructure], info
    ) -> Optional[PromoteStructure]:
        """Validate promote structure compatibility with distribution method."""
        # Get the distribution_method from the data being validated
        if info.data is None:
            return v

        distribution_method = info.data.get("distribution_method")

        if distribution_method == "waterfall" and v is None:
            raise ValueError(
                "Waterfall distribution method requires a promote structure"
            )

        if distribution_method == "pari_passu" and v is not None:
            raise ValueError(
                "Pari passu distribution method cannot have a promote structure"
            )

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

    @computed_field
    @property
    def has_explicit_commitments(self) -> bool:
        """Check if using explicit capital commitments (inferred from data)."""
        # All partners must have commitments or none (no mixed mode)
        has_any = any(p.capital_commitment is not None for p in self.partners)
        has_all = all(p.capital_commitment is not None for p in self.partners)
        
        if has_any and not has_all:
            raise ValueError(
                "Mixed capital commitment mode not supported. "
                "Either all partners must have explicit commitments or none."
            )
        return has_all

    @computed_field
    @property
    def total_committed_capital(self) -> Optional[float]:
        """Total committed capital from all partners."""
        if not self.has_explicit_commitments:
            return None  # Will be derived at runtime
        
        return sum(p.capital_commitment for p in self.partners)

    @computed_field
    @property
    def capital_shares(self) -> Dict[str, float]:
        """Each partner's share of total capital (different from ownership share)."""
        if not self.has_explicit_commitments:
            # When derived, capital shares = ownership shares
            return {p.name: p.share for p in self.partners}
        
        total = self.total_committed_capital
        return {p.name: p.capital_commitment / total for p in self.partners}

    def validate_commitments(self, required_equity: float) -> None:
        """Validate that commitments meet or exceed requirements."""
        if self.has_explicit_commitments:
            total = self.total_committed_capital
            if total < required_equity:
                shortfall = required_equity - total
                raise ValueError(
                    f"Capital commitments (${total:,.0f}) fall short of "
                    f"required equity (${required_equity:,.0f}) by ${shortfall:,.0f}"
                )

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
