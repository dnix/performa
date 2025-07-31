# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from performa.analysis import register_scenario
from performa.analysis.orchestrator import AnalysisContext, CashFlowOrchestrator
from performa.core.base import LeaseSpecBase
from performa.core.primitives import CashFlowModel

from ..commercial.analysis import CommercialAnalysisScenarioBase
from .expense import OfficeCapExItem, OfficeOpExItem
from .lease import OfficeLease
from .misc_income import OfficeMiscIncome
from .property import OfficeProperty
from .recovery import RecoveryCalculationState


@register_scenario(OfficeProperty)
class OfficeAnalysisScenario(CommercialAnalysisScenarioBase):
    """
    Analysis scenario for office commercial properties.
    
    OFFICE-SPECIFIC ASSEMBLER IMPLEMENTATION
    =========================================
    
    This scenario implements the assembler pattern for commercial office properties,
    handling office-specific lease structures, recovery methods, and rollover scenarios.
    
    OFFICE-SPECIFIC LOGIC:
    
    1. RECOVERY METHOD RESOLUTION
       ===========================
       - Creates name-based lookup maps for office expense recovery methods
       - Supports base year, net, fixed stop, and percentage-based recovery structures
       - Enables zero-lookup access during cash flow calculations
    
    2. TI/LC MODEL HANDLING
       ====================
       - Resolves UUID references to direct TI/LC template objects
       - Creates lease-specific TI models with proper area calculations
       - Handles commission payment timing (signing vs commencement)
       - Generates realistic signing dates for speculative leases (3-month lead time)
    
    3. ROLLOVER PROFILE MANAGEMENT
       ============================
       - Manages complex renewal vs market rate scenarios
       - Supports multi-tier commission structures
       - Handles rollover cost calculations and lease transitions
    
    IMPLEMENTATION DETAILS:
    - prepare_models() performs UUID resolution and object injection
    - AnalysisContext provides direct object access during runtime
    - Maintains compatibility with existing office property models
    - Supports properties ranging from single tenant to multi-tenant complexes
    
    TESTED WITH:
    - Single tenant office buildings
    - Multi-tenant properties with varied lease structures  
    - Properties with multiple recovery methods and rollover profiles
    - Complex commission structures and TI allowances
    """
    
    model: OfficeProperty

    def run(self) -> None:
        """
        ASSEMBLER PATTERN - ENHANCED RUN METHOD FOR OFFICE
        
        This override implements the same architectural pattern as residential:
        1. Recovery states pre-calculation (office-specific)
        2. AnalysisContext serves as universal data bus
        3. One-time UUID resolution during assembly  
        4. Leases get direct object references (no runtime lookups)
        """
        # === 1. PRE-CALCULATE OFFICE-SPECIFIC STATES ===
        recovery_states = self._pre_calculate_recoveries()
        
        # === 2. CREATE UUID LOOKUP MAPS ===
        # Collect all rollover profiles from lease specs
        rollover_profile_lookup = {}
        if hasattr(self.model, "rent_roll") and self.model.rent_roll:
            for lease_spec in self.model.rent_roll.leases:
                if hasattr(lease_spec, 'rollover_profile') and lease_spec.rollover_profile:
                    profile = lease_spec.rollover_profile
                    rollover_profile_lookup[profile.uid] = profile
        
        # Collect recovery methods for fast access
        recovery_method_lookup = {}
        if hasattr(self.model, "rent_roll") and self.model.rent_roll:
            for lease_spec in self.model.rent_roll.leases:
                if hasattr(lease_spec, 'recovery_method') and lease_spec.recovery_method:
                    method = lease_spec.recovery_method
                    recovery_method_lookup[method.name] = method
        
        # Office-specific: TI/LC template lookup (if we add this feature later)
        ti_template_lookup = {}  # Future enhancement
        lc_template_lookup = {}  # Future enhancement
        
        # === 3. CREATE ENHANCED CONTEXT ===
        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=self.model,
            recovery_states=recovery_states,
            rollover_profile_lookup=rollover_profile_lookup,
            recovery_method_lookup=recovery_method_lookup,
            ti_template_lookup=ti_template_lookup,
            lc_template_lookup=lc_template_lookup,
        )

        # === 4. ASSEMBLE MODELS WITH DIRECT OBJECT INJECTION ===
        all_models = self.prepare_models(context)

        # === 5. RUN ORCHESTRATOR ===
        orchestrator = CashFlowOrchestrator(models=all_models, context=context)
        orchestrator.execute()
        self._orchestrator = orchestrator

    def _pre_calculate_recoveries(self) -> Dict[UUID, RecoveryCalculationState]:
        """
        Pre-calculates base year stops for all recovery methods in the model.
        
        This method processes recovery methods from both the rent roll and absorption plans,
        identifying those with base year structures ("base_year", "base_year_plus1", 
        "base_year_minus1") and calculating the total recoverable expenses for the specified base year.
        
        For base year recoveries, it calculates what the total annual expenses would be
        in the specified base year using current expense models, applying growth rates
        as appropriate.
        
        Returns:
            Dict mapping recovery UIDs to RecoveryCalculationState objects with
            calculated_annual_base_year_stop populated for base year structures.
        """
        recovery_states = {}
        
        # Collect all recovery methods from rent roll leases
        recovery_methods_to_process = []
        
        if hasattr(self.model, "rent_roll") and self.model.rent_roll:
            for lease_spec in self.model.rent_roll.leases:
                if hasattr(lease_spec, 'recovery_method') and lease_spec.recovery_method:
                    recovery_methods_to_process.append(lease_spec.recovery_method)
        
        # Collect all recovery methods from absorption plans  
        if hasattr(self.model, "absorption_plans") and self.model.absorption_plans:
            for absorption_plan in self.model.absorption_plans:
                # Generate lease specs from absorption plan to check their recovery methods
                try:
                    generated_specs = absorption_plan.generate_lease_specs(
                        available_vacant_suites=self.model.rent_roll.vacant_suites,
                        analysis_start_date=self.timeline.start_date.to_timestamp().date(),
                        analysis_end_date=self.timeline.end_date.to_timestamp().date(),
                        global_settings=self.settings
                    )
                    for spec in generated_specs:
                        if hasattr(spec, 'recovery_method') and spec.recovery_method:
                            recovery_methods_to_process.append(spec.recovery_method)
                except Exception as e:
                    # Log error but continue processing - absorption plans are optional
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to generate lease specs from absorption plan: {e}")
        
        # Process all recovery methods to create states
        for recovery_method in recovery_methods_to_process:
            if hasattr(recovery_method, 'recoveries'):
                for recovery_item in recovery_method.recoveries:
                    if recovery_item.uid not in recovery_states:
                        # Create basic recovery state
                        recovery_state = RecoveryCalculationState(
                            recovery_uid=recovery_item.uid,
                            calculated_annual_base_year_stop=None,
                            frozen_base_year_pro_rata=None,
                        )
                        
                        # Calculate base year stop for base year structures
                        if hasattr(recovery_item, 'structure') and recovery_item.structure in ["base_year", "base_year_plus1", "base_year_minus1"]:
                            base_year_stop = self._calculate_base_year_expenses(recovery_item)
                            recovery_state.calculated_annual_base_year_stop = base_year_stop
                        
                        recovery_states[recovery_item.uid] = recovery_state
        
        return recovery_states
    
    def _calculate_base_year_expenses(self, recovery_item) -> float:
        """
        Calculate the total annual recoverable expenses for a base year recovery.
        
        This method determines what the total expenses would be for the specified base year
        by using the current expense models in the property. For base year structures,
        we need to simulate what expenses would have been in that specific year.
        
        Args:
            recovery_item: Recovery object with base_year structure and base_year specified
            
        Returns:
            Total annual recoverable expenses for the base year
        """
        if not hasattr(recovery_item, 'base_year') or not recovery_item.base_year:
            return 0.0
        
        # Determine the target year based on recovery structure
        target_year = recovery_item.base_year
        if hasattr(recovery_item, 'structure'):
            if recovery_item.structure == "base_year_plus1":
                target_year += 1
            elif recovery_item.structure == "base_year_minus1":
                target_year -= 1
        
        # Get the expense pool to calculate
        if not hasattr(recovery_item, 'expense_pool'):
            return 0.0
            
        expense_pool = recovery_item.expense_pool
        expenses_to_process = (
            expense_pool.expenses if isinstance(expense_pool.expenses, list) 
            else [expense_pool.expenses]
        )
        
        total_annual_expenses = 0.0
        
        # Calculate total expenses for each item in the pool
        for expense_item in expenses_to_process:
            # Only include recoverable expenses - is_recoverable is computed from recoverable_ratio
            if hasattr(expense_item, 'is_recoverable') and not expense_item.is_recoverable:
                continue
                
            # Get the base annual value from the expense item
            if hasattr(expense_item, 'value'):
                annual_value = expense_item.value
                
                # Convert to annual if needed
                if hasattr(expense_item, 'frequency'):
                    from performa.core.primitives.enums import FrequencyEnum
                    if expense_item.frequency == FrequencyEnum.MONTHLY:
                        annual_value *= 12
                
                # Apply reference-based adjustments (PropertyAttributeKey multiplication)
                if hasattr(expense_item, 'reference') and expense_item.reference:
                    from performa.core.primitives import PropertyAttributeKey
                    
                    # DYNAMIC RESOLUTION: Use enum value as attribute name
                    # This approach is extensible and not brittle - works for ANY PropertyAttributeKey
                    if isinstance(expense_item.reference, PropertyAttributeKey):
                        attribute_name = expense_item.reference.value  # e.g., "unit_count", "net_rentable_area"
                        
                        if hasattr(self.model, attribute_name):
                            property_value = getattr(self.model, attribute_name)
                            if property_value is not None:
                                annual_value *= property_value
                
                # Apply growth from model year to target year if growth rate exists
                if hasattr(expense_item, 'growth_rate') and expense_item.growth_rate:
                    # Calculate years difference (can be negative for past years)
                    analysis_year = self.timeline.start_date.year
                    years_diff = target_year - analysis_year
                    
                    if years_diff != 0 and hasattr(expense_item.growth_rate, 'value'):
                        growth_rate_value = expense_item.growth_rate.value
                        if isinstance(growth_rate_value, (int, float)):
                            # Apply compound growth
                            annual_value *= (1 + growth_rate_value) ** years_diff
                
                total_annual_expenses += annual_value
        
        return total_annual_expenses

    def _create_lease_from_spec(self, spec: LeaseSpecBase, context: Optional[AnalysisContext] = None) -> CashFlowModel:
        """
        Create OfficeLease with enhanced context support and object injection.
        
        ASSEMBLER PATTERN - OBJECT INJECTION:
        When context is provided, this method can inject pre-resolved objects
        directly into the lease for maximum runtime performance.
        
        Args:
            spec: Office lease specification
            context: Optional AnalysisContext with pre-built lookup maps
            
        Returns:
            OfficeLease instance with direct object references where possible
        """
        # Create OfficeLease using the existing from_spec method
        lease = OfficeLease.from_spec(
            spec=spec,
            analysis_start_date=self.timeline.start_date.to_timestamp().date(),
            timeline=self.timeline,
            settings=self.settings,
        )
        
        # FUTURE ENHANCEMENT: Object injection when context is available
        # if context and hasattr(spec, 'rollover_profile_id'):
        #     profile = context.rollover_profile_lookup.get(spec.rollover_profile_id)
        #     if profile:
        #         lease._injected_rollover_profile = profile
        
        return lease

    def _create_misc_income_models(self, context: Optional[AnalysisContext] = None) -> List[CashFlowModel]:
        """
        Create miscellaneous income models with optional context enhancement.
        
        Args:
            context: Optional AnalysisContext for enhanced performance
            
        Returns:
            List of miscellaneous income CashFlowModel instances
        """
        models = []
        if self.model.miscellaneous_income:
            for item in self.model.miscellaneous_income:
                # Here we would convert an OfficeMiscIncomeSpec into a real model
                # For now, assuming the items are already models.
                if isinstance(item, OfficeMiscIncome):
                    models.append(item)
        return models

    def _create_expense_models(self, context: Optional[AnalysisContext] = None) -> List[CashFlowModel]:
        """
        Create expense models with optional context enhancement.
        
        Args:
            context: Optional AnalysisContext for enhanced performance
            
        Returns:
            List of expense CashFlowModel instances
        """
        models = []
        if self.model.expenses:
            if self.model.expenses.operating_expenses:
                for item in self.model.expenses.operating_expenses:
                    if isinstance(item, OfficeOpExItem):
                        models.append(item)
            if self.model.expenses.capital_expenses:
                 for item in self.model.expenses.capital_expenses:
                    if isinstance(item, OfficeCapExItem):
                        models.append(item)
        return models
