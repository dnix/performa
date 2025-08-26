# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Deal Patterns

High-level functions that assemble complete Deal objects for immediate analysis.

Patterns compose primitives and constructs across asset, debt, and deal
modules to create full, end-to-end investment archetypes.
"""

from __future__ import annotations

from .acquisition import create_stabilized_acquisition_deal
from .base import DevelopmentPatternBase, PatternBase
from .development import create_development_deal
from .office_development import OfficeDevelopmentPattern
from .stabilized_acquisition import StabilizedAcquisitionPattern
from .value_add_acquisition import ValueAddAcquisitionPattern

__all__ = [
    # Base classes
    "PatternBase",
    "DevelopmentPatternBase",
    # Asset-specific development patterns (RECOMMENDED)
    "OfficeDevelopmentPattern",
    # TODO: Add ResidentialDevelopmentPattern when implemented
    # General patterns
    "StabilizedAcquisitionPattern",
    "ValueAddAcquisitionPattern",
    # Legacy functions (will be deprecated)
    "create_stabilized_acquisition_deal",
    "create_development_deal",
]
