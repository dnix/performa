"""
Performa Deal Models
Public API for the performa.deal subpackage.

This module contains models for deal-level components that span across
property lifecycle phases, including acquisition, disposition, and
deal-level financial structuring.
"""

from .acquisition import AcquisitionTerms

__all__ = [
    "AcquisitionTerms",
] 