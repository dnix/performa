"""Common types used across debt module"""

from typing import Union

from pydantic import Field
from typing_extensions import Annotated

from .construction import ConstructionFacility
from .permanent import PermanentFacility

# Common type definitions
AnyDebtFacility = Annotated[
    Union[ConstructionFacility, PermanentFacility], Field(discriminator="kind")
]
