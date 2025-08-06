# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Universal Reversion Valuation - Exit Strategy Modeling

Universal reversion valuation that works for any property type:
office, residential, development projects, existing assets, etc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Literal, Optional
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, model_validator

from ..core.primitives import Model, PositiveFloat, UnleveredAggregateLineKey

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext


class ReversionValuation(Model):
    """
    Universal exit strategy valuation for any property type.

    Provides flexible reversion modeling using cap rate methodologies
    that work across all asset classes and scenarios.

    Attributes:
        name: Human-readable name for the reversion scenario
        cap_rate: Cap rate for property valuation at reversion
        transaction_costs_rate: Transaction costs as percentage of sale price
        hold_period_months: Holding period to reversion (optional)
        cap_rates_by_use: Asset-specific cap rates for mixed-use properties
        uid: Unique identifier

    Example:
        ```python
        # Simple reversion for any property type
        reversion = ReversionValuation(
            name="Standard Sale",
            cap_rate=0.065,
            transaction_costs_rate=0.025
        )

        # Mixed-use with different cap rates
        reversion = ReversionValuation(
            name="Mixed-Use Sale",
            cap_rate=0.06,  # Blended rate
            cap_rates_by_use={
                "office": 0.055,
                "retail": 0.070,
                "residential": 0.045
            },
            transaction_costs_rate=0.030
        )
        ```
    """

    # === CORE IDENTITY ===
    name: str = Field(...)
    uid: UUID = Field(default_factory=uuid4)
    kind: Literal["reversion"] = Field(
        default="reversion", description="Discriminator field for polymorphic valuation"
    )

    # === REVERSION PARAMETERS ===
    cap_rate: PositiveFloat = Field(
        ..., description="Cap rate for property valuation at reversion"
    )
    transaction_costs_rate: PositiveFloat = Field(
        default=0.025, description="Transaction costs as percentage of sale price"
    )
    hold_period_months: Optional[int] = Field(
        default=None, description="Holding period to reversion (optional for modeling)"
    )

    # === ADVANCED PARAMETERS ===
    cap_rates_by_use: Optional[Dict[str, PositiveFloat]] = Field(
        default=None, description="Asset-specific cap rates for mixed-use properties"
    )

    # === VALIDATION ===

    @model_validator(mode="after")
    def validate_reversion_parameters(self) -> "ReversionValuation":
        """Validate reversion parameters are reasonable."""
        # Validate main cap rate
        if not (0.01 <= self.cap_rate <= 0.20):
            raise ValueError(
                f"Cap rate ({self.cap_rate:.1%}) should be between 1% and 20%"
            )

        # Validate transaction costs
        if not (0.005 <= self.transaction_costs_rate <= 0.10):
            raise ValueError(
                f"Transaction costs rate ({self.transaction_costs_rate:.1%}) should be between 0.5% and 10%"
            )

        # Validate asset-specific cap rates if provided
        if self.cap_rates_by_use:
            for use_type, cap_rate in self.cap_rates_by_use.items():
                if not (0.01 <= cap_rate <= 0.20):
                    raise ValueError(
                        f"Cap rate for {use_type} ({cap_rate:.1%}) should be between 1% and 20%"
                    )

        return self

    # === COMPUTED PROPERTIES ===

    @property
    def net_sale_proceeds_rate(self) -> float:
        """Net proceeds rate after transaction costs."""
        return 1.0 - self.transaction_costs_rate

    # === CALCULATION METHODS ===

    def calculate_gross_value(
        self, stabilized_noi: float, noi_by_use: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calculate gross disposition value based on stabilized NOI.

        Args:
            stabilized_noi: Total stabilized NOI
            noi_by_use: NOI breakdown by use type (for mixed-use properties)

        Returns:
            Gross disposition value before transaction costs
        """
        if self.cap_rates_by_use and noi_by_use:
            # Use asset-specific cap rates
            total_value = 0.0
            for use_type, noi in noi_by_use.items():
                if use_type in self.cap_rates_by_use:
                    cap_rate = self.cap_rates_by_use[use_type]
                    total_value += noi / cap_rate
                else:
                    # Fall back to blended cap rate
                    total_value += noi / self.cap_rate
            return total_value
        else:
            # Simple cap rate valuation
            return stabilized_noi / self.cap_rate

    def calculate_net_proceeds(
        self, stabilized_noi: float, noi_by_use: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calculate net disposition proceeds after transaction costs.

        Args:
            stabilized_noi: Total stabilized NOI
            noi_by_use: NOI breakdown by use type (for mixed-use properties)

        Returns:
            Net disposition proceeds after transaction costs
        """
        gross_value = self.calculate_gross_value(stabilized_noi, noi_by_use)
        return gross_value * self.net_sale_proceeds_rate

    def calculate_metrics(
        self,
        stabilized_noi: float,
        total_cost_basis: float,
        noi_by_use: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Calculate key reversion metrics.

        Args:
            stabilized_noi: Total stabilized NOI
            total_cost_basis: Total cost basis (acquisition + development + improvements)
            noi_by_use: NOI breakdown by use type (for mixed-use properties)

        Returns:
            Dictionary of reversion metrics
        """
        gross_value = self.calculate_gross_value(stabilized_noi, noi_by_use)
        net_proceeds = self.calculate_net_proceeds(stabilized_noi, noi_by_use)

        return {
            "gross_reversion_value": gross_value,
            "net_reversion_proceeds": net_proceeds,
            "transaction_costs": gross_value - net_proceeds,
            "total_profit": net_proceeds - total_cost_basis,
            "profit_margin": (net_proceeds - total_cost_basis) / total_cost_basis
            if total_cost_basis > 0
            else 0.0,
            "reversion_cap_rate": self.cap_rate,
            "stabilized_yield_on_cost": stabilized_noi / total_cost_basis
            if total_cost_basis > 0
            else 0.0,
        }

    def compute_cf(self, context: "AnalysisContext") -> pd.Series:
        """
        Compute disposition cash flow series for reversion valuation.

        This method calculates the net disposition proceeds and places them at the
        appropriate time in the analysis timeline, typically at the end of the hold period.

        Args:
            context: Analysis context containing timeline, settings, and analysis results

        Returns:
            pd.Series containing disposition proceeds aligned with timeline
        """
        # Initialize disposition cash flow series with zeros
        disposition_cf = pd.Series(0.0, index=context.timeline.period_index)

        try:
            # Extract stabilized NOI from unlevered analysis
            if hasattr(context, "unlevered_analysis") and context.unlevered_analysis:
                # Get NOI series from the analysis
                noi_series = context.unlevered_analysis.get_series(
                    UnleveredAggregateLineKey.NET_OPERATING_INCOME, context.timeline
                )

                # Use the last period's NOI as stabilized NOI (annualized)
                if not noi_series.empty:
                    stabilized_monthly_noi = noi_series.iloc[-1]  # Last period NOI
                    stabilized_annual_noi = stabilized_monthly_noi * 12  # Annualize
                else:
                    stabilized_annual_noi = 0.0
            else:
                # Fallback: try to get from resolved lookups
                noi_lookup = context.resolved_lookups.get(
                    UnleveredAggregateLineKey.NET_OPERATING_INCOME.value
                )
                if noi_lookup is not None and isinstance(noi_lookup, pd.Series):
                    stabilized_monthly_noi = (
                        noi_lookup.iloc[-1] if not noi_lookup.empty else 0.0
                    )
                    stabilized_annual_noi = stabilized_monthly_noi * 12
                else:
                    stabilized_annual_noi = 0.0

            # Calculate net disposition proceeds using our existing logic
            if stabilized_annual_noi > 0:
                net_proceeds = self.calculate_net_proceeds(stabilized_annual_noi)

                # Place disposition proceeds at the end of the analysis period
                # (typically the last month of the timeline)
                if not context.timeline.period_index.empty:
                    disposition_period = context.timeline.period_index[-1]
                    disposition_cf[disposition_period] = net_proceeds

        except Exception as e:
            # Log warning but continue with zeros
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Could not calculate reversion disposition proceeds: {e}")

        return disposition_cf

    # === FACTORY METHODS ===

    @classmethod
    def conservative(
        cls, name: str = "Conservative Sale", cap_rate: float = 0.065, **kwargs
    ) -> "ReversionValuation":
        """Factory method for conservative reversion assumptions."""
        return cls(
            name=name,
            cap_rate=cap_rate,
            transaction_costs_rate=0.025,  # 2.5% transaction costs
            **kwargs,
        )

    @classmethod
    def aggressive(
        cls, name: str = "Aggressive Sale", cap_rate: float = 0.055, **kwargs
    ) -> "ReversionValuation":
        """Factory method for aggressive reversion assumptions."""
        return cls(
            name=name,
            cap_rate=cap_rate,
            transaction_costs_rate=0.020,  # 2.0% transaction costs
            **kwargs,
        )
