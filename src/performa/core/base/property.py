from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import Field

from ..primitives.enums import AssetTypeEnum
from ..primitives.model import Model
from ..primitives.types import PositiveFloat, PositiveInt
from .program import ProgramComponentSpec


class Address(Model):
    """Street address of the property"""

    street: str
    city: str
    state: str
    zip_code: str
    country: str


class PropertyBaseModel(Model):
    """
    Base model for core property characteristics.
    """

    # Identity
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    description: Optional[str] = None
    external_id: Optional[str] = None
    address: Optional[Address] = None
    year_built: Optional[PositiveInt] = None

    
    # Physical Characteristics
    property_type: AssetTypeEnum
    gross_area: PositiveFloat
    net_rentable_area: PositiveFloat

    # Program mix (for mixed-use properties)
    # FIXME: address this
    program_components: Optional[List[ProgramComponentSpec]] = None
