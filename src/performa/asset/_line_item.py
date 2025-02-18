from typing import Literal, Optional

from ..utils._model import Model
from ..utils._types import FloatBetween0And1, PositiveFloat
from ._enums import UnitOfMeasureEnum
from ._growth import GrowthRates


class LineItem(Model):
    """Base model for any income/expense line item"""

    type: str
    description: str
    account: str
    amount: PositiveFloat
    unit_of_measure: UnitOfMeasureEnum
    frequency: Literal["monthly", "yearly"]
    area: Optional[PositiveFloat]
    growth_rate: GrowthRates | PositiveFloat
    is_variable: bool = False
    percent_variable: Optional[FloatBetween0And1] = None
