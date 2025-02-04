from enum import Enum
from typing import List, Optional

import pandas as pd
from pydantic import Field, model_validator

from ..utils._types import FloatBetween0And1, PositiveFloat, PositiveInt
from ._model import Model

#############################
######### FINANCING #########
#############################

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
        None, 
        description="Spread over base rate for floating rates"
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
    
    @model_validator(mode='after')
    def validate_spread_for_floating(self) -> 'InterestRate':
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


class DebtTranche(Model):
    """
    Class representing a single debt tranche in a financing structure.
    
    Attributes:
        name (str): Tranche name (e.g. 'Senior', 'Mezzanine 1')
        interest_rate (InterestRate): Interest rate configuration
        fee_rate (FloatBetween0And1): Upfront fee as percentage of tranche amount
        ltc_threshold (FloatBetween0And1): Maximum LTC for this tranche, used for stacking
        
    Example:
        >>> senior = DebtTranche(
        ...     name="Senior",
        ...     interest_rate=InterestRate(
        ...         rate_type=InterestRateType.FLOATING,
        ...         base_rate=0.05,
        ...         spread=0.03
        ...     ),
        ...     fee_rate=0.01,
        ...     ltc_threshold=0.45
        ... )
    """
    name: str = Field(..., description="Tranche name (e.g. 'Senior', 'Mezzanine 1')")
    interest_rate: InterestRate
    fee_rate: FloatBetween0And1
    ltc_threshold: FloatBetween0And1 = Field(
        ..., 
        description="Maximum LTC for this tranche"
    )
    # TODO: add commitment_fee_rate for undrawn amounts
    # TODO: add interest rate caps/floors
    # TODO: add PIK interest toggle
    # TODO: add DSCR covenant threshold
    
    def __lt__(self, other: 'DebtTranche') -> bool:
        """Compare tranches by LTC threshold for sorting"""
        return self.ltc_threshold < other.ltc_threshold


class ConstructionFinancing(Model):
    """
    Class for construction financing with multiple debt tranches.
    
    Manages the stacking and interaction of multiple debt tranches during construction.
    Tranches are ordered by seniority based on their LTC thresholds.
    
    Attributes:
        tranches (List[DebtTranche]): List of debt tranches, ordered by seniority
        
    Properties:
        max_ltc (FloatBetween0And1): Maximum total LTC across all tranches
        
    Methods:
        calculate_tranche_amounts: Calculate maximum amounts for each tranche
        calculate_interest: Calculate period interest for drawn amounts
        calculate_fees: Calculate upfront fees for each tranche
        
    Example:
        >>> construction_financing = ConstructionFinancing(
        ...     tranches=[
        ...         DebtTranche(name="Senior", ltc_threshold=0.45, ...),
        ...         DebtTranche(name="Mezzanine", ltc_threshold=0.60, ...)
        ...     ]
        ... )
    """
    tranches: List[DebtTranche] = Field(
        ...,
        description="List of debt tranches, ordered by seniority (LTC threshold)"
    )
    # TODO: field for draw order logic (sequential vs simultaneous with senior debt) per intercreditor agreement
    
    @model_validator(mode='after')
    def sort_and_validate_tranches(self) -> 'ConstructionFinancing':
        """
        Sort tranches by LTC threshold and validate stacking.
        
        Validates:
        - Tranches are properly stacked (increasing LTC thresholds)
        - No tranche exceeds 100% LTC
        - No gaps in the capital stack
        """
        # Sort tranches by LTC threshold
        self.tranches.sort()
        
        # Validate LTC thresholds are increasing and <= 1
        previous_ltc = 0.0
        for tranche in self.tranches:
            if tranche.ltc_threshold <= previous_ltc:
                raise ValueError(
                    f"Tranche {tranche.name} LTC threshold must be greater than "
                    f"previous tranche threshold of {previous_ltc}"
                )
            if tranche.ltc_threshold > 1.0:
                raise ValueError(
                    f"Tranche {tranche.name} LTC threshold cannot exceed 1.0"
                )
            previous_ltc = tranche.ltc_threshold
            
        return self
    
    @property
    def max_ltc(self) -> FloatBetween0And1:
        """Maximum total LTC across all tranches"""
        return max(tranche.ltc_threshold for tranche in self.tranches)
    
    def calculate_tranche_amounts(self, total_cost: PositiveFloat) -> pd.Series:
        """
        Calculate the maximum amount available for each tranche based on total cost
        
        Args:
            total_cost: Total project cost
            
        Returns:
            pd.Series with tranche names as index and maximum amounts as values
        """
        amounts = {}
        previous_ltc = 0.0
        
        for tranche in self.tranches:
            tranche_ltc = tranche.ltc_threshold - previous_ltc
            amounts[tranche.name] = total_cost * tranche_ltc
            previous_ltc = tranche.ltc_threshold
            
        return pd.Series(amounts)
    
    def calculate_interest(
        self, 
        drawn_amounts: dict[str, float],
        period_start: pd.Period,  # Keep for future floating rate implementation
    ) -> pd.Series:
        """
        Calculate interest for each tranche based on drawn amounts
        
        Args:
            drawn_amounts: Dictionary mapping tranche names to drawn amounts
            period_start: Start of interest period (used for floating rates)
            
        Returns:
            pd.Series with tranche names as index and interest amounts as values
        """
        # Use simple monthly interest (annual rate / 12) for consistency
        rates = pd.Series({
            tranche.name: tranche.interest_rate.effective_rate / 12
            for tranche in self.tranches
        })
        amounts = pd.Series(drawn_amounts)
        
        return amounts * rates
    
    def calculate_fees(self, tranche_amounts: pd.Series) -> pd.Series:
        """
        Calculate upfront fees for each tranche
        
        Args:
            tranche_amounts: Series with tranche names as index and amounts as values
            
        Returns:
            pd.Series with tranche names as index and fee amounts as values
        """
        fee_rates = pd.Series({
            tranche.name: tranche.fee_rate 
            for tranche in self.tranches
        })
        return tranche_amounts * fee_rates[tranche_amounts.index]


class PermanentFinancing(Model):
    """Class for permanent financing"""
    interest_rate: InterestRate = Field(
        ...,
        description="Interest rate configuration"
    )
    fee_rate: FloatBetween0And1 = Field(
        ...,
        description="Upfront fee rate as percentage of loan amount"
    )
    ltv_ratio: FloatBetween0And1 = Field(
        default=0.75,
        description="Loan-to-value ratio"
    )
    amortization: PositiveInt = Field(
        default=30,
        description="Amortization term in years"
    )
    # FIXME: more permanent financing amortization here from _project.py
