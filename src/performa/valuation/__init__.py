# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Valuation Module - Industry Standard Approaches

Three standard real estate valuation methods:
1. Income Approach (DirectCap) - NOI/Cap Rate  
2. Sales Comparison Approach (SalesComps) - Comparable analysis
3. Cost/Manual Approach (DirectEntry) - Manual pricing

Follows industry standards used in Argus Enterprise and Rockport Val.
"""

from typing import Union

from .base.valuation import BaseValuation
from .direct_cap import DirectCapValuation
from .direct_entry import DirectEntry
from .helpers import AssetValuation
from .metrics import PropertyMetrics
from .sales_comp import SalesComparable, SalesCompValuation

# Polymorphic union type for all valuation models  
AnyValuation = Union[DirectCapValuation, DirectEntry, SalesCompValuation]

__all__ = [
    # Base class
    "BaseValuation",
    # Three standard valuation approaches
    "DirectCapValuation",  # Income approach
    "DirectEntry",         # Cost/manual approach
    "SalesCompValuation",  # Sales comparison approach
    "SalesComparable",
    # Helpers and utilities
    "AssetValuation", 
    "PropertyMetrics",
    # Type unions
    "AnyValuation",
]
