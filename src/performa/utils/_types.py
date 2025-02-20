from typing import Annotated, Tuple

from pydantic import Field

# constrained types
PositiveInt = Annotated[int, Field(strict=True, ge=0)]
PositiveIntGt1 = Annotated[int, Field(strict=True, gt=1)]
PositiveFloat = Annotated[float, Field(strict=True, ge=0)]
FloatBetween0And1 = Annotated[float, Field(strict=True, ge=0, le=1)]

SquareFootRange = Tuple[PositiveFloat, PositiveFloat]
