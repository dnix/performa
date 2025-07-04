"""
Development Project Data Model

The DevelopmentProject is a pure data container that bundles all the
components needed to model the complete lifecycle of a real estate
development project from ground-breaking to stabilized operations.

This model now uses the "Asset Factory" pattern where development blueprints
create stabilized assets rather than becoming assets themselves.
"""

from __future__ import annotations

from typing import Annotated, List, Optional, Union

from pydantic import Discriminator

from ..asset.office import OfficeDevelopmentBlueprint
from ..asset.residential import ResidentialDevelopmentBlueprint
from ..common.base import DevelopmentBlueprintBase, PropertyBaseModel
from ..common.capital import CapitalPlan
from ..common.primitives import AssetTypeEnum
from ..debt import ConstructionFacility
from ..valuation import DispositionValuation

# Polymorphic union type for development blueprints
AnyDevelopmentBlueprint = Annotated[
    Union[OfficeDevelopmentBlueprint, ResidentialDevelopmentBlueprint],
    Discriminator("use_type"),
]


class DevelopmentProject(PropertyBaseModel):
    """
    Complete specification for a real estate development project.
    
    This model contains everything needed to analyze the complete lifecycle:
    - Physical specifications (inherited from PropertyBaseModel)
    - Construction plan (CapitalPlan with timeline and costs)
    - Financing plan (ConstructionFacility with debt/equity structure)
    - Development blueprints (polymorphic list of asset factory blueprints)
    - Disposition strategy (exit assumptions and timing)
    
    The AnalysisScenario acts as the "Assembler" that reads this blueprint
    and orchestrates the cash flow models for the entire lifecycle.
    
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
            financing_plan=financing_plan,
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
            ],
            disposition_valuation=disposition_valuation
        )
        ```
    """
    
    
    # Development projects must specify what property type they're developing
    # This is required (in parent class)and should reflect the actual development:
    # - AssetTypeEnum.OFFICE for office-only developments  
    # - AssetTypeEnum.MULTIFAMILY for residential-only developments
    # - AssetTypeEnum.MIXED_USE for true mixed-use developments
    # - etc.
    # TODO: review this
    # property_type: AssetTypeEnum  # Required field inherited from PropertyBaseModel
    
    # Construction & Development
    construction_plan: CapitalPlan
    financing_plan: ConstructionFacility
    blueprints: List[AnyDevelopmentBlueprint]
    
    # Exit Strategy
    disposition_valuation: Optional[DispositionValuation] = None
 