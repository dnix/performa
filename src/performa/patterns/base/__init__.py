# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Base classes for deal patterns.

This module contains the abstract base classes that provide common functionality
for all deal patterns in Performa.
"""

from .development_base import DevelopmentPatternBase
from .pattern_base import PatternBase

__all__ = [
    "PatternBase",
    "DevelopmentPatternBase",
]
