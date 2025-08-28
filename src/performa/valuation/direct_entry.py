# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
DirectEntry Valuation - Manual and Rule-Based Pricing

Provides manual property valuation through explicit pricing,
unit-based multipliers, or yield targeting approaches.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Dict, Literal, Optional

import pandas as pd
from pydantic import Field, field_validator, model_validator

from ..core.primitives import PositiveFloat
from .base.valuation import BaseValuation

if TYPE_CHECKING:
    from performa.deal.orchestrator import DealContext


class DirectEntry(BaseValuation):
    """
    Manual and rule-based property valuation.

    Provides three modes of manual valuation:
    1. Explicit: Direct dollar amount
    2. Unit Multiplier: Units × rate (e.g., $/SF, $/unit)
    3. Yield Target: Reverse cap rate calculation

    This covers the "Cost Approach" in traditional appraisal
    as well as manual override scenarios.

    Attributes:
        name: Human-readable name for the valuation
        mode: Valuation mode ("explicit", "unit_multiplier", "yield_target")
        value: Explicit dollar value (for explicit mode)
        units: Number of units (for unit_multiplier mode)
        rate_per_unit: Rate per unit (for unit_multiplier mode)
        unit_type: Type of unit (e.g., "SF", "units", "keys", "stalls")
        target_cap_rate: Target cap rate (for yield_target mode)
        noi_basis_kind: NOI basis for yield target ("LTM", "NTM", "Stabilized", "ALM")

    Example:
        ```python
        # Explicit pricing
        valuation = DirectEntry.explicit(
            name="Manual Override",
            value=15_000_000
        )

        # Unit-based pricing
        valuation = DirectEntry.unit_multiplier(
            name="Per-SF Valuation",
            units=100_000,
            rate_per_unit=150.0,
            unit_type="SF"
        )

        # Yield targeting
        valuation = DirectEntry.yield_target(
            name="Target 6% Yield",
            target_cap_rate=0.06,
            noi_basis_kind="LTM"
        )
        ```
    """

    # === CORE IDENTITY ===
    kind: Literal["direct_entry"] = Field(
        default="direct_entry", description="Discriminator for polymorphic valuation"
    )

    # === VALUATION MODE ===
    mode: Literal["explicit", "unit_multiplier", "yield_target"] = Field(
        ..., description="Valuation mode"
    )

    # === EXPLICIT MODE ===
    value: Optional[PositiveFloat] = Field(
        default=None, description="Explicit dollar value (explicit mode only)"
    )

    # === UNIT MULTIPLIER MODE ===
    units: Optional[PositiveFloat] = Field(
        default=None, description="Number of units (unit_multiplier mode only)"
    )
    rate_per_unit: Optional[PositiveFloat] = Field(
        default=None, description="Rate per unit (unit_multiplier mode only)"
    )
    unit_type: Optional[str] = Field(
        default=None, description="Type of unit (e.g., 'SF', 'units', 'keys')"
    )

    # === YIELD TARGET MODE ===
    target_cap_rate: Optional[PositiveFloat] = Field(
        default=None, description="Target cap rate (yield_target mode only)"
    )
    noi_basis_kind: Optional[Literal["LTM", "NTM", "Stabilized", "ALM"]] = Field(
        default=None, description="NOI basis for yield target"
    )

    # === VALIDATION ===

    @model_validator(mode="after")
    def validate_mode_parameters(self) -> "DirectEntry":
        """Validate that required parameters are provided for each mode."""
        if self.mode == "explicit":
            if self.value is None:
                raise ValueError("Explicit mode requires 'value' parameter")

        elif self.mode == "unit_multiplier":
            if self.units is None or self.rate_per_unit is None:
                raise ValueError(
                    "Unit multiplier mode requires 'units' and 'rate_per_unit'"
                )
            if self.unit_type is None:
                raise ValueError("Unit multiplier mode requires 'unit_type'")

        elif self.mode == "yield_target":
            if self.target_cap_rate is None:
                raise ValueError("Yield target mode requires 'target_cap_rate'")
            if self.noi_basis_kind is None:
                raise ValueError("Yield target mode requires 'noi_basis_kind'")

        return self

    @field_validator("target_cap_rate")
    @classmethod
    def validate_cap_rate(cls, v: Optional[float]) -> Optional[float]:
        """Validate cap rate is reasonable."""
        if v is not None and not (0.01 <= v <= 0.20):
            raise ValueError(f"Target cap rate ({v:.1%}) should be between 1% and 20%")
        return v

    @field_validator("unit_type")
    @classmethod
    def validate_unit_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate unit type is recognized."""
        if v is not None:
            valid_types = {"SF", "units", "keys", "stalls", "acres", "rooms", "beds"}
            if v not in valid_types:
                # Allow but warn for non-standard unit types
                pass  # Could add logging here
        return v

    # === CALCULATION METHODS ===

    def calculate_value(
        self, context: Optional["DealContext"] = None
    ) -> Dict[str, float]:
        """
        Calculate property value based on the selected mode.

        Args:
            context: Deal context (required for yield_target mode)

        Returns:
            Dictionary with valuation results
        """
        if self.mode == "explicit":
            return self._calculate_explicit()
        elif self.mode == "unit_multiplier":
            return self._calculate_unit_multiplier()
        elif self.mode == "yield_target":
            if context is None:
                raise ValueError("Context required for yield_target mode")
            return self._calculate_yield_target(context)
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

    def _calculate_explicit(self) -> Dict[str, float]:
        """Calculate explicit value."""
        return {
            "property_value": self.value,
            "mode": "explicit",
        }

    def _calculate_unit_multiplier(self) -> Dict[str, float]:
        """Calculate unit multiplier value."""
        property_value = self.units * self.rate_per_unit

        return {
            "property_value": property_value,
            "units": self.units,
            "rate_per_unit": self.rate_per_unit,
            "unit_type": self.unit_type,
            "mode": "unit_multiplier",
        }

    def _calculate_yield_target(self, context: "DealContext") -> Dict[str, float]:
        """Calculate yield target value."""
        # Get NOI based on specified basis
        noi_basis = self._get_noi_basis(context)

        # Calculate value using target cap rate
        property_value = noi_basis / self.target_cap_rate

        return {
            "property_value": property_value,
            "noi_basis": noi_basis,
            "noi_basis_kind": self.noi_basis_kind,
            "target_cap_rate": self.target_cap_rate,
            "mode": "yield_target",
        }

    def _get_noi_basis(self, context: "DealContext") -> float:
        """Extract NOI basis from context based on specified kind."""
        if context.noi_series is None or context.noi_series.empty:
            raise ValueError("NOI series required for yield target but not provided")

        noi_series = context.noi_series

        if self.noi_basis_kind == "LTM":
            # Last 12 months (trailing)
            trailing_periods = min(12, len(noi_series))
            return noi_series.iloc[-trailing_periods:].sum()

        elif self.noi_basis_kind == "NTM":
            # Next 12 months (forward)
            forward_periods = min(12, len(noi_series))
            return noi_series.iloc[:forward_periods].sum()

        elif self.noi_basis_kind == "ALM":
            # Annualized last month (12× last month)
            # Include warning about potential issues
            warnings.warn(
                "ALM (12× last month) NOI basis can be unreliable for properties with "
                "revenue timing variations. Consider LTM or Stabilized instead.",
                UserWarning,
            )
            return noi_series.iloc[-1] * 12

        elif self.noi_basis_kind == "Stabilized":
            # Use average of available periods (assumes stabilized)
            return noi_series.mean() * 12

        else:
            raise ValueError(f"Unknown NOI basis kind: {self.noi_basis_kind}")

    def compute_cf(self, context: "DealContext") -> pd.Series:
        """
        Compute disposition cash flow series for DirectEntry valuation.

        Args:
            context: Deal context containing timeline and deal data

        Returns:
            pd.Series containing disposition proceeds at timeline end
        """
        # Initialize cash flow series
        disposition_cf = pd.Series(0.0, index=context.timeline.period_index)

        try:
            # Calculate value based on mode
            value_results = self.calculate_value(context)
            property_value = value_results["property_value"]

            # Place proceeds at end of timeline
            if not context.timeline.period_index.empty:
                disposition_period = context.timeline.period_index[-1]
                disposition_cf[disposition_period] = property_value

        except Exception as e:
            # Fail fast instead of silently returning zeros
            raise RuntimeError(f"DirectEntry valuation failed: {e}") from e

        return disposition_cf

    # === FACTORY METHODS ===

    @classmethod
    def explicit(cls, name: str, value: float, **kwargs) -> "DirectEntry":
        """Factory method for explicit value."""
        return cls(name=name, mode="explicit", value=value, **kwargs)

    @classmethod
    def unit_multiplier(
        cls, name: str, units: float, rate_per_unit: float, unit_type: str, **kwargs
    ) -> "DirectEntry":
        """Factory method for unit multiplier."""
        return cls(
            name=name,
            mode="unit_multiplier",
            units=units,
            rate_per_unit=rate_per_unit,
            unit_type=unit_type,
            **kwargs,
        )

    @classmethod
    def yield_target(
        cls,
        name: str,
        target_cap_rate: float,
        noi_basis_kind: Literal["LTM", "NTM", "Stabilized", "ALM"] = "LTM",
        **kwargs,
    ) -> "DirectEntry":
        """Factory method for yield targeting."""
        return cls(
            name=name,
            mode="yield_target",
            target_cap_rate=target_cap_rate,
            noi_basis_kind=noi_basis_kind,
            **kwargs,
        )
