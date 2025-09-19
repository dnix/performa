# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Entity models for deal participants.

This module provides base classes for any entity that can receive payments from deals,
including equity partners and third-party service providers.
"""

from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from ..core.primitives.model import Model
from ..core.primitives.types import PositiveFloat


class Entity(Model):
    """Base model for any entity that can receive payments from deals."""

    # Core Identity
    uid: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Entity name")
    kind: Literal["GP", "LP", "Third Party"] = Field(
        ..., description="Entity classification"
    )
    description: Optional[str] = Field(None, description="Additional entity details")

    @property
    def is_equity_participant(self) -> bool:
        """Check if this entity participates in equity distributions."""
        return self.kind in ["GP", "LP"]

    def __str__(self) -> str:
        """Return string representation of the entity."""
        if self.description:
            return f"{self.name} ({self.kind}) - {self.description}"
        return f"{self.name} ({self.kind})"


class Partner(Entity):
    """Equity partner in a deal with ownership share and optional capital commitment."""

    # General partner or limited partner
    kind: Literal["GP", "LP"] = Field(..., description="Partner type")

    # Equity ownership percentage
    share: float = Field(..., description="Equity ownership percentage")

    # Capital commitment (drives funding contributions)
    capital_commitment: Optional[PositiveFloat] = Field(
        None,
        description="Explicit capital commitment in dollars. "
        "If None for ALL partners, funding is derived pro-rata from shares.",
    )

    @field_validator("share")
    @classmethod
    def validate_share(cls, v):
        """Validate that share is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError(f"Partner share must be between 0 and 1, got {v}")
        return v

    def __str__(self) -> str:
        """Return string representation of the partner."""
        return f"{self.name} ({self.kind}): {self.share:.1%} equity"


class ThirdParty(Entity):
    """External entity that receives payments but has no equity participation."""

    kind: Literal["Third Party"] = Field(
        default="Third Party", description="Third party classification"
    )

    def __str__(self) -> str:
        """Return string representation of the third party."""
        if self.description:
            return f"{self.name} (Third Party) - {self.description}"
        return f"{self.name} (Third Party)"


# Export all entity types
__all__ = [
    "Entity",
    "Partner",
    "ThirdParty",
]
