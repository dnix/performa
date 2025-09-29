# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Compatibility shim for legacy imports.

This module maintains backward compatibility by re-exporting the active 
backend Ledger class. All new code should import from the main __init__.py.
"""

# Re-export the active backend Ledger
from . import Ledger

__all__ = ["Ledger"]
