"""
Core Deal Model - Universal Investment Container

This module defines the central Deal model that wraps any asset type with
complete investment strategy including acquisition, financing, disposition, and equity structure.
"""

from __future__ import annotations

from typing import List, Optional, Union
from uuid import UUID, uuid4

from pydantic import Field, computed_field

from ..asset.office.property import OfficeProperty
from ..asset.residential.property import ResidentialProperty
from ..common.primitives import AssetTypeEnum, Model
from ..debt.plan import FinancingPlan
from ..development.project import DevelopmentProject
from ..valuation.disposition import DispositionValuation
from .acquisition import AcquisitionTerms
from .partners import PartnershipStructure

# Simple union for all asset types that can be in a Deal
# Pydantic v2 automatically infers the correct type based on unique fields:
# - OfficeProperty: has unique 'rent_roll' field of type OfficeRentRoll
# - ResidentialProperty: has unique 'unit_mix' field of type ResidentialRentRoll
# - DevelopmentProject: has unique 'construction_plan' and 'blueprints' fields
# No artificial discriminator needed - let Pydantic do the smart type inference
# FIXME; this could be problematic to maintain as we add more use types. can we just use parent classes for typing?
AnyAsset = Union[OfficeProperty, ResidentialProperty, DevelopmentProject]


class Deal(Model):
    """
    Universal deal container for any real estate investment.
    
    This is the core model that enables the unified deal-centric architecture.
    It cleanly separates the physical asset from the investment strategy,
    allowing the same analyze_deal() function to handle any scenario.
    
    Key Architecture:
    - asset: The physical real estate property or development project
    - acquisition: How the asset is purchased (timing, costs)
    - financing: Complete debt structure over asset lifecycle
    - disposition: Exit strategy and assumptions
    - equity: Partner structure and waterfall logic
    
    Examples:
        # Simple stabilized acquisition
        deal = Deal(
            name="123 Main Street Acquisition",
            asset=office_property,
            acquisition=AcquisitionTerms(...),
            financing=FinancingPlan([permanent_loan]),
            disposition=DispositionValuation(...)
        )
        
        # Complex development project
        deal = Deal(
            name="Urban Mixed-Use Development",
            asset=development_project,
            acquisition=AcquisitionTerms(...),  # Land acquisition
            financing=FinancingPlan([construction_loan, permanent_loan]),
            disposition=DispositionValuation(...)
        )
    """
    
    # Core Identity
    uid: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Deal name for identification")
    description: Optional[str] = Field(default=None, description="Deal description")
    
    # Core Components - The Universal Deal Structure
    asset: AnyAsset = Field(..., description="The physical real estate asset")
    acquisition: AcquisitionTerms = Field(..., description="Acquisition terms and costs")
    
    # Financing - Complete debt structure over asset lifecycle
    financing: Optional[FinancingPlan] = Field(default=None, description="Debt facilities sequence")
    
    disposition: Optional[DispositionValuation] = Field(
        default=None, description="Exit strategy and disposition assumptions"
    )
    
    # Equity Structure - Partnership structure for equity waterfall
    equity_partners: Optional[PartnershipStructure] = Field(
        default=None, description="Partnership structure for equity waterfall and distributions"
    )
    
    @computed_field
    @property
    def deal_type(self) -> str:
        """
        Classify the deal based on the asset type.
        
        Returns:
            String classification of the deal type
        """
        # FIXME: this could be problematic to maintain as we add more use types
        # Use duck typing to detect development projects
        if hasattr(self.asset, 'construction_plan'):
            return "development"
        elif self.asset.property_type == AssetTypeEnum.OFFICE:
            return "office_acquisition"
        elif self.asset.property_type == AssetTypeEnum.MULTIFAMILY:
            return "residential_acquisition"
        else:
            return f"{self.asset.property_type.value}_acquisition"
    
    @computed_field
    @property
    def is_development_deal(self) -> bool:
        """Check if this is a development deal."""
        return hasattr(self.asset, 'construction_plan')
    
    @computed_field
    @property
    def is_stabilized_deal(self) -> bool:
        """Check if this is a stabilized asset deal."""
        return not self.is_development_deal
    
    @computed_field
    @property
    def financing_type(self) -> str:
        """
        Classify the financing structure.
        
        Returns:
            String classification of the financing type
        """
        if self.financing is None:
            return "all_equity"
        elif self.financing.has_refinancing:
            return "refinancing"
        elif self.financing.has_construction_financing:
            return "construction_financing"
        elif self.financing.has_permanent_financing:
            return "permanent_financing"
        else:
            return "other_financing"
    
    @computed_field
    @property
    def has_equity_partners(self) -> bool:
        """Check if this deal has equity partners."""
        return self.equity_partners is not None and self.equity_partners.partner_count > 0
    
    @computed_field
    @property
    def total_facilities(self) -> int:
        """Get the total number of debt facilities in the financing plan."""
        return len(self.financing.facilities) if self.financing else 0
    
    def validate_deal_components(self) -> None:
        """
        Validate that all deal components are compatible.
        
        This method performs business logic validation to ensure
        the deal components make sense together.
        """
        # FIXME: is this necessary? should we be using pydantic validators instead?
        # Validate asset has property_type for business logic
        if not hasattr(self.asset, 'property_type'):
            raise ValueError(f"Asset {type(self.asset)} missing required 'property_type' field")
        
        # Additional validations can be added here
        # For example, ensuring financing is appropriate for asset type
        pass 