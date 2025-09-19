# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Deal Models
Public API for the performa.deal subpackage.

This module contains models for deal-level components that span across
property lifecycle phases, including acquisition, disposition, and
deal-level financial structuring.
"""

from .acquisition import AcquisitionTerms
from .api import analyze
from .constructs import (
    create_gp_lp_waterfall,
    create_institutional_waterfall_from_capital,
    create_partnership_from_capital,
    create_simple_capital_partnership,
    create_simple_partnership,
)
from .deal import Deal
from .distribution_calculator import (
    DistributionCalculator,
    calculate_partner_distributions_with_structure,
)
from .entities import Entity, Partner, ThirdParty
from .fees import DealFee
from .orchestrator import DealCalculator, DealContext
from .partnership import (
    CarryPromote,
    PartnershipStructure,
    PromoteStructure,
    WaterfallPromote,
    WaterfallTier,
)
from .results import DealResults

__all__ = [
    # Core deal components
    "Deal",
    "AcquisitionTerms",
    "DealFee",
    # Analysis API
    "analyze",
    "DealResults",
    "DealCalculator",
    "DealContext",
    # Partnership structures
    "Entity",
    "Partner",
    "ThirdParty",
    "PartnershipStructure",
    "WaterfallTier",
    "WaterfallPromote",
    "CarryPromote",
    "PromoteStructure",
    # Constructs
    "create_gp_lp_waterfall",
    "create_simple_partnership",
    # Capital-based constructs (pro-rata ownership)
    "create_partnership_from_capital",
    "create_simple_capital_partnership",
    "create_institutional_waterfall_from_capital",
    # Distribution calculations
    "DistributionCalculator",
    "calculate_partner_distributions_with_structure",
]
