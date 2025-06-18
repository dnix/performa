from __future__ import annotations

from typing import Any, Dict, List, Union
from uuid import UUID

from performa.analysis import register_scenario
from performa.common.base import LeaseSpecBase
from performa.common.primitives import CashFlowModel

from ..commercial.analysis import CommercialAnalysisScenarioBase
from .expense import OfficeCapExItem, OfficeOpExItem
from .lease import OfficeLease
from .misc_income import OfficeMiscIncome
from .property import OfficeProperty
from .recovery import RecoveryCalculationState


@register_scenario(OfficeProperty)
class OfficeAnalysisScenario(CommercialAnalysisScenarioBase):
    model: OfficeProperty

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
                if lease_spec.recovery_method:
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
                        if spec.recovery_method:
                            recovery_methods_to_process.append(spec.recovery_method)
                except Exception as e:
                    # Log error but continue processing - absorption plans are optional
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to generate lease specs from absorption plan: {e}")
        
        # Process all recovery methods to create states
        for recovery_method in recovery_methods_to_process:
            for recovery_item in recovery_method.recoveries:
                if recovery_item.uid not in recovery_states:
                    # Create basic recovery state
                    recovery_state = RecoveryCalculationState(
                        recovery_uid=recovery_item.uid,
                        calculated_annual_base_year_stop=None,
                        frozen_base_year_pro_rata=None,
                    )
                    
                    # Calculate base year stop for base year structures
                    if recovery_item.structure in ["base_year", "base_year_plus1", "base_year_minus1"]:
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
        if not recovery_item.base_year:
            return 0.0
        
        # Determine the target year based on recovery structure
        target_year = recovery_item.base_year
        if recovery_item.structure == "base_year_plus1":
            target_year += 1
        elif recovery_item.structure == "base_year_minus1":
            target_year -= 1
        
        # Get the expense pool to calculate
        expense_pool = recovery_item.expense_pool
        expenses_to_process = (
            expense_pool.expenses if isinstance(expense_pool.expenses, list) 
            else [expense_pool.expenses]
        )
        
        total_annual_expenses = 0.0
        
        # Calculate total expenses for each item in the pool
        for expense_item in expenses_to_process:
            # Only include recoverable expenses - is_recoverable is computed from recoverable_ratio
            if not expense_item.is_recoverable:
                continue
                
            # Get the base annual value from the expense item
            if hasattr(expense_item, 'value'):
                annual_value = expense_item.value
                
                # Convert to annual if needed
                if hasattr(expense_item, 'frequency'):
                    from performa.common.primitives.enums import FrequencyEnum
                    if expense_item.frequency == FrequencyEnum.MONTHLY:
                        annual_value *= 12
                
                # Apply unit of measure adjustments
                if hasattr(expense_item, 'unit_of_measure'):
                    from performa.common.primitives.enums import UnitOfMeasureEnum
                    if expense_item.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
                        # Multiply by property area for per-unit expenses
                        annual_value *= self.model.net_rentable_area
                
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

    def _create_lease_from_spec(self, spec: LeaseSpecBase) -> CashFlowModel:
        # Create OfficeLease directly from spec using attached objects
        return OfficeLease.from_spec(
            spec=spec,
            analysis_start_date=self.timeline.start_date.to_timestamp().date(),
            timeline=self.timeline,
            settings=self.settings,
        )

    def _create_misc_income_models(self) -> List[CashFlowModel]:
        models = []
        if self.model.miscellaneous_income:
            for item in self.model.miscellaneous_income:
                # Here we would convert an OfficeMiscIncomeSpec into a real model
                # For now, assuming the items are already models.
                if isinstance(item, OfficeMiscIncome):
                    models.append(item)
        return models

    def _create_expense_models(self) -> List[CashFlowModel]:
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

    def run(self) -> None:
        # Pre-calculate office-specific states before running the main analysis
        self._recovery_states = self._pre_calculate_recoveries()
        super().run()
