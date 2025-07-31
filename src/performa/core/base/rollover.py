# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, field_validator

from ..primitives.enums import FrequencyEnum, UponExpirationEnum
from ..primitives.cash_flow import ReferenceKey
from ..primitives.growth_rates import GrowthRate
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1, PositiveFloat, PositiveInt
from ..primitives.validation import validate_monthly_period_index
from .cost import LeasingCommissionBase, TenantImprovementAllowanceBase
from .lease_components import RentAbatementBase, RentEscalationBase
from .recovery import RecoveryMethodBase


class RolloverLeaseTermsBase(Model):
    """
    Base class for lease terms applied in different rollover scenarios.
    """
    term_months: Optional[PositiveInt] = None
    market_rent: Optional[Union[PositiveFloat, pd.Series, Dict, List]] = None
    reference: Optional[ReferenceKey] = None  # For per-unit calculations
    frequency: FrequencyEnum = FrequencyEnum.ANNUAL
    growth_rate: Optional[GrowthRate] = None
    rent_escalation: Optional[RentEscalationBase] = None
    rent_abatement: Optional[RentAbatementBase] = None
    recovery_method: Optional[RecoveryMethodBase] = None
    ti_allowance: Optional[TenantImprovementAllowanceBase] = None
    leasing_commission: Optional[LeasingCommissionBase] = None
    
    @field_validator("market_rent")
    @classmethod
    def validate_market_rent(cls, v: Optional[Union[PositiveFloat, pd.Series, Dict, List]]) -> Optional[Union[PositiveFloat, pd.Series, Dict, List]]:
        """Validate market rent format and constraints."""
        if v is None:
            return v
            
        if isinstance(v, pd.Series):
            # Validate monthly PeriodIndex
            validate_monthly_period_index(v, field_name="market_rent")
            
            # Ensure all values are non-negative
            if not pd.api.types.is_numeric_dtype(v.dtype):
                raise ValueError("Market rent Series must have numeric values")
            if (v < 0).any():
                raise ValueError("All market rent values in Series must be non-negative")
        elif isinstance(v, dict):
            # Validate dict values are non-negative
            for key, val in v.items():
                if not isinstance(val, (int, float)) or val < 0:
                    raise ValueError(f"Dict value for {key} must be non-negative, got {val}")
        elif isinstance(v, list):
            # Validate list values are non-negative
            for i, val in enumerate(v):
                if not isinstance(val, (int, float)) or val < 0:
                    raise ValueError(f"List value at index {i} must be non-negative, got {val}")
        elif isinstance(v, (int, float)):
            if v < 0:
                raise ValueError(f"Market rent must be non-negative, got {v}")
        else:
            raise TypeError(f"Market rent must be a positive number, Series, Dict, or List, got {type(v)}")
        
        return v


class RolloverProfileBase(Model):
    """
    Base class for a comprehensive profile for lease rollovers and renewals.
    """
    uid: UUID = Field(default_factory=uuid4, description="Unique identifier for this rollover profile")
    name: str
    term_months: PositiveInt
    renewal_probability: FloatBetween0And1
    downtime_months: int
    market_terms: RolloverLeaseTermsBase
    renewal_terms: RolloverLeaseTermsBase
    option_terms: Optional[RolloverLeaseTermsBase] = None
    upon_expiration: UponExpirationEnum = UponExpirationEnum.MARKET
    next_profile: Optional[str] = None 