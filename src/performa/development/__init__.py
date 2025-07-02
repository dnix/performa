# Copyright 2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Development Module - Institutional Development Modeling Engine

This module provides institutional-grade development modeling capabilities
for the Performa real estate financial modeling framework.

Key Components:
- DevelopmentProject: Complete project specification container (now with polymorphic blueprints)
- DevelopmentAnalysisScenario: Lifecycle assembler and analysis engine
- AnyDevelopmentBlueprint: Polymorphic union type for development blueprints
- DispositionCashFlow: Exit strategy cash flow modeling

Design Pattern:
This module uses the "Asset Factory" pattern where development blueprints
(OfficeDevelopmentBlueprint, ResidentialDevelopmentBlueprint) create stabilized
assets rather than becoming assets themselves.
"""

from .analysis import DevelopmentAnalysisScenario
from .project import AnyDevelopmentBlueprint, DevelopmentProject

__all__ = [
    "DevelopmentProject",
    "AnyDevelopmentBlueprint",
    "DevelopmentAnalysisScenario",
]
