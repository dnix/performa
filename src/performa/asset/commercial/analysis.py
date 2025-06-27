from __future__ import annotations

from abc import abstractmethod
from typing import List, Optional

from performa.analysis import AnalysisScenarioBase
from performa.analysis.orchestrator import AnalysisContext
from performa.common.base import LeaseSpecBase
from performa.common.primitives import CashFlowModel


class CommercialAnalysisScenarioBase(AnalysisScenarioBase):
    """
    Base class for commercial asset analysis scenarios with assembler pattern support.
    
    COMMERCIAL ASSEMBLER IMPLEMENTATION
    ====================================
    
    This base class implements the assembler pattern for commercial real estate analysis,
    handling the complexity common to office, retail, and industrial properties.
    
    COMMERCIAL-SPECIFIC FEATURES:
    
    1. CONTEXT PREPARATION
       ===================
       - Recovery method lookup maps (name-based for expense recovery)
       - TI/LC template resolution (UUID to direct object references)
       - Rollover profile management (renewal vs market scenarios)
       - Multi-phase dependency handling for commercial expense structures
    
    2. ASSEMBLER PATTERN IMPLEMENTATION
       =================================
       Assembly time:
       - Resolve recovery method names to objects
       - Resolve capital plan UUIDs to direct references  
       - Populate AnalysisContext with commercial-specific lookup maps
       - Inject direct references into lease and expense models
       
       Runtime:
       - Direct attribute access (context.recovery_method_lookup[name])
       - No UUID resolution overhead during cash flow calculations
    
    3. COMMERCIAL MODELING SUPPORT
       ============================
       - Expense recovery calculations (base year, net, gross-up)
       - Tenant improvement and leasing commission modeling
       - Complex rollover scenarios with state transitions
       - Multi-tenant lease structure support
    
    COMPATIBILITY:
    - Maintains backward compatibility with existing commercial models
    - Supports single tenant through multi-tenant properties
    - Enables scenario modeling for commercial portfolios
    - No breaking changes to existing analysis workflows
    
    This foundation supports office, retail, and industrial analysis scenarios
    while maintaining the modeling capabilities required for commercial real estate analysis.
    """
    
    @abstractmethod
    def _create_lease_from_spec(self, spec: LeaseSpecBase, context: Optional[AnalysisContext] = None) -> CashFlowModel:
        """
        Abstract method for creating a lease from a spec.
        
        Args:
            spec: The lease specification to create a lease from
            context: Optional AnalysisContext for object injection and UUID resolution
            
        Returns:
            CashFlowModel instance representing the lease
        """
        pass

    @abstractmethod
    def _create_misc_income_models(self, context: Optional[AnalysisContext] = None) -> List[CashFlowModel]:
        """
        Abstract method for creating miscellaneous income models.
        
        Args:
            context: Optional AnalysisContext for enhanced performance
            
        Returns:
            List of miscellaneous income CashFlowModel instances
        """
        pass

    @abstractmethod
    def _create_expense_models(self, context: Optional[AnalysisContext] = None) -> List[CashFlowModel]:
        """
        Abstract method for creating expense models.
        
        Args:
            context: Optional AnalysisContext for enhanced performance
            
        Returns:
            List of expense CashFlowModel instances
        """
        pass

    def prepare_models(self, context: Optional[AnalysisContext] = None) -> List[CashFlowModel]:
        """
        Prepares all cash flow models for the analysis with enhanced context support.
        
        ASSEMBLER PATTERN IMPLEMENTATION:
        When context is provided, this method can perform UUID resolution and
        object injection for maximum runtime performance. When context is None,
        falls back to legacy behavior for backward compatibility.
        
        Args:
            context: Optional AnalysisContext containing pre-built lookup maps
            
        Returns:
            List of all CashFlowModel instances for the analysis
        """
        all_models: List[CashFlowModel] = []

        # 1. Leases from Rent Roll
        if hasattr(self.model, "rent_roll") and self.model.rent_roll:
            for lease_spec in self.model.rent_roll.leases:
                lease_model = self._create_lease_from_spec(lease_spec, context)
                all_models.append(lease_model)
                
                # Also add the TI and LC models if they exist
                # These are typically created by the lease during construction
                if hasattr(lease_model, 'ti_allowance') and lease_model.ti_allowance:
                    all_models.append(lease_model.ti_allowance)
                if hasattr(lease_model, 'leasing_commission') and lease_model.leasing_commission:
                    all_models.append(lease_model.leasing_commission)
            
            # TODO: Handle vacant suite absorption modeling with context support

        # 2. Miscellaneous Income
        if hasattr(self.model, "miscellaneous_income"):
            all_models.extend(self._create_misc_income_models(context))

        # 3. Expenses
        all_models.extend(self._create_expense_models(context))

        return all_models
