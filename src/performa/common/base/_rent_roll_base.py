from __future__ import annotations

from ..primitives._enums import ProgramUseEnum
from ..primitives._model import Model
from ..primitives._types import PositiveFloat


class VacantSuiteBase(Model):
    """
    Base model representing a vacant suite available for lease-up.
    """
    suite: str
    floor: str
    area: PositiveFloat
    use_type: ProgramUseEnum
