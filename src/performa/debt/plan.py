"""
Financing Plan - Container for Debt Facilities

This module defines the FinancingPlan which orchestrates a sequence of debt facilities
to support complex financing scenarios like construction-to-permanent workflows.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import Field, computed_field, model_validator

from ..core.primitives import Model
from .construction import ConstructionFacility
from .debt_facility import DebtFacility
from .permanent import PermanentFacility
from .types import AnyDebtFacility


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

    def calculate_refinancing_transactions(self, timeline) -> List[Dict[str, Any]]:
        """
        Calculate refinancing transactions for the financing plan.
        
        This handles transitions between facilities, such as construction-to-permanent
        refinancing where the construction loan is paid off and replaced by permanent financing.
        
        Args:
            timeline: Timeline object for the analysis period
            
        Returns:
            List of refinancing transaction dictionaries with details like:
            - transaction_date: When the refinancing occurs
            - payoff_facility: Facility being paid off
            - new_facility: New facility being originated  
            - payoff_amount: Amount needed to pay off old facility
            - new_loan_amount: Amount of new facility
            - net_proceeds: Net cash to borrower (new loan - payoff)
            
        Raises:
            NotImplementedError: This method requires actual construction loan balances
                which are not yet available. Use get_outstanding_balance() with actual
                financing cash flows from deal analysis.
        """
        transactions = []
        
        # Handle construction-to-permanent refinancing
        if self.has_construction_financing and self.has_permanent_financing:
            construction_facilities = self.construction_facilities
            permanent_facilities = self.permanent_facilities
            
            for const_facility in construction_facilities:
                for perm_facility in permanent_facilities:
                    # Determine refinancing timing
                    if hasattr(perm_facility, 'refinance_timing') and perm_facility.refinance_timing:
                        # Use specified timing
                        refinance_period_index = min(perm_facility.refinance_timing - 1, len(timeline.period_index) - 1)
                        refinance_period = timeline.period_index[refinance_period_index]
                    else:
                        # Default: refinance at end of construction (middle of timeline)
                        refinance_period_index = len(timeline.period_index) // 2
                        refinance_period = timeline.period_index[refinance_period_index]
                    
                    # SAFETY: Prevent unsafe placeholder usage
                    # TODO: Implement refinancing payoff calculation using actual construction loan balances
                    # This requires integration with deal calculator's financing cash flows
                    raise NotImplementedError(
                        "Refinancing payoff calculation requires actual construction loan balances. "
                        "Use ConstructionFacility.get_outstanding_balance() with financing cash flows "
                        "from deal analysis. This prevents using dangerous placeholder values."
                    )
                    
                    # FIXME: Replace with actual payoff calculation when construction cash flows are available:
                    # refinance_date = refinance_period.to_timestamp().date()
                    # estimated_payoff = const_facility.get_outstanding_balance(refinance_date, financing_cash_flows)
                    
                    # Calculate new loan amount
                    if hasattr(perm_facility, 'loan_amount') and perm_facility.loan_amount:
                        new_loan_amount = perm_facility.loan_amount
                    else:
                        # TODO: Calculate new loan amount based on property value and NOI
                        # This requires integration with asset valuation and stabilized NOI
                        raise NotImplementedError(
                            "Permanent loan sizing requires property value and stabilized NOI. "
                            "Use PermanentFacility.calculate_refinance_amount() with actual asset data."
                        )
                    
                    # NOTE: Transaction creation code moved below NotImplementedError to prevent execution
                    # transaction = {
                    #     "transaction_date": refinance_period,
                    #     "transaction_type": "construction_to_permanent_refinancing",
                    #     "payoff_facility": const_facility.kind,
                    #     "new_facility": perm_facility.kind,
                    #     "payoff_amount": estimated_payoff,
                    #     "new_loan_amount": new_loan_amount,
                    #     "net_proceeds": new_loan_amount - estimated_payoff,
                    #     "description": f"Refinance {const_facility.kind} with {perm_facility.kind}"
                    # }
                    # 
                    # transactions.append(transaction)
        
        return transactions 