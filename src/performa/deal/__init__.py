"""
Performa Deal Models
Public API for the performa.deal subpackage.

This module contains models for deal-level components that span across
property lifecycle phases, including acquisition, disposition, and
deal-level financial structuring.
"""

from .acquisition import AcquisitionTerms
from .calculator import analyze_deal
from .deal import Deal

__all__ = [
    "AcquisitionTerms",
    "Deal",
    "analyze_deal",
] 