"""
Office development blueprint implementation.

This module defines the concrete implementation of the development blueprint pattern
for office assets, following the "Asset Factory" design where development projects
create stabilized assets rather than becoming assets themselves.
"""

from __future__ import annotations

from typing import List, Literal

from ...core.base import DevelopmentBlueprintBase
from ...core.primitives import Timeline
from .absorption import OfficeAbsorptionPlan
from .expense import OfficeExpenses
from .losses import OfficeCollectionLoss, OfficeGeneralVacancyLoss, OfficeLosses
from .misc_income import OfficeMiscIncome
from .property import OfficeProperty
from .rent_roll import OfficeRentRoll, OfficeVacantSuite


class OfficeDevelopmentBlueprint(DevelopmentBlueprintBase):
    """
    Development blueprint for office assets.
    
    This class encapsulates all the knowledge required to transform a development
    plan into a stabilized office property. It follows the "Asset Factory" pattern
    where the blueprint acts as a specialized factory for creating OfficeProperty
    instances from development inputs.
    
    The blueprint contains:
    - vacant_inventory: The physical space being developed  
    - absorption_plan: Complete business plan for stabilization (REQUIRED)
    
    The absorption_plan serves as the complete business plan and contains:
    - Leasing pace and timing
    - Template lease specifications for new market leases
    - Stabilized operating assumptions  
    - Complete business logic for vacant space → stabilization
    
    Attributes:
        vacant_inventory: List of vacant office suites to be leased up
        absorption_plan: Complete business plan for lease-up and stabilization
    """
    
    use_type: Literal["OFFICE"] = "OFFICE"
    vacant_inventory: List[OfficeVacantSuite]
    absorption_plan: OfficeAbsorptionPlan
    
    # TODO: Future consideration - alternative path for direct stabilized asset specification
    # (explicit leases, expenses, losses, misc_income without absorption logic)
    # This would enable instant stabilization scenarios vs. phased lease-up scenarios
    
    def to_stabilized_asset(self, timeline: Timeline) -> OfficeProperty:
        """
        Factory method to create a stabilized office property.
        
        This method executes the absorption plan against the vacant inventory
        to generate lease specifications, then constructs a fully-formed
        OfficeProperty ready for operations analysis.
        
        The process:
        1. Execute absorption plan to generate lease specs from vacant inventory
        2. Identify any remaining vacant suites after absorption  
        3. Create stabilized rent roll with generated leases + remaining vacant
        4. Apply stabilized operating assumptions from absorption plan
        5. Return fully-formed OfficeProperty ready for analysis
        
        Args:
            timeline: Project timeline for phasing construction and absorption
            
        Returns:
            Stabilized OfficeProperty with lease specs and operating assumptions
            
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
        
        # Execute absorption plan to generate lease specifications
        generated_lease_specs = self.absorption_plan.generate_lease_specs(
            available_vacant_suites=self.vacant_inventory,
            analysis_start_date=analysis_start_date,
            analysis_end_date=analysis_end_date,
            lookup_fn=None,  # TODO: Add lookup function support if needed
            global_settings=None,  # TODO: Add global settings support if needed
        )
        
        # Identify remaining vacant suites after absorption
        # The absorption plan modifies suite states, so we need to check what's left
        remaining_vacant_suites = []
        for suite in self.vacant_inventory:
            # Check if suite was completely absorbed by looking at generated specs
            suite_lease_specs = [spec for spec in generated_lease_specs if spec.suite == suite.suite]
            total_leased_area = sum(spec.area for spec in suite_lease_specs)
            
            if total_leased_area < suite.area:
                # Create a new vacant suite for the remaining area
                remaining_area = suite.area - total_leased_area
                if remaining_area > 0:
                    remaining_vacant_suite = OfficeVacantSuite(
                        suite=f"{suite.suite}_remaining",
                        floor=suite.floor,
                        area=remaining_area,
                        use_type=suite.use_type,
                        is_divisible=suite.is_divisible,
                        subdivision_average_lease_area=suite.subdivision_average_lease_area,
                        subdivision_minimum_lease_area=suite.subdivision_minimum_lease_area,
                    )
                    remaining_vacant_suites.append(remaining_vacant_suite)
        
        # Create stabilized rent roll
        stabilized_rent_roll = OfficeRentRoll(
            leases=generated_lease_specs,
            vacant_suites=remaining_vacant_suites,
        )
        
        # Use default operating assumptions
        # TODO: Extract operating assumptions from absorption plan when implemented
        stabilized_expenses = OfficeExpenses()
        stabilized_losses = OfficeLosses(
            general_vacancy=OfficeGeneralVacancyLoss(rate=0.05),  # Default 5% vacancy
            collection_loss=OfficeCollectionLoss(rate=0.01)       # Default 1% collection loss
        )
        stabilized_misc_income = []
        
        # Calculate total area from vacant inventory
        total_area = sum(suite.area for suite in self.vacant_inventory)
        
        # Create and return the stabilized office property
        return OfficeProperty(
            name=self.name,
            address=None,  # TODO: Add address support from development project
            property_type="office",  # Office asset type
            gross_area=total_area * 1.1,  # Assume 10% efficiency factor (gross > net)
            net_rentable_area=total_area,
            rent_roll=stabilized_rent_roll,
            expenses=stabilized_expenses,
            losses=stabilized_losses,
            miscellaneous_income=stabilized_misc_income,
            absorption_plans=[],  # Empty for stabilized asset
        ) 