from __future__ import annotations

from ..primitives._enums import ProgramUseEnum
from ..primitives._model import Model
from ..primitives._types import PositiveFloat


class ProgramComponentSpec(Model):
    """
    Defines a component within a mixed-use property.
    """

    program_use: ProgramUseEnum
    area: PositiveFloat
    identifier: str  # e.g., "Office Tower A", "Retail Podium" 