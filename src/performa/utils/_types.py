from typing import Annotated

from pydantic import Field

from ._decimal import DecimalExtensionArray

# constrained types
PositiveInt = Annotated[int, Field(strict=True, ge=0)]
PositiveIntGt1 = Annotated[int, Field(strict=True, gt=1)]
PositiveFloat = Annotated[float, Field(strict=True, ge=0)]
FloatBetween0And1 = Annotated[float, Field(strict=True, ge=0, le=1)]
PositiveDecimal = Annotated[DecimalExtensionArray, Field(strict=True, ge=0)]
NegativeDecimal = Annotated[DecimalExtensionArray, Field(strict=True, lt=0)]
