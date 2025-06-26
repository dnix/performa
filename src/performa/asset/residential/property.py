from __future__ import annotations

from typing import List

from pydantic import Field, computed_field, model_validator

from ...common.base import PropertyBaseModel
from ...common.primitives import AssetTypeEnum
from .expense import ResidentialExpenses
from .losses import ResidentialLosses
from .misc_income import ResidentialMiscIncome

# Now we can import ResidentialRentRoll directly
from .rent_roll import ResidentialRentRoll


class ResidentialProperty(PropertyBaseModel):
    """
    Represents a multifamily residential property for analysis.
    
    This model embodies the "unit-centric" paradigm of residential
    real estate analysis, where the central concept is the "unit mix"
    rather than individual lease specifications.
    
    Key Architectural Differences from Office:
    - Uses unit_mix instead of rent_roll (aggregated by unit type)
    - Focuses on unit count and average rents rather than individual leases
    - Simplified turnover assumptions (per-unit costs vs. complex TI/LC)
    - Auto-calculates building areas from unit mix data
    
    The analysis scenario will "unroll" the unit_mix into individual
    ResidentialLease instances for granular cash flow modeling.
    """
    
    property_type: AssetTypeEnum = AssetTypeEnum.MULTIFAMILY
    unit_mix: ResidentialRentRoll
    expenses: ResidentialExpenses
    losses: ResidentialLosses
    miscellaneous_income: List[ResidentialMiscIncome] = Field(default_factory=list)
    
    # Note: gross_area and net_rentable_area are required by PropertyBaseModel
    # In residential context, net_rentable_area should equal unit_mix.total_rentable_area
    # gross_area should be slightly larger (typically 15-20% efficiency factor)
    
    @computed_field
    @property
    def unit_count(self) -> int:
        """Total number of units in the property"""
        return self.unit_mix.total_unit_count
    
    @computed_field
    @property
    def weighted_avg_rent(self) -> float:
        """Weighted average rent across all unit types"""
        return self.unit_mix.weighted_avg_rent
    
    @computed_field
    @property
    def occupancy_rate(self) -> float:
        """Current occupancy rate based on unit mix composition"""
        if self.unit_count == 0:
            return 0.0
        return self.unit_mix.occupied_units / self.unit_count
    
    @model_validator(mode='after')
    def _validate_area_consistency(self) -> "ResidentialProperty":
        """
        Validate that net rentable area matches unit mix total area.
        
        This ensures consistency between the PropertyBaseModel area fields
        and the unit mix calculations in residential properties.
        """
        unit_mix_area = self.unit_mix.total_rentable_area
        nra = self.net_rentable_area
        
        # Allow small rounding differences (0.1% tolerance)
        tolerance = 0.001
        if abs(unit_mix_area - nra) / nra > tolerance:
            percentage_diff = abs(unit_mix_area - nra) / nra * 100
            raise ValueError(
                f"Area inconsistency in property '{self.name}': "
                f"Unit mix total area ({unit_mix_area:,.0f} SF) differs from "
                f"Net Rentable Area ({nra:,.0f} SF) by {percentage_diff:.1f}%. "
                f"Net Rentable Area should match unit mix total."
            )
        
        return self 