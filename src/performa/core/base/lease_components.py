# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Basic lease components that can be used throughout the base modules without circular dependencies.

This module contains fundamental lease-related classes that don't depend on other base modules,
allowing them to be imported safely by recovery.py, rollover.py, and lease.py.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Dict, Literal, Optional, Union

import pandas as pd
from pydantic import field_validator, model_validator

from ..primitives.enums import UnitOfMeasureEnum
from ..primitives.growth_rates import FixedGrowthRate, PercentageGrowthRate
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1, PositiveFloat, PositiveInt

if TYPE_CHECKING:
    pass


class RentEscalationBase(Model):
    """
    Base class for rent escalation mechanisms.
    
    Defines how rent increases over time, supporting various escalation types:
    - Fixed amount increases 
    - Percentage-based increases
    
    Timing can be specified as either:
    - Absolute: start_date (specific date)
    - Relative: start_month (months from lease start, consistent with RentAbatement)
    
    The rate field can be:
    - A simple float value for basic cases
    - A PercentageGrowthRate object for complex percentage scenarios  
    - A FixedGrowthRate object for complex fixed dollar scenarios
    """
    type: Literal["fixed", "percentage"]
    rate: Union[PositiveFloat, PercentageGrowthRate, FixedGrowthRate]
    unit_of_measure: UnitOfMeasureEnum
    is_relative: bool
    
    # Timing: exactly one must be provided
    start_date: Optional[date] = None
    start_month: Optional[PositiveInt] = None
    
    recurring: bool = False
    frequency_months: Optional[PositiveInt] = None

    @model_validator(mode='after')
    def validate_timing(self) -> 'RentEscalationBase':
        """Ensure exactly one timing method is provided"""
        # FIXME: consider using reusable validator?
        has_date = self.start_date is not None
        has_month = self.start_month is not None
        
        if not (has_date or has_month):
            raise ValueError("Either start_date or start_month must be provided")
        if has_date and has_month:
            raise ValueError("Cannot provide both start_date and start_month")
            
        return self

    @field_validator('rate')
    @classmethod
    def validate_rate_type_consistency(cls, v, info):
        """Validate that rate type is consistent with escalation type"""
        escalation_type = info.data.get('type')
        
        if escalation_type == 'percentage':
            # For percentage escalations, allow simple float (0-1) or PercentageGrowthRate
            if isinstance(v, (int, float)):
                if not (0 <= v <= 1):
                    raise ValueError(f"Percentage escalation rate must be between 0 and 1, got {v}")
            elif hasattr(v, '__class__') and 'PercentageGrowthRate' in str(v.__class__):
                pass  # PercentageGrowthRate is valid
            elif hasattr(v, '__class__') and 'FixedGrowthRate' in str(v.__class__):
                raise ValueError("Cannot use FixedGrowthRate with percentage escalation type")
            
        elif escalation_type == 'fixed':
            # For fixed escalations, allow non-negative float or FixedGrowthRate (consistent with PositiveFloat)
            if isinstance(v, (int, float)):
                if v < 0:
                    raise ValueError(f"Fixed escalation rate must be non-negative, got {v}")
            elif hasattr(v, '__class__') and 'FixedGrowthRate' in str(v.__class__):
                pass  # FixedGrowthRate is valid
            elif hasattr(v, '__class__') and 'PercentageGrowthRate' in str(v.__class__):
                raise ValueError("Cannot use PercentageGrowthRate with fixed escalation type")
        
        return v

    @property
    def uses_rate_object(self) -> bool:
        """Check if this escalation uses a rate object instead of simple float"""
        return not isinstance(self.rate, (int, float))

    @property 
    def rate_object(self) -> Optional[Union[PercentageGrowthRate, FixedGrowthRate]]:
        """Get the rate object if one is used"""
        if self.uses_rate_object:
            return self.rate
        return None

    @property
    def rate_value(self) -> float:
        """Get the simple rate value (for basic cases)"""
        if isinstance(self.rate, (int, float)):
            return self.rate
        else:
            raise ValueError("Cannot get simple rate value from rate object - use rate_object property")

    def get_start_period(self, lease_start_period: pd.Period) -> pd.Period:
        """
        Get the escalation start period for a given lease start.
        
        Args:
            lease_start_period: The lease start period (pd.Period)
            
        Returns:
            The period when this escalation should begin
        """
        if self.start_date is not None:
            return pd.Period(self.start_date, freq="M")
        elif self.start_month is not None:
            # start_month is 1-indexed (1 = first month of lease)
            return lease_start_period + (self.start_month - 1)
        else:
            raise ValueError("No start timing defined")


class RentAbatementBase(Model):
    """
    Base class for rent abatement (free rent) periods.
    
    Defines periods where rent is reduced or waived entirely,
    commonly used in lease incentive packages.
    """
    months: int
    includes_recoveries: bool = False
    start_month: int = 1
    abated_ratio: FloatBetween0And1 = 1.0


class TenantBase(Model):
    """
    Base class for tenant information and characteristics.
    
    This is a placeholder for future tenant-specific data like
    creditworthiness, industry type, or special lease terms.
    """
    pass 