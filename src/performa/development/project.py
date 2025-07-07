"""
Development Project Data Model

The DevelopmentProject is a data container that bundles all the
components needed to model the complete lifecycle of a real estate
development project from ground-breaking to stabilized operations.

This model uses the "Asset Factory" pattern where development blueprints
create stabilized assets rather than becoming assets themselves.
"""

from __future__ import annotations

from typing import Annotated, List, Union

from pydantic import Discriminator

from ..asset.office import OfficeDevelopmentBlueprint
from ..asset.residential import ResidentialDevelopmentBlueprint
from ..common.base import DevelopmentBlueprintBase, PropertyBaseModel
from ..common.capital import CapitalPlan
from ..common.primitives import AssetTypeEnum

# Polymorphic union type for development blueprints
AnyDevelopmentBlueprint = Annotated[
    Union[OfficeDevelopmentBlueprint, ResidentialDevelopmentBlueprint],
    Discriminator("use_type"),
]  # FIXME: this could be problematic to maintain as we add more use types. can we just use parent classes for typing?


class DevelopmentProject(PropertyBaseModel):
    """
    Development project asset model for real estate development modeling.
    
    This model represents a development project containing physical specifications,
    construction plans, and operational blueprints that define how the completed
    project will operate once stabilized.
    
    Key Components:
    - Physical specifications (inherited from PropertyBaseModel)  
    - Construction plan (CapitalPlan with timeline and costs)
    - Development blueprints (specifications for stabilized operations)
    
    Implementation Pattern:
    The `blueprints` field uses the "Asset Factory" pattern where each blueprint
    knows how to create its stabilized asset type (OfficeProperty, ResidentialProperty, etc.).
    
    Example:
        ```python
        project = DevelopmentProject(
            name="Mixed-Use Urban Development",
            property_type=AssetTypeEnum.MIXED_USE,
            gross_area=1200000.0,
            net_rentable_area=1050000.0,
            construction_plan=construction_plan,
            blueprints=[
                OfficeDevelopmentBlueprint(
                    name="Office Tower",
                    vacant_inventory=[...],
                    absorption_plan=office_absorption_plan
                ),
                ResidentialDevelopmentBlueprint(
                    name="Residential Component", 
                    vacant_inventory=[...],
                    absorption_plan=residential_absorption_plan
                )
            ]
        )
        ```
    """
    
    # Development projects must specify what property type they're developing
    # This is required and should reflect the actual development type:
    # - AssetTypeEnum.OFFICE for office-only developments  
    # - AssetTypeEnum.MULTIFAMILY for residential-only developments
    # - AssetTypeEnum.MIXED_USE for true mixed-use developments
    # property_type: AssetTypeEnum  # Required field inherited from PropertyBaseModel
    
    # Asset Components - Physical Development
    construction_plan: CapitalPlan
    blueprints: List[AnyDevelopmentBlueprint]
 