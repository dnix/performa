# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ..primitives.enums import ProgramUseEnum
from ..primitives.model import Model
from ..primitives.types import PositiveFloat


class ProgramComponentSpec(Model):
    """
    Defines a component within a mixed-use property.
    """

    program_use: ProgramUseEnum
    area: PositiveFloat
    identifier: str  # e.g., "Office Tower A", "Retail Podium" 