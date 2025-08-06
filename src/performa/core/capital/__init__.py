# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Capital planning system for Performa.

This module provides flexible capital expenditure modeling with factory methods
for common renovation patterns. Built on the CashFlowModel foundation for
seamless integration with existing analysis workflows.
"""

from .plan import CapitalItem, CapitalPlan

__all__ = [
    "CapitalItem",
    "CapitalPlan",
]
