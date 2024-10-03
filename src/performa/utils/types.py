from typing import Annotated

from pydantic import Field

from .money import Money

# constrained types
PositiveInt = Annotated[int, Field(strict=True, ge=0)]
PositiveIntGt1 = Annotated[int, Field(strict=True, gt=1)]
PositiveFloat = Annotated[float, Field(strict=True, ge=0)]
FloatBetween0And1 = Annotated[float, Field(strict=True, ge=0, le=1)]
PositiveMoney = Annotated[Money, Field(strict=True, ge=0)]
NegativeMoney = Annotated[Money, Field(strict=True, lt=0)]
