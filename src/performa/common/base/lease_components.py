"""
Basic lease components that can be used throughout the base modules without circular dependencies.

This module contains fundamental lease-related classes that don't depend on other base modules,
allowing them to be imported safely by recovery.py, rollover.py, and lease.py.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from ..primitives.enums import UnitOfMeasureEnum
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1, PositiveFloat


class RentEscalationBase(Model):
    """
    Base class for rent escalation mechanisms.
    
    Defines how rent increases over time, supporting various escalation types:
    - Fixed amount increases 
    - Percentage-based increases
    - CPI-linked increases
    """
    type: Literal["fixed", "percentage", "cpi"]
    amount: PositiveFloat
    unit_of_measure: UnitOfMeasureEnum
    is_relative: bool
    start_date: date
    recurring: bool = False
    frequency_months: Optional[int] = None


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