from __future__ import annotations

import logging
from typing import List

from performa.analysis import AnalysisScenarioBase, register_scenario
from performa.common.primitives import (
    CashFlowModel,
    FrequencyEnum,
    LeaseStatusEnum,
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)

from .expense import ResidentialCapExItem, ResidentialOpExItem
from .lease import ResidentialLease
from .misc_income import ResidentialMiscIncome
from .property import ResidentialProperty
from .rent_roll import ResidentialUnitSpec

logger = logging.getLogger(__name__)


@register_scenario(ResidentialProperty)
class ResidentialAnalysisScenario(AnalysisScenarioBase):
    """
    Analysis scenario for residential multifamily properties.
    
    This is the critical "translator" that bridges the gap between the high-level
    ResidentialProperty model (with its unit-centric paradigm) and the low-level
    CashFlowOrchestrator (which processes individual CashFlowModel instances).
    
    Key Responsibility: "Unrolling the Unit Mix"
    =============================================
    The central architectural challenge is converting the aggregated "unit mix"
    input into granular lease instances:
    
    INPUT:  ResidentialUnitSpec("1BR/1BA", count=40, rent=$2,200)
    OUTPUT: 40 individual ResidentialLease instances
    
    This allows efficient user input (aggregate) while enabling precise analysis
    (granular) with staggered lease expirations and individual unit lifecycles.
    """
    
    model: ResidentialProperty
    
    def prepare_models(self) -> List[CashFlowModel]:
        """
        Prepares all cash flow models for residential analysis.
        
        This method performs the critical "unrolling" operation:
        1. Loop through each unit type specification
        2. Create individual ResidentialLease instances for each physical unit
        3. Add property-level expense and income models
        4. Return complete list for the CashFlowOrchestrator
        
        Returns:
            List of CashFlowModel instances ready for analysis
        """
        all_models: List[CashFlowModel] = []
        
        logger.info(f"Preparing models for residential property '{self.model.name}' "
                   f"with {self.model.unit_count} total units")
        
        # 1. UNROLL UNIT MIX: Convert unit specifications to individual lease instances
        all_models.extend(self._create_lease_models_from_unit_mix())
        
        # 2. PROPERTY EXPENSES: Add operating and capital expense models
        all_models.extend(self._create_expense_models())
        
        # 3. MISCELLANEOUS INCOME: Add additional income streams
        all_models.extend(self._create_misc_income_models())
        
        logger.info(f"Prepared {len(all_models)} total cash flow models for analysis")
        
        return all_models
    
    def _create_lease_models_from_unit_mix(self) -> List[ResidentialLease]:
        """
        The heart of residential analysis: convert unit mix to individual leases.
        
        This method embodies the paradigm shift from office to residential:
        - Office: rent_roll.leases (already individual)
        - Residential: unit_mix.unit_specs (aggregate -> needs unrolling)
        
        For each unit spec (e.g., "1BR/1BA - Garden Level", count=25):
        1. Loop 25 times to create 25 individual ResidentialLease instances
        2. Each lease represents one physical apartment unit
        3. Set reasonable defaults for lease timing and terms
        4. Link each lease to its source unit spec for rollover logic
        
        Returns:
            List of ResidentialLease instances (one per physical unit)
        """
        lease_models = []
        
        for unit_spec in self.model.unit_mix.unit_specs:
            logger.debug(f"Unrolling unit spec '{unit_spec.unit_type_name}': "
                        f"{unit_spec.unit_count} units at ${unit_spec.current_avg_monthly_rent}/month")
            
            # Create individual lease instance for each physical unit
            for unit_number in range(1, unit_spec.unit_count + 1):
                lease_instance = self._create_lease_from_unit_spec(unit_spec, unit_number)
                lease_models.append(lease_instance)
        
        logger.info(f"Created {len(lease_models)} individual lease instances from unit mix")
        return lease_models
    
    def _create_lease_from_unit_spec(
        self, 
        unit_spec: ResidentialUnitSpec, 
        unit_number: int
    ) -> ResidentialLease:
        """
        Create a single ResidentialLease instance from a unit specification.
        
        This method sets up realistic defaults for a stabilized property analysis:
        - All leases start at analysis start (stabilized assumption)
        - Standard 12-month lease terms (typical residential)
        - Sequential suite numbering for identification
        - Links back to source spec for rollover logic
        
        Args:
            unit_spec: The unit type specification
            unit_number: Sequential number for this unit (1, 2, 3...)
            
        Returns:
            ResidentialLease instance representing one physical unit
        """
        # Generate a unique suite identifier
        # Format: "{UnitType}-{Number}" (e.g., "1BR1BA-001", "1BR1BA-002")
        safe_unit_type = unit_spec.unit_type_name.replace("/", "").replace(" ", "").replace("-", "")
        suite_id = f"{safe_unit_type}-{unit_number:03d}"
        
        # For stabilized properties, assume all leases start at analysis start
        # Future enhancement: stagger lease start dates for more realistic modeling
        lease_timeline = Timeline(
            start_date=self.timeline.start_date.to_timestamp().date(),
            duration_months=12  # Standard residential lease term
        )
        
        # Create the lease instance
        lease = ResidentialLease(
            name=f"Resident {suite_id}",
            timeline=lease_timeline,
            status=LeaseStatusEnum.CONTRACT,  # Existing tenant in stabilized property
            area=unit_spec.avg_area_sf,
            suite=suite_id,
            floor="1",  # Simplified - future enhancement could vary by unit
            upon_expiration=UponExpirationEnum.MARKET,  # Standard rollover handling
            value=unit_spec.current_avg_monthly_rent,  # Monthly rent in dollars
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            frequency=FrequencyEnum.MONTHLY,
            rollover_profile=unit_spec.rollover_profile,
            source_spec=unit_spec,  # Critical link for rollover logic
            settings=self.settings,
        )
        
        logger.debug(f"Created lease for {suite_id}: ${unit_spec.current_avg_monthly_rent}/month, "
                    f"{unit_spec.avg_area_sf} SF")
        
        return lease
    
    def _create_expense_models(self) -> List[CashFlowModel]:
        """
        Create expense models for the residential property.
        
        Residential expenses are typically much simpler than office:
        - Property management fees
        - Utilities (if paid by landlord)
        - Maintenance and repairs
        - Insurance and taxes
        - Capital reserves
        
        The key difference: many expenses are calculated "per unit" rather
        than "per square foot" which is more common in office properties.
        
        Returns:
            List of expense CashFlowModel instances
        """
        models = []
        
        if self.model.expenses:
            # Operating Expenses
            if self.model.expenses.operating_expenses:
                for expense_item in self.model.expenses.operating_expenses:
                    if isinstance(expense_item, ResidentialOpExItem):
                        models.append(expense_item)
                        logger.debug(f"Added operating expense: {expense_item.name}")
            
            # Capital Expenses (reserves, major repairs, etc.)
            if self.model.expenses.capital_expenses:
                for expense_item in self.model.expenses.capital_expenses:
                    if isinstance(expense_item, ResidentialCapExItem):
                        models.append(expense_item)
                        logger.debug(f"Added capital expense: {expense_item.name}")
        
        logger.info(f"Added {len(models)} expense models")
        return models
    
    def _create_misc_income_models(self) -> List[CashFlowModel]:
        """
        Create miscellaneous income models for the residential property.
        
        Common residential miscellaneous income sources:
        - Laundry facilities
        - Parking fees  
        - Pet fees
        - Application fees
        - Late payment fees
        - Vending machines
        - Storage units
        
        Returns:
            List of miscellaneous income CashFlowModel instances
        """
        models = []
        
        if self.model.miscellaneous_income:
            for income_item in self.model.miscellaneous_income:
                if isinstance(income_item, ResidentialMiscIncome):
                    models.append(income_item)
                    logger.debug(f"Added miscellaneous income: {income_item.name}")
        
        logger.info(f"Added {len(models)} miscellaneous income models")
        return models 