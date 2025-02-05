"""Common types used across debt module"""

from typing import Union

from pydantic import Field
from typing_extensions import Annotated

from ._construction import ConstructionFacility
from ._permanent import PermanentFacility

# Common type definitions
AnyDebtFacility = Annotated[
    Union[ConstructionFacility, PermanentFacility], Field(discriminator="kind")
]
