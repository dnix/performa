# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Deal Patterns

High-level functions that assemble complete Deal objects for immediate analysis.

Patterns compose primitives and constructs across asset, debt, and deal
modules to create full, end-to-end investment archetypes.
"""

from __future__ import annotations

from .base import DevelopmentPatternBase, PatternBase
from .office_development import OfficeDevelopmentPattern
from .office_stabilized_acquisition import OfficeStabilizedAcquisitionPattern
from .residential_development import ResidentialDevelopmentPattern
from .stabilized_acquisition import StabilizedAcquisitionPattern
from .value_add_acquisition import ValueAddAcquisitionPattern

__all__ = [
    # Base classes
    "PatternBase",
    "DevelopmentPatternBase",
    # Asset-specific development patterns
    "OfficeDevelopmentPattern",
    "ResidentialDevelopmentPattern",
    # Asset-specific acquisition patterns
    "OfficeStabilizedAcquisitionPattern",
    "StabilizedAcquisitionPattern",  # Residential only
    # General patterns
    "ValueAddAcquisitionPattern",
]
