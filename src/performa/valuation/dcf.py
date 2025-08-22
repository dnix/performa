# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Universal DCF Valuation - Discounted Cash Flow Analysis

Universal DCF valuation that works for any property type:
office, residential, development projects, existing assets, etc.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Literal, Optional
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, model_validator

from performa.core.primitives import Model, PositiveFloat

if TYPE_CHECKING:
    from performa.deal.orchestrator import DealContext

logger = logging.getLogger(__name__)


class DCFValuation(Model):
    """
    Universal discounted cash flow valuation for any property type.

    Provides flexible DCF modeling using industry-standard approaches
    that work across all asset classes and scenarios.

    Attributes:
        name: Human-readable name for the DCF scenario
        discount_rate: Discount rate for present value calculations
        terminal_cap_rate: Cap rate for terminal value calculation
        hold_period_years: Analysis period length in years
        terminal_growth_rate: Annual growth rate for terminal value (optional)
        reversion_costs_rate: Transaction costs at sale as percentage of gross value
        uid: Unique identifier

    Example:
        ```python
        # Standard DCF for any property type
        dcf = DCFValuation(
            name="Standard DCF",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=10
        )

        # Growth-oriented DCF with terminal value growth
        dcf = DCFValuation(
            name="Growth DCF",
            discount_rate=0.075,
            terminal_cap_rate=0.06,
            hold_period_years=7,
            terminal_growth_rate=0.02
        )
        ```
    """

    # === CORE IDENTITY ===
    name: str = Field(...)
    uid: UUID = Field(default_factory=uuid4)
    kind: Literal["dcf"] = Field(
        default="dcf", description="Discriminator field for polymorphic valuation"
    )

    # === DCF PARAMETERS ===
    discount_rate: PositiveFloat = Field(
        ..., description="Discount rate for present value calculations"
    )
    terminal_cap_rate: PositiveFloat = Field(
        ..., description="Cap rate for terminal value calculation"
    )
    hold_period_years: int = Field(..., description="Analysis period length in years")
    terminal_growth_rate: Optional[PositiveFloat] = Field(
        default=None, description="Annual growth rate for terminal value (optional)"
    )
    reversion_costs_rate: PositiveFloat = Field(
        default=0.025,
        description="Transaction costs at sale as percentage of gross value",
    )

    # === VALIDATION ===

    @model_validator(mode="after")
    def validate_dcf_parameters(self) -> "DCFValuation":
        """Validate DCF parameters are reasonable."""
        # Validate discount rate
        if not (0.02 <= self.discount_rate <= 0.25):
            raise ValueError(
                f"Discount rate ({self.discount_rate:.1%}) should be between 2% and 25%"
            )

        # Validate terminal cap rate
        if not (0.01 <= self.terminal_cap_rate <= 0.20):
            raise ValueError(
                f"Terminal cap rate ({self.terminal_cap_rate:.1%}) should be between 1% and 20%"
            )

        # Validate hold period
        if not (1 <= self.hold_period_years <= 50):
            raise ValueError(
                f"Hold period ({self.hold_period_years} years) should be between 1 and 50 years"
            )

        # Validate growth rate if provided
        if self.terminal_growth_rate is not None:
            if not (0.0 <= self.terminal_growth_rate <= 0.10):
                raise ValueError(
                    f"Terminal growth rate ({self.terminal_growth_rate:.1%}) should be between 0% and 10%"
                )

            # Growth rate should be less than discount rate
            if self.terminal_growth_rate >= self.discount_rate:
                raise ValueError(
                    f"Terminal growth rate ({self.terminal_growth_rate:.1%}) must be less than "
                    f"discount rate ({self.discount_rate:.1%})"
                )

        # Validate reversion costs
        if not (0.005 <= self.reversion_costs_rate <= 0.10):
            raise ValueError(
                f"Reversion costs rate ({self.reversion_costs_rate:.1%}) should be between 0.5% and 10%"
            )

        return self

    # === COMPUTED PROPERTIES ===

    @property
    def net_terminal_proceeds_rate(self) -> float:
        """Net proceeds rate after reversion costs."""
        return 1.0 - self.reversion_costs_rate

    @property
    def terminal_discount_factor(self) -> float:
        """Discount factor for terminal value."""
        return 1.0 / ((1.0 + self.discount_rate) ** self.hold_period_years)

    # === CALCULATION METHODS ===

    def calculate_present_value(
        self, cash_flows: pd.Series, terminal_noi: float
    ) -> Dict[str, float]:
        """
        Calculate present value of property using DCF analysis.

        Args:
            cash_flows: Time series of annual cash flows
            terminal_noi: NOI in the terminal year for reversion calculation

        Returns:
            Dictionary with DCF analysis results
        """
        if len(cash_flows) == 0:
            raise ValueError("Cash flows cannot be empty")

        # Ensure we have the right number of years
        if len(cash_flows) > self.hold_period_years:
            cash_flows = cash_flows.iloc[: self.hold_period_years]

        # Calculate present value of operating cash flows
        pv_operations = 0.0
        for year, cf in enumerate(cash_flows, start=1):
            discount_factor = 1.0 / ((1.0 + self.discount_rate) ** year)
            pv_operations += cf * discount_factor

        # Calculate terminal value
        terminal_noi_with_growth = terminal_noi
        if self.terminal_growth_rate is not None:
            # Apply growth to terminal NOI
            terminal_noi_with_growth = terminal_noi * (
                (1.0 + self.terminal_growth_rate) ** self.hold_period_years
            )

        # Terminal value using cap rate
        gross_terminal_value = terminal_noi_with_growth / self.terminal_cap_rate
        net_terminal_value = gross_terminal_value * self.net_terminal_proceeds_rate

        # Present value of terminal value
        pv_terminal = net_terminal_value * self.terminal_discount_factor

        # Total present value
        total_pv = pv_operations + pv_terminal

        return {
            "present_value": total_pv,
            "pv_operations": pv_operations,
            "pv_terminal": pv_terminal,
            "gross_terminal_value": gross_terminal_value,
            "net_terminal_value": net_terminal_value,
            "terminal_noi": terminal_noi_with_growth,
            "operations_percentage": (pv_operations / total_pv * 100)
            if total_pv > 0
            else 0.0,
            "terminal_percentage": (pv_terminal / total_pv * 100)
            if total_pv > 0
            else 0.0,
        }

    def calculate_metrics(
        self, cash_flows: pd.Series, terminal_noi: float, initial_investment: float
    ) -> Dict[str, float]:
        """
        Calculate comprehensive DCF metrics.

        Args:
            cash_flows: Time series of annual cash flows
            terminal_noi: NOI in the terminal year for reversion calculation
            initial_investment: Initial investment amount

        Returns:
            Dictionary of DCF metrics including NPV, value per dollar invested, etc.
        """
        dcf_results = self.calculate_present_value(cash_flows, terminal_noi)
        present_value = dcf_results["present_value"]

        # Calculate investment metrics
        npv = present_value - initial_investment
        value_per_dollar = (
            present_value / initial_investment if initial_investment > 0 else 0.0
        )

        return {
            **dcf_results,
            "npv": npv,
            "value_per_dollar_invested": value_per_dollar,
            "initial_investment": initial_investment,
            "profit": npv,
            "profit_margin": npv / initial_investment
            if initial_investment > 0
            else 0.0,
        }

    def calculate_sensitivity_analysis(
        self,
        cash_flows: pd.Series,
        terminal_noi: float,
        discount_rate_range: tuple[float, float] = (-0.01, 0.01),
        cap_rate_range: tuple[float, float] = (-0.005, 0.005),
        steps: int = 5,
    ) -> pd.DataFrame:
        """
        Calculate sensitivity analysis varying discount and cap rates.

        Args:
            cash_flows: Time series of annual cash flows
            terminal_noi: NOI in the terminal year for reversion calculation
            discount_rate_range: Range for discount rate variation (min, max)
            cap_rate_range: Range for cap rate variation (min, max)
            steps: Number of steps in each direction

        Returns:
            DataFrame with sensitivity analysis results
        """
        # Generate rate variations
        discount_rates = [
            self.discount_rate
            + i * (discount_rate_range[1] - discount_rate_range[0]) / (steps - 1)
            for i in range(steps)
        ]
        cap_rates = [
            self.terminal_cap_rate
            + i * (cap_rate_range[1] - cap_rate_range[0]) / (steps - 1)
            for i in range(steps)
        ]

        # Calculate present values for each combination
        results = []
        for disc_rate in discount_rates:
            for cap_rate in cap_rates:
                # Create temporary DCF with varied rates
                temp_dcf = self.model_copy(
                    update={"discount_rate": disc_rate, "terminal_cap_rate": cap_rate}
                )

                pv_result = temp_dcf.calculate_present_value(cash_flows, terminal_noi)

                results.append({
                    "discount_rate": disc_rate,
                    "terminal_cap_rate": cap_rate,
                    "present_value": pv_result["present_value"],
                    "discount_rate_delta": disc_rate - self.discount_rate,
                    "cap_rate_delta": cap_rate - self.terminal_cap_rate,
                })

        return pd.DataFrame(results)

    def compute_cf(self, context: "DealContext") -> pd.Series:
        """
        Compute disposition cash flow series for DCF valuation.

        This method calculates the present value based on projected cash flows and
        places the terminal value at the appropriate time in the analysis timeline.

        Args:
            context: Deal context containing timeline, settings, deal data, and NOI series

        Returns:
            pd.Series containing disposition proceeds aligned with timeline
        """
        # Initialize disposition cash flow series with zeros
        disposition_cf = pd.Series(0.0, index=context.timeline.period_index)

        try:
            # Get NOI series from deal context (required - no fallbacks)
            if context.noi_series is None or context.noi_series.empty:
                raise ValueError(
                    "NOI series required for DCF valuation but not provided in DealContext"
                )

            noi_series = context.noi_series

            # Convert monthly NOI to annual series for DCF calculation
            annual_periods = []
            annual_noi = []

            # Group by year and sum monthly NOI
            for year in range(noi_series.index[0].year, noi_series.index[-1].year + 1):
                # Create year mask by checking each date's year
                year_mask = pd.Series(
                    [d.year == year for d in noi_series.index], index=noi_series.index
                )
                if year_mask.any():
                    annual_noi.append(noi_series[year_mask].sum())
                    annual_periods.append(year)

                if annual_noi:
                    annual_noi_series = pd.Series(annual_noi, index=annual_periods)

                    # Use the last year's NOI as terminal NOI
                    terminal_noi = annual_noi[-1] if annual_noi else 0.0

                    # Calculate DCF present value
                    dcf_results = self.calculate_present_value(
                        cash_flows=annual_noi_series[: self.hold_period_years],
                        terminal_noi=terminal_noi,
                    )

                    # Get the net terminal value (already accounts for transaction costs)
                    net_proceeds = dcf_results["net_terminal_value"]

                    # Place disposition proceeds at the end of the hold period
                    hold_period_end = min(
                        self.hold_period_years * 12,
                        len(context.timeline.period_index),
                    )
                    if hold_period_end > 0:
                        disposition_period = context.timeline.period_index[
                            hold_period_end - 1
                        ]
                        disposition_cf[disposition_period] = net_proceeds

        except Exception as e:
            # Fail fast instead of silently returning zeros
            raise RuntimeError(f"DCF valuation failed: {e}") from e

        return disposition_cf

    # === FACTORY METHODS ===

    @classmethod
    def conservative(
        cls,
        name: str = "Conservative DCF",
        discount_rate: float = 0.09,
        terminal_cap_rate: float = 0.07,
        hold_period_years: int = 10,
        **kwargs,
    ) -> "DCFValuation":
        """Factory method for conservative DCF assumptions."""
        return cls(
            name=name,
            discount_rate=discount_rate,
            terminal_cap_rate=terminal_cap_rate,
            hold_period_years=hold_period_years,
            reversion_costs_rate=0.025,  # 2.5% transaction costs
            **kwargs,
        )

    @classmethod
    def aggressive(
        cls,
        name: str = "Aggressive DCF",
        discount_rate: float = 0.075,
        terminal_cap_rate: float = 0.055,
        hold_period_years: int = 7,
        **kwargs,
    ) -> "DCFValuation":
        """Factory method for aggressive DCF assumptions."""
        return cls(
            name=name,
            discount_rate=discount_rate,
            terminal_cap_rate=terminal_cap_rate,
            hold_period_years=hold_period_years,
            terminal_growth_rate=0.02,  # 2% terminal growth
            reversion_costs_rate=0.020,  # 2.0% transaction costs
            **kwargs,
        )
