"""
Performa Valuation Module

Universal property valuation methods that work across all asset types
and development scenarios. Supports multiple valuation approaches.
"""

from typing import Union

from pydantic import Field

from .dcf import DCFValuation
from .direct_cap import DirectCapValuation
from .metrics import PropertyMetrics
from .reversion import ReversionValuation
from .sales_comp import SalesComparable, SalesCompValuation

# Polymorphic union type for all valuation models
AnyValuation = Union[
    DCFValuation,
    DirectCapValuation,
    ReversionValuation, 
    SalesCompValuation
]

__all__ = [
    # Core valuation methods
    "DCFValuation",
    "DirectCapValuation", 
    "ReversionValuation",
    "SalesCompValuation",
    "SalesComparable",
    # Universal metrics
    "PropertyMetrics",
    # Polymorphic union
    "AnyValuation",
]
