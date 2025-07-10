"""
Performa Deal Models
Public API for the performa.deal subpackage.

This module contains models for deal-level components that span across
property lifecycle phases, including acquisition, disposition, and
deal-level financial structuring.
"""

from .acquisition import AcquisitionTerms
from .api import analyze
from .deal import Deal
from .distribution_calculator import (
    DistributionCalculator,
    calculate_partner_distributions_with_structure,
    create_simple_partnership,
)
from .fees import DealFee
from .orchestrator import DealCalculator
from .partners import (
    CarryPromote,
    Partner,
    PartnershipStructure,
    PromoteStructure,
    WaterfallPromote,
    WaterfallTier,
)
from .results import DealAnalysisResult

__all__ = [
    # Core deal components
    "Deal",
    "AcquisitionTerms",
    "DealFee",
    
    # Analysis API
    "analyze",
    "DealAnalysisResult",
    "DealCalculator",
    
    # Partnership structures
    "Partner",
    "PartnershipStructure",
    "WaterfallTier",
    "WaterfallPromote",
    "CarryPromote",
    "PromoteStructure",
    
    # Distribution calculations
    "DistributionCalculator",
    "calculate_partner_distributions_with_structure",
    "create_simple_partnership",
] 