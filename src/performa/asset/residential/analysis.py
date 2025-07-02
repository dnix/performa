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
    
    def run(self) -> None:
        """
        ASSEMBLER PATTERN - ENHANCED RUN METHOD
        
        This override implements the user's architectural guidance:
        1. Capital plans live on ResidentialProperty (Single Source of Truth)
        2. AnalysisContext serves as the universal data bus
        3. One-time UUID resolution during assembly
        4. Leases get direct object references (no runtime lookups)
        """
        from performa.analysis.orchestrator import AnalysisContext, CashFlowOrchestrator
        
        # === 1. CREATE UUID LOOKUP MAPS ===
        # This is the "hydration" step that happens once per analysis
        capital_plan_lookup = {plan.uid: plan for plan in self.model.capital_plans}
        
        # Collect all available rollover profiles (from unit specs and property)
        rollover_profile_lookup = {}
        if self.model.unit_mix:
            for unit_spec in self.model.unit_mix.unit_specs:
                profile = unit_spec.rollover_profile
                rollover_profile_lookup[profile.uid] = profile
                
                # Also collect any next_rollover_profiles that might be referenced
                if profile.next_rollover_profile_id and profile.next_rollover_profile_id not in rollover_profile_lookup:
                    # This would typically be resolved from a property-level rollover profile library
                    # For now, we assume all needed profiles are referenced via unit specs
                    pass
        
        # === 2. CREATE ENHANCED CONTEXT ===
        # The context becomes the universal data bus
        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=self.model,
            capital_plan_lookup=capital_plan_lookup,
            rollover_profile_lookup=rollover_profile_lookup,
        )

        # === 3. ASSEMBLE MODELS WITH DIRECT OBJECT INJECTION ===
        all_models = self.prepare_models(context)

        # === 4. RUN ORCHESTRATOR ===
        orchestrator = CashFlowOrchestrator(models=all_models, context=context)
        orchestrator.execute()
        self._orchestrator = orchestrator

    def prepare_models(self, context: AnalysisContext) -> List[CashFlowModel]:
        """
        ASSEMBLER LOGIC - UUID RESOLUTION AND OBJECT INJECTION
        
        This method now receives the fully-prepared context and performs
        the critical "assembly" step: resolving UUID references into
        direct object references for maximum runtime performance.
        """
        all_models = []
        prop: ResidentialProperty = self.model
        
        # Add individual expense items (not containers)
        # Only individual CashFlowModel instances should go to orchestrator
        if prop.expenses.operating_expenses:
            all_models.extend(prop.expenses.operating_expenses)
        if prop.expenses.capital_expenses:
            all_models.extend(prop.expenses.capital_expenses)
        
        # Add miscellaneous income items (these inherit from CashFlowModel)
        all_models.extend(prop.miscellaneous_income)
        
        # Note: Losses are handled differently by the orchestrator and don't go in all_models

        # === ASSEMBLE LEASES BY UNROLLING UNIT MIX ===
        if prop.unit_mix:
            for unit_spec in prop.unit_mix.unit_specs:
                for unit_index in range(unit_spec.unit_count):
                    lease_instance = self._create_lease_from_unit_spec(unit_spec, unit_index, context)
                    all_models.append(lease_instance)

        return all_models

    def _create_lease_from_unit_spec(
        self, unit_spec: ResidentialUnitSpec, unit_index: int, context: AnalysisContext
    ) -> ResidentialLease:
        """
        ASSEMBLER CORE LOGIC - RESOLVE UUIDS AND INJECT OBJECT REFERENCES
        
        Critical assembler step: lightweight UUID references are resolved
        into direct object references for zero-lookup performance.
        """
        suite_id = f"{unit_spec.unit_type_name}_{unit_index + 1:03d}"
        
        # === UUID RESOLUTION ===
        # Resolve capital plan for THIS turnover
        current_capital_plan = None
        if unit_spec.capital_plan_id:
            current_capital_plan = context.capital_plan_lookup.get(unit_spec.capital_plan_id)
            
        # Resolve next rollover profile for state transitions
        next_rollover_profile = None
        if unit_spec.rollover_profile.next_rollover_profile_id:
            next_rollover_profile = context.rollover_profile_lookup.get(
                unit_spec.rollover_profile.next_rollover_profile_id
            )
        
        # Create lease timeline (for stabilized property, all leases start at analysis start)
        lease_timeline = Timeline(
            start_date=self.timeline.start_date.to_timestamp().date(),
            duration_months=12  # Standard residential lease term
        )
        
        # === OBJECT INJECTION ===
        # Create lease with DIRECT OBJECT REFERENCES (no UUIDs, no lookups)
        lease = ResidentialLease(
            name=f"Resident {suite_id}",
            timeline=lease_timeline,
            status=LeaseStatusEnum.CONTRACT,  # Existing tenant in stabilized property
            area=unit_spec.avg_area_sf,
            suite=suite_id,
            floor="1",  # Simplified - future enhancement could vary by unit
            upon_expiration=UponExpirationEnum.MARKET,  # Standard rollover handling
            monthly_rent=unit_spec.current_avg_monthly_rent,  # Monthly rent in dollars
            value=unit_spec.current_avg_monthly_rent,  # Same as monthly_rent for CashFlowModel
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            frequency=FrequencyEnum.MONTHLY,
            rollover_profile=unit_spec.rollover_profile,
            # DIRECT OBJECT INJECTION - NO LOOKUPS NEEDED AT RUNTIME
            turnover_capital_plan=current_capital_plan,
            next_rollover_profile=next_rollover_profile,
        )
        
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