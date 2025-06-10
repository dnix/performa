from __future__ import annotations

import pytest

from performa.common.base._program_base import ProgramComponentSpec
from performa.common.base._property_base import Address, PropertyBaseModel
from performa.common.primitives import AssetTypeEnum, ProgramUseEnum


def test_property_base_instantiation():
    """Test successful instantiation of PropertyBaseModel."""
    addr = Address(
        street="123 Main St", city="Anytown", state="CA", zip_code="12345", country="USA"
    )
    prog = ProgramComponentSpec(program_use=ProgramUseEnum.OFFICE, area=100000, identifier="Main Tower")
    
    prop = PropertyBaseModel(
        name="Test Property",
        address=addr,
        property_type=AssetTypeEnum.OFFICE,
        gross_area=120000,
        net_rentable_area=100000,
        program_components=[prog]
    )
    assert prop.name == "Test Property"
    assert prop.address.city == "Anytown"
    assert len(prop.program_components) == 1
