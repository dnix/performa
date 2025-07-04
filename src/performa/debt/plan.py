"""
Financing Plan - Container for Debt Facilities

This module defines the FinancingPlan which orchestrates a sequence of debt facilities
to support complex financing scenarios like construction-to-permanent workflows.
"""

from __future__ import annotations

from typing import List, Optional, Union

from pydantic import Field, computed_field, model_validator

from ..common.primitives import Model
from .construction import ConstructionFacility
from .debt_facility import DebtFacility
from .permanent import PermanentFacility

# Union type for all debt facility types
AnyDebtFacility = Union[ConstructionFacility, PermanentFacility, DebtFacility]


class FinancingPlan(Model):
    """
    Container for a sequence of debt facilities over an asset's lifecycle.
    
    This enables complex financing scenarios like:
    - Construction loan → Permanent loan refinancing
    - Bridge loan → Permanent loan refinancing  
    - Multiple permanent loans with different terms
    - Debt facilities with different timing and terms
    
    The FinancingPlan orchestrates the sequence and transitions between facilities,
    while each facility handles its own debt service calculations.
    
    Key Features:
    - Supports multiple debt facilities in sequence
    - Handles refinancing transitions (construction → permanent)
    - Maintains facility timing and coordination
    - Integrates with Deal-level cash flow orchestration
    
    Examples:
        # Simple permanent financing
        plan = FinancingPlan(
            name="Permanent Financing",
            facilities=[permanent_loan]
        )
        
        # Construction-to-permanent financing
        plan = FinancingPlan(
            name="Construction-to-Permanent",
            facilities=[construction_loan, permanent_loan]
        )
        
        # Complex multi-facility financing
        plan = FinancingPlan(
            name="Multi-Phase Financing",
            facilities=[
                construction_loan,
                bridge_loan,
                permanent_loan_1,
                permanent_loan_2
            ]
        )
    """
    
    # Core Identity
    name: str = Field(..., description="Name of the financing plan")
    description: Optional[str] = Field(default=None, description="Description of financing strategy")
    
    # Debt Facilities Sequence
    facilities: List[AnyDebtFacility] = Field(
        ...,
        description="List of debt facilities in chronological order",
        min_length=1
    )
    
    @computed_field
    @property
    def primary_facility(self) -> AnyDebtFacility:
        """
        Get the primary (first) debt facility in the plan.
        
        Returns:
            The first debt facility in the sequence
        """
        return self.facilities[0]
    
    @computed_field
    @property
    def has_construction_financing(self) -> bool:
        """Check if the plan includes construction financing."""
        return any(
            isinstance(facility, ConstructionFacility) 
            for facility in self.facilities
        )
    
    @computed_field
    @property
    def has_permanent_financing(self) -> bool:
        """Check if the plan includes permanent financing."""
        return any(
            isinstance(facility, PermanentFacility) 
            for facility in self.facilities
        )
    
    @computed_field
    @property
    def has_refinancing(self) -> bool:
        """Check if the plan includes a refinancing transition."""
        return len(self.facilities) > 1
    
    @computed_field
    @property
    def construction_facilities(self) -> List[ConstructionFacility]:
        """Get all construction facilities in the plan."""
        return [
            facility for facility in self.facilities
            if isinstance(facility, ConstructionFacility)
        ]
    
    @computed_field
    @property
    def permanent_facilities(self) -> List[PermanentFacility]:
        """Get all permanent facilities in the plan."""
        return [
            facility for facility in self.facilities
            if isinstance(facility, PermanentFacility)
        ]
    
    @model_validator(mode='after')
    def validate_facility_sequence(self) -> "FinancingPlan":
        """
        Validate that the facility sequence makes business sense.
        
        Business rules:
        - Construction facilities should come before permanent facilities
        - Multiple facilities should have logical sequencing
        - Refinancing scenarios should be valid
        """
        if len(self.facilities) < 1:
            raise ValueError("FinancingPlan must have at least one debt facility")
        
        # Check construction-to-permanent sequencing
        construction_facilities = self.construction_facilities
        permanent_facilities = self.permanent_facilities
        
        if construction_facilities and permanent_facilities:
            # Find indices of construction and permanent facilities
            construction_indices = [
                i for i, facility in enumerate(self.facilities)
                if isinstance(facility, ConstructionFacility)
            ]
            permanent_indices = [
                i for i, facility in enumerate(self.facilities)
                if isinstance(facility, PermanentFacility)
            ]
            
            # Construction should generally come before permanent
            if construction_indices and permanent_indices:
                last_construction_idx = max(construction_indices)
                first_permanent_idx = min(permanent_indices)
                
                if last_construction_idx > first_permanent_idx:
                    # This might be valid in some cases, but warn for now
                    # In future we could add more sophisticated validation
                    pass
        
        return self
    
    def get_facility_by_name(self, name: str) -> Optional[AnyDebtFacility]:
        """
        Get a facility by its name.
        
        Args:
            name: Name of the facility to find
            
        Returns:
            The facility with the given name, or None if not found
        """
        for facility in self.facilities:
            if hasattr(facility, 'name') and facility.name == name:
                return facility
        return None
    
    def get_facilities_by_type(self, facility_type: type) -> List[AnyDebtFacility]:
        """
        Get all facilities of a specific type.
        
        Args:
            facility_type: Type of facility to find (e.g., ConstructionFacility)
            
        Returns:
            List of facilities of the specified type
        """
        return [
            facility for facility in self.facilities
            if isinstance(facility, facility_type)
        ] 