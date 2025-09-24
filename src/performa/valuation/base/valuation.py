# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Base Valuation Classes - Industry Standard Approaches

Provides the foundation for all valuation methods following
real estate appraisal industry standards.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Literal
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field

from ...core.primitives import Model

if TYPE_CHECKING:
    from performa.deal.orchestrator import DealContext


class BaseValuation(Model, ABC):
    """
    Abstract base class for all valuation methods.

    Follows the three standard real estate appraisal approaches:
    1. Income Approach (DirectCap)
    2. Sales Comparison Approach (SalesComps)
    3. Cost/Manual Approach (DirectEntry)

    All valuation classes provide a consistent interface for
    computing disposition proceeds in deal analysis.
    """

    # === CORE IDENTITY ===
    name: str = Field(..., description="Human-readable name for the valuation")
    uid: UUID = Field(default_factory=uuid4, description="Unique identifier")

    @abstractmethod
    def compute_cf(self, context: "DealContext") -> pd.Series:
        """
        Compute disposition cash flow series for this valuation method.

        This is the primary interface used by the deal orchestrator
        to calculate exit proceeds and place them at the appropriate
        time in the analysis timeline.

        Args:
            context: Deal context containing timeline, NOI series, and deal data

        Returns:
            pd.Series containing disposition proceeds aligned with timeline

        Raises:
            ValueError: If required data is missing or invalid
            RuntimeError: If valuation calculation fails
        """
        pass

    @abstractmethod
    def calculate_value(self, **kwargs) -> Dict[str, float]:
        """
        Calculate property value using this valuation method.

        This provides a standalone calculation interface separate
        from the cash flow integration (compute_cf).

        Returns:
            Dictionary with valuation results and supporting metrics
        """
        pass

    def validate_context(self, context: "DealContext") -> None:
        """
        Validate that context contains required data for this valuation.

        Override in subclasses to add method-specific validation.

        Args:
            context: Deal context to validate

        Raises:
            ValueError: If required data is missing or invalid
        """
        if not context.timeline.period_index.empty:
            return

        raise ValueError(
            "Timeline is required for valuation but not provided in context"
        )


# Type discriminator for polymorphic valuation handling
ValuationKind = Literal["direct_cap", "direct_entry", "sales_comp"]
