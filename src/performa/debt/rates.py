"""Interest rate models for debt facilities"""

from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from ..core.primitives import FloatBetween0And1, Model


class InterestRateType(str, Enum):
    """Type of interest rate"""

    FIXED = "fixed"
    FLOATING = "floating"
    # TODO: implement floating rate logic:
    # - Add rate index lookup/time series (e.g., SOFR curve)
    # - Add rate caps/floors
    # - Add rate reset frequency (e.g., monthly, quarterly)
    # - Support forward curves and rate scenarios


class InterestRate(Model):
    """Base class for interest rates"""

    rate_type: InterestRateType
    base_rate: FloatBetween0And1
    spread: Optional[FloatBetween0And1] = Field(
        None, description="Spread over base rate for floating rates"
    )
    # TODO: Add fields for floating rate configuration:
    # - rate_index (e.g., SOFR, LIBOR)
    # - reset_frequency
    # - rate_cap
    # - rate_floor
    # TODO: Add fields for interest calculation conventions:
    # - day_count_convention (e.g., 30/360, Actual/365)
    # - payment_frequency
    # - accrual_method

    @model_validator(mode="after")
    def validate_spread_for_floating(self) -> "InterestRate":
        """Ensure spread is provided for floating rates"""
        if self.rate_type == InterestRateType.FLOATING and self.spread is None:
            raise ValueError("Spread must be provided for floating rate loans")
        return self

    @property
    def effective_rate(self) -> FloatBetween0And1:
        """Calculate effective interest rate"""
        if self.rate_type == InterestRateType.FIXED:
            return self.base_rate
        return self.base_rate + (self.spread or 0.0)
