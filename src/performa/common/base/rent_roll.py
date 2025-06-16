from __future__ import annotations

from ..primitives.enums import ProgramUseEnum
from ..primitives.model import Model
from ..primitives.types import PositiveFloat


class VacantSuiteBase(Model):
    """
    Base model representing a vacant suite available for lease-up.
    """
    suite: str
    floor: str
    area: PositiveFloat
    use_type: ProgramUseEnum
