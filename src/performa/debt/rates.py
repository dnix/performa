# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""Interest rate models for debt facilities"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Union

import pandas as pd
from pydantic import Field, model_validator
from typing_extensions import Annotated

from ..core.primitives import FloatBetween0And1, Model, PositiveFloat


class RateIndexEnum(str, Enum):
    """Common benchmark interest rate indices used in commercial real estate financing."""
    
    SOFR_30_DAY_AVG = "SOFR 30-Day Average"
    SOFR_90_DAY_AVG = "SOFR 90-Day Average"
    PRIME = "Prime Rate"
    # Legacy indices (rarely used in new deals but may exist in older loans)
    LIBOR_1M = "1-Month LIBOR"
    LIBOR_3M = "3-Month LIBOR"


class FixedRate(Model):
    """
    A simple fixed interest rate for debt facilities.
    
    Used for permanent loans and construction loans where the rate 
    is locked for the entire term.
    
    Attributes:
        rate_type: Always "fixed" for this rate type
        rate: The fixed annual interest rate as a decimal
        
    Example:
        >>> fixed_rate = FixedRate(rate=0.065)  # 6.5% fixed
        >>> assert fixed_rate.rate_type == "fixed"
        >>> assert fixed_rate.rate == 0.065
    """
    
    rate_type: Literal["fixed"] = "fixed"
    rate: FloatBetween0And1 = Field(
        ..., 
        description="The fixed annual interest rate as a decimal (e.g., 0.065 for 6.5%)"
    )


class FloatingRate(Model):
    """
    Institutional-grade floating interest rate structure.
    
    Defines a complete floating rate specification including base index,
    spread, caps, floors, and reset frequency. This captures the standard
    structure of commercial real estate floating rate debt.
    
    Attributes:
        rate_type: Always "floating" for this rate type
        rate_index: The benchmark index (e.g., SOFR)
        spread: The fixed spread over the index in decimal form
        reset_frequency: How often the rate adjusts
        interest_rate_cap: Optional ceiling on total rate
        interest_rate_floor: Optional floor on total rate
        
    Example:
        >>> floating_rate = FloatingRate(
        ...     rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
        ...     spread=0.0275,  # 275 bps
        ...     interest_rate_cap=0.08,  # 8% cap
        ... )
        >>> assert floating_rate.rate_type == "floating"
    """
    
    rate_type: Literal["floating"] = "floating"
    rate_index: RateIndexEnum = Field(
        ..., 
        description="The benchmark index (e.g., SOFR 30-Day Average)"
    )
    spread: FloatBetween0And1 = Field(
        ..., 
        description="The fixed spread over the rate index in decimal form (e.g., 0.0275 for 275 bps)"
    )
    
    reset_frequency: Literal["monthly", "quarterly", "semi-annually", "annually"] = Field(
        default="monthly", 
        description="How often the rate adjusts to current index levels"
    )
    
    # Rate hedging components
    interest_rate_cap: Optional[PositiveFloat] = Field(
        default=None, 
        description="A ceiling on the total effective interest rate (index + spread)"
    )
    interest_rate_floor: Optional[PositiveFloat] = Field(
        default=None, 
        description="A floor on the total effective interest rate (index + spread)"
    )


# The discriminated union for any rate type
AnyRateStructure = Annotated[
    Union[FixedRate, FloatingRate],
    Field(discriminator="rate_type")
]


class InterestRate(Model):
    """
    Unified interface for both fixed and floating interest rates.
    
    This class provides a single interface for working with different rate types,
    handling the complexity of floating rate calculations including index lookups,
    caps, floors, and reset frequencies.
    
    The key method is get_rate_for_period() which returns the effective rate
    for any given period, handling all the floating rate mechanics internally.
    
    Attributes:
        details: The specific rate structure (FixedRate or FloatingRate)
        
    Example:
        >>> # Fixed rate example
        >>> fixed_rate = InterestRate(
        ...     details=FixedRate(rate=0.065)
        ... )
        >>> rate = fixed_rate.get_rate_for_period(pd.Period("2024-01", freq="M"))
        >>> assert rate == 0.065
        
        >>> # Floating rate example
        >>> floating_rate = InterestRate(
        ...     details=FloatingRate(
        ...         rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
        ...         spread=0.0275,
        ...         interest_rate_cap=0.08
        ...     )
        ... )
        >>> # Requires index curve for floating rates
        >>> sofr_curve = pd.Series([0.045, 0.048, 0.050], 
        ...                       index=pd.period_range("2024-01", periods=3, freq="M"))
        >>> rate = floating_rate.get_rate_for_period(
        ...     pd.Period("2024-01", freq="M"), 
        ...     sofr_curve
        ... )
        >>> assert rate == 0.0725  # 4.5% SOFR + 275 bps
    """
    
    details: AnyRateStructure

    def get_rate_for_period(
        self, 
        period: pd.Period, 
        index_curve: Optional[pd.Series] = None
    ) -> float:
        """
        Calculate the effective interest rate for a specific period.
        
        This is the primary method used by amortization engines and deal
        calculators to get the actual rate for any given period.
        
        For fixed rates, simply returns the fixed rate.
        For floating rates, looks up the index value, adds the spread,
        and applies caps/floors as needed.
        
        Args:
            period: The period (month) for which to calculate the rate
            index_curve: pandas Series with PeriodIndex containing the values
                        for the floating rate index. Required for floating rates.
                        
        Returns:
            The effective annual interest rate for that period as a decimal
            
        Raises:
            ValueError: If index_curve is not provided for floating rates
            KeyError: If the period is not found in the index_curve
        """
        if self.details.rate_type == 'fixed':
            return self.details.rate

        # --- Floating Rate Logic ---
        if index_curve is None:
            raise ValueError(
                f"An 'index_curve' must be provided for floating rate calculations "
                f"using {self.details.rate_index}"
            )
            
        # Get the index rate for the current period
        # Use forward fill for missing values to handle gaps in data
        try:
            if period in index_curve.index:
                index_rate = index_curve.loc[period]
            else:
                # Forward fill from the most recent available data
                available_periods = index_curve.index[index_curve.index <= period]
                if len(available_periods) == 0:
                    raise KeyError(f"No index data available for period {period} or earlier")
                latest_period = available_periods[-1]
                index_rate = index_curve.loc[latest_period]
        except (KeyError, IndexError) as e:
            raise KeyError(
                f"Index rate for {self.details.rate_index} not found for period {period}. "
                f"Available periods: {list(index_curve.index)}"
            ) from e
        
        # Calculate effective rate
        effective_rate = index_rate + self.details.spread
        
        # Apply floor first, then cap (standard market practice)
        if self.details.interest_rate_floor is not None:
            effective_rate = max(effective_rate, self.details.interest_rate_floor)
        if self.details.interest_rate_cap is not None:
            effective_rate = min(effective_rate, self.details.interest_rate_cap)
            
        return effective_rate

    @property
    def effective_rate(self) -> float:
        """
        Get the effective rate for fixed rates, or base calculation for floating rates.
        
        For fixed rates, returns the fixed rate.
        For floating rates, returns spread only (since index varies over time).
        
        Note: For floating rates, use get_rate_for_period() with actual index data
        for accurate calculations.
        
        Returns:
            Effective rate for fixed rates, or spread for floating rates
        """
        if self.details.rate_type == 'fixed':
            return self.details.rate
        else:
            # For floating rates, can only return the spread component
            # since the index varies over time
            return self.details.spread

    def __str__(self) -> str:
        """String representation of the interest rate."""
        if self.details.rate_type == 'fixed':
            return f"Fixed {self.details.rate:.3%}"
        else:
            cap_str = f" (cap: {self.details.interest_rate_cap:.3%})" if self.details.interest_rate_cap else ""
            floor_str = f" (floor: {self.details.interest_rate_floor:.3%})" if self.details.interest_rate_floor else ""
            return f"{self.details.rate_index} + {self.details.spread:.3%}{cap_str}{floor_str}"


# Backward compatibility aliases
InterestRateType = RateIndexEnum  # For any code that might reference the old enum
