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
from .distribution_calculator import (
    DistributionCalculator,
    calculate_partner_distributions_with_structure,
    create_simple_partnership,
)
from .fees import DealFee
from .partners import (
    CarryPromote,
    Partner,
    PartnershipStructure,
    PromoteStructure,
    WaterfallPromote,
    WaterfallTier,
)

__all__ = [
    "AcquisitionTerms",
    "Deal",
    "analyze_deal",
    "DealFee",
    "Partner",
    "PartnershipStructure",
    "WaterfallTier",
    "WaterfallPromote",
    "CarryPromote",
    "PromoteStructure",

    "DistributionCalculator",
    "calculate_partner_distributions_with_structure",
    "create_simple_partnership",
] 