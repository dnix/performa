"""
Residential development blueprint implementation.

This module defines the concrete implementation of the development blueprint pattern
for residential/multifamily assets, following the "Asset Factory" design where 
development projects create stabilized assets rather than becoming assets themselves.

The residential blueprint follows the "unit-centric" paradigm of multifamily real estate
analysis, where properties are modeled by unit mix rather than individual leases.
"""

from __future__ import annotations

from typing import List, Literal

from ...core.base import DevelopmentBlueprintBase
from ...core.primitives import Timeline
from .absorption import ResidentialAbsorptionPlan
from .expense import ResidentialExpenses
from .losses import (
    ResidentialCollectionLoss,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
)
from .misc_income import ResidentialMiscIncome
from .property import ResidentialProperty
from .rent_roll import ResidentialRentRoll, ResidentialVacantUnit


class ResidentialDevelopmentBlueprint(DevelopmentBlueprintBase):
    """
    Development blueprint for residential/multifamily assets.
    
    This class encapsulates all the knowledge required to transform a development
    plan into a stabilized residential property. It follows the "Asset Factory" pattern
    where the blueprint acts as a specialized factory for creating ResidentialProperty
    instances from development inputs.
    
    The blueprint contains:
    - vacant_inventory: The unit mix being developed (unit-centric approach)
    - absorption_plan: Complete business plan for stabilization (REQUIRED)
    
    The absorption_plan serves as the complete business plan and contains:
    - Leasing pace and timing (unit-based: lease 10 units/month)
    - Template lease specifications for new market leases
    - Stabilized operating assumptions  
    - Complete business logic for vacant units → stabilization
    
    Key Differences from Office Blueprint:
    - Unit-centric vs area-centric (units instead of square footage)
    - ResidentialVacantUnit vs OfficeVacantSuite
    - Creates ResidentialProperty vs OfficeProperty
    - Unit mix modeling vs individual lease specifications
    
    Attributes:
        vacant_inventory: List of vacant residential units to be leased up
        absorption_plan: Complete business plan for lease-up and stabilization
    """
    
    use_type: Literal["RESIDENTIAL"] = "RESIDENTIAL"
    vacant_inventory: List[ResidentialVacantUnit]
    absorption_plan: ResidentialAbsorptionPlan
    
    # TODO: Future consideration - alternative path for direct stabilized asset specification
    # (explicit unit specs, expenses, losses, misc_income without absorption logic)
    # This would enable instant stabilization scenarios vs. phased lease-up scenarios
    
    def to_stabilized_asset(self, timeline: Timeline) -> ResidentialProperty:
        """
        Factory method to create a stabilized residential property.
        
        This method executes the absorption plan against the vacant inventory
        to generate unit specifications, then constructs a fully-formed
        ResidentialProperty ready for operations analysis.
        
        The process:
        1. Execute absorption plan to generate unit specs from vacant inventory
        2. Identify any remaining vacant units after absorption  
        3. Create stabilized rent roll with generated unit specs + remaining vacant
        4. Apply stabilized operating assumptions from absorption plan
        5. Return fully-formed ResidentialProperty ready for analysis
        
        Args:
            timeline: Project timeline for phasing construction and absorption
            
        Returns:
            Stabilized ResidentialProperty with unit specs and operating assumptions
            
        Raises:
            ValueError: If absorption plan execution fails
            ValueError: If timeline is incompatible with absorption plan
        """
        if timeline.is_relative:
            raise ValueError(
                "Cannot execute absorption plan with relative timeline. "
                "Timeline must be absolute with specific start/end dates."
            )
        
        # Convert timeline to dates for absorption plan execution
        analysis_start_date = timeline.start_date.to_timestamp().date()
        analysis_end_date = timeline.end_date.to_timestamp().date()
        
        # Execute absorption plan to generate unit specifications
        generated_unit_specs = self.absorption_plan.generate_unit_specs(
            available_vacant_units=self.vacant_inventory,
            analysis_start_date=analysis_start_date,
            analysis_end_date=analysis_end_date,
            lookup_fn=None,  # TODO: Add lookup function support if needed
            global_settings=None,  # TODO: Add global settings support if needed
        )
        
        # Identify remaining vacant units after absorption
        # For residential, we track by unit counts rather than area
        remaining_vacant_units = []
        for vacant_unit in self.vacant_inventory:
            # Count how many units of this type were absorbed
            absorbed_count = sum(
                spec.unit_count for spec in generated_unit_specs 
                if spec.unit_type_name == vacant_unit.unit_type_name
            )
            
            # If there are remaining units, create a new vacant unit entry
            remaining_count = vacant_unit.unit_count - absorbed_count
            if remaining_count > 0:
                remaining_vacant_unit = ResidentialVacantUnit(
                    unit_type_name=f"{vacant_unit.unit_type_name}_remaining",
                    unit_count=remaining_count,
                    avg_area_sf=vacant_unit.avg_area_sf,
                    market_rent=vacant_unit.market_rent,
                    rollover_profile=vacant_unit.rollover_profile,
                )
                remaining_vacant_units.append(remaining_vacant_unit)
        
        # Create stabilized rent roll with unit-centric structure
        stabilized_rent_roll = ResidentialRentRoll(
            unit_specs=generated_unit_specs,
            vacant_units=remaining_vacant_units,
        )
        
        # Use default operating assumptions
        # TODO: Extract operating assumptions from absorption plan when implemented
        stabilized_expenses = ResidentialExpenses()
        stabilized_losses = ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),  # Default 5% vacancy
            collection_loss=ResidentialCollectionLoss(rate=0.01)       # Default 1% collection loss
        )
        stabilized_misc_income = []
        
        # Calculate total area from unit mix for NRA
        total_area = sum(unit.total_area for unit in self.vacant_inventory)
        
        # Create and return the stabilized residential property
        return ResidentialProperty(
            name=self.name,
            address=None,  # TODO: Add address support from development project
            gross_area=total_area * 1.15,  # Assume 15% efficiency factor for residential (includes common areas)
            net_rentable_area=total_area,
            unit_mix=stabilized_rent_roll,
            expenses=stabilized_expenses,
            losses=stabilized_losses,
            miscellaneous_income=stabilized_misc_income,
            capital_plans=[],  # Empty for stabilized asset
        ) 