# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Asset Models

Real estate asset modeling capabilities across all major property types.
Each asset module implements property-specific modeling logic.
"""

from . import office, residential

# from . import retail # To be uncommented when implemented
# from . import industrial
# from . import hotel

__all__ = [
    "office",
    "residential",
    # "retail",
    # "industrial",
    # "hotel",
    # etc.
]
