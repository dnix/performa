from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import Field, computed_field, model_validator

from ...common.primitives import Model, PositiveFloat, PositiveInt
from .rollover import ResidentialRolloverProfile


class ResidentialUnitSpec(Model):
    """
    Represents a group of identical units in a multifamily property.
    
    This is the core of the "unit mix" paradigm for residential real estate.
    Instead of defining individual leases (as in office), we define groups
    of identical units with their shared characteristics.
    
    ASSEMBLER PATTERN - BLUEPRINT COMPONENT:
    This model stores only lightweight UUID references to capital plans.
    The AnalysisScenario acts as the "Assembler" that resolves these UUIDs
    into direct object references when creating runtime lease instances.
    
    Key Architectural Concept:
    - unit_type_name: Human-readable identifier (e.g., "1BR/1BA - Garden")
    - unit_count: Number of identical units of this type
    - avg_area_sf: Average square footage per unit
    - current_avg_monthly_rent: Current average rent per unit per month
    - rollover_profile: Assumptions for turnover, rent growth, costs
    - capital_plan_id: UUID reference to renovation project for value-add scenarios
    
    The analysis engine will "unroll" this specification into individual
    ResidentialLease instances - one for each physical unit.
    """
    
    unit_type_name: str
    unit_count: PositiveInt
    avg_area_sf: PositiveFloat
    current_avg_monthly_rent: PositiveFloat
    rollover_profile: ResidentialRolloverProfile
    capital_plan_id: Optional[UUID] = Field(
        default=None,
        description="UUID reference to CapitalPlan for value-add renovations when units turn over"
    )
    
    @computed_field
    @property
    def total_area(self) -> float:
        """Total area for all units of this type."""
        return self.unit_count * self.avg_area_sf
    
    @computed_field
    @property
    def monthly_income_potential(self) -> float:
        """Total monthly rental income potential for all units of this type."""
        return self.unit_count * self.current_avg_monthly_rent


class ResidentialVacantUnit(Model):
    """
    Represents a group of identical vacant units in a multifamily property.
    
    Mirrors the ResidentialUnitSpec structure but for units that are currently
    vacant. This enables explicit vacancy modeling rather than percentage-based
    occupancy rates.
    
    Attributes:
        unit_type_name: Description of the unit type (e.g., "1BR/1BA - Vacant")
        unit_count: Number of vacant units of this type
        avg_area_sf: Average square footage per unit
        market_rent: Expected market rent when leased
        rollover_profile: Leasing assumptions for these units
    """
    
    unit_type_name: str
    unit_count: PositiveInt
    avg_area_sf: PositiveFloat
    market_rent: PositiveFloat
    rollover_profile: ResidentialRolloverProfile
    
    @computed_field
    @property
    def total_area(self) -> float:
        """Total area for all vacant units of this type."""
        return self.unit_count * self.avg_area_sf
    
    @computed_field
    @property
    def monthly_income_potential(self) -> float:
        """Total monthly rental income potential if all units were leased."""
        return self.unit_count * self.market_rent


class ResidentialRentRoll(Model):
    """
    Container for all unit specifications in a multifamily property.
    
    This model represents the "Unit Mix" that is standard in multifamily
    underwriting. Unlike office properties with unique lease specifications,
    residential properties are analyzed by grouping identical units.
    
    Key Properties:
    - unit_specs: List of ResidentialUnitSpec defining occupied unit types
    - vacant_units: List of ResidentialVacantUnit defining vacant units
    - Computed aggregates: total units, total area, total income
    - Industry-standard calculated metrics
    
    Architecture Note:
    This follows the same explicit vacancy pattern as the office module,
    where occupancy emerges from the composition of occupied vs vacant units
    rather than being a hardcoded percentage.
    """
    
    # DESIGN DECISION: unit_specs is REQUIRED (core property definition)
    # A multifamily property without unit specifications doesn't make business sense
    unit_specs: List[ResidentialUnitSpec]
    
    # vacant_units is OPTIONAL with default_factory - properties can start fully occupied
    vacant_units: List[ResidentialVacantUnit] = Field(default_factory=list)
    
    @model_validator(mode='after')
    def _validate_business_rules(self) -> "ResidentialRentRoll":
        """Validate critical business rules for residential properties."""
        # A property must have either occupied units OR vacant units (or both)
        # Empty unit_specs is allowed if there are vacant_units (e.g., lease-up phase)
        if not self.unit_specs and not self.vacant_units:
            raise ValueError(
                "Residential property must have at least one unit specification or vacant unit. "
                "Empty unit_specs and vacant_units lists are not valid for multifamily analysis."
            )
        return self
    
    @computed_field
    @property
    def occupied_units(self) -> int:
        """Total number of occupied units."""
        return sum(spec.unit_count for spec in self.unit_specs)
    
    @computed_field
    @property
    def vacant_unit_count(self) -> int:
        """Total number of vacant units."""
        return sum(vacant.unit_count for vacant in self.vacant_units)
    
    @computed_field
    @property
    def total_unit_count(self) -> int:
        """Total number of units (occupied + vacant)."""
        return self.occupied_units + self.vacant_unit_count
    
    @computed_field
    @property
    def occupied_area(self) -> float:
        """Total rentable area of occupied units."""
        return sum(spec.total_area for spec in self.unit_specs)
    
    @computed_field
    @property
    def vacant_area(self) -> float:
        """Total rentable area of vacant units."""
        return sum(vacant.total_area for vacant in self.vacant_units)
    
    @computed_field
    @property
    def total_rentable_area(self) -> float:
        """Total rentable area across all units (occupied + vacant)."""
        return self.occupied_area + self.vacant_area
    
    @computed_field
    @property
    def current_monthly_income(self) -> float:
        """Current monthly rental income from occupied units only."""
        return sum(spec.monthly_income_potential for spec in self.unit_specs)
    
    @computed_field
    @property
    def total_monthly_income_potential(self) -> float:
        """Total monthly rental income potential if all units were leased."""
        occupied_income = sum(spec.monthly_income_potential for spec in self.unit_specs)
        vacant_income = sum(vacant.monthly_income_potential for vacant in self.vacant_units)
        return occupied_income + vacant_income
    
    @computed_field
    @property
    def occupancy_rate(self) -> float:
        """Current occupancy rate calculated from unit composition."""
        if self.total_unit_count == 0:
            return 0.0
        return self.occupied_units / self.total_unit_count
    
    @computed_field
    @property
    def average_rent_per_unit(self) -> float:
        """Weighted average rent per unit if all units were leased."""
        if self.total_unit_count == 0:
            return 0.0
        return self.total_monthly_income_potential / self.total_unit_count
    
    @computed_field
    @property
    def current_average_rent_per_occupied_unit(self) -> float:
        """Average rent per currently occupied unit."""
        if self.occupied_units == 0:
            return 0.0
        return self.current_monthly_income / self.occupied_units
    
    @computed_field
    @property
    def average_rent_per_sf(self) -> float:
        """Weighted average rent per square foot if all units were leased."""
        if self.total_rentable_area == 0:
            return 0.0
        return self.total_monthly_income_potential / self.total_rentable_area
    
    @computed_field
    @property  
    def weighted_avg_rent(self) -> float:
        """Alias for average_rent_per_unit - weighted average rent per unit."""
        return self.average_rent_per_unit 