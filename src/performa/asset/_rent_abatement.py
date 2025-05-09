from __future__ import annotations

from ..core._model import Model
from ..core._types import FloatBetween0And1


class RentAbatement(Model):
    """
    Structured rent abatement (free rent) periods.

    Attributes:
        months: Duration of free rent
        includes_recoveries: Whether recoveries are also abated
        start_month: When free rent begins (relative to lease start)
        abated_ratio: Portion of rent that is abated
    """

    months: int
    includes_recoveries: bool = False
    start_month: int = 1
    abated_ratio: FloatBetween0And1 = 1.0
