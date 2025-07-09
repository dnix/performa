from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pandas as pd
from pydantic import Field, computed_field, field_validator

from ...core.base import LeaseBase
from ...core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    Model,
    PositiveFloat,
    PositiveInt,
    Timeline,
    UnitOfMeasureEnum,
)

if TYPE_CHECKING:
    from ...analysis import AnalysisContext
    from ...core.capital import CapitalPlan
    from .rollover import ResidentialRolloverLeaseTerms, ResidentialRolloverProfile

logger = logging.getLogger(__name__)


class ResidentialLease(LeaseBase):
    """
    Lease model for residential units implementing the assembler pattern.
    
    RESIDENTIAL LEASE DESIGN
    ========================
    
    This model focuses on rent cash flow generation while delegating complex business
    logic to appropriate architectural layers for better separation of concerns.
    
    ARCHITECTURAL APPROACH:
    
    1. LEASE RESPONSIBILITIES
       ======================
       - Monthly rent cash flow generation
       - Simple state transitions via direct object references
       - Runtime calculations with pre-resolved references
    
    2. DELEGATED LOGIC
       ===============
       - Value-add renovation logic → ResidentialRolloverProfile.effective_market_rent
       - Capital plan execution → CapitalPlan primitive  
       - Blended rollover terms → ResidentialRolloverProfile.blend_lease_terms()
       - UUID resolution → ResidentialAnalysisScenario.prepare_models()
       - State transitions → rollover profile definitions
    
    3. ASSEMBLER PATTERN USAGE
       ========================
       Assembly time:
       - AnalysisScenario resolves UUIDs to direct object references
       - Populates turnover_capital_plan and next_rollover_profile fields
       
       Runtime:
       - Direct attribute access (no UUID lookups)
       - Simple monthly rent calculation
    
    RESIDENTIAL-SPECIFIC FEATURES:
    - Monthly rent payments (no complex escalation schedules)
    - No recovery methods (residents don't pay building expenses)
    - CapitalPlan integration for turnover costs and renovations
    - Renewal vs market rate logic via rollover profiles
    
    VALUE-ADD CAPABILITIES:
    All residential modeling features remain functional through proper delegation:
    - Post-renovation rent premiums via rollover profile logic
    - Capital plan execution via injected references
    - State transitions via next_rollover_profile
    """
    
    # === BASIC LEASE TERMS ===
    monthly_rent: PositiveFloat  # Base monthly rent
    rollover_profile: Optional[ResidentialRolloverProfile] = None
    
    # === RUNTIME OBJECT REFERENCES (Injected by Assembler) ===
    # These hold direct object references, passed in by the AnalysisScenario.
    # They are for runtime use and not part of the input specification.
    turnover_capital_plan: Optional["CapitalPlan"] = Field(
        default=None, 
        exclude=True,
        description="Direct reference to capital plan for THIS turnover (injected by assembler)"
    )
    next_rollover_profile: Optional[ResidentialRolloverProfile] = Field(
        default=None,
        exclude=True, 
        description="Direct reference to rollover profile for NEXT turnover (enables state transitions)"
    )
    
    # Override base class defaults for residential
    unit_of_measure: UnitOfMeasureEnum = UnitOfMeasureEnum.CURRENCY
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    
    @field_validator('value', mode='before')
    @classmethod
    def set_value_from_monthly_rent(cls, v, info):
        """Set value field from monthly_rent if not explicitly provided."""
        if v is None and 'monthly_rent' in info.data:
            return info.data['monthly_rent']
        return v
    
    def compute_cf(self, context: "AnalysisContext") -> Dict[str, pd.Series]:
        """
        Calculate cash flows for this residential lease.
        
        Returns cash flows in the expected component structure:
        - base_rent: Monthly rent payments → maps to POTENTIAL_GROSS_REVENUE
        """
        # Create basic rent series over the lease timeline
        rent_series = pd.Series(
            self.monthly_rent,
            index=self.timeline.period_index,
            name=f"{self.name}_rent"
        )
        
        # Return in component dictionary format expected by orchestrator
        return {
            "base_rent": rent_series
        }
    
    def project_future_cash_flows(self, context: "AnalysisContext") -> pd.DataFrame:
        """
        Project lease cash flows and handle state transitions.
        
        PURE STATE MACHINE ARCHITECTURE:
        1. Generate current lease rent stream
        2. Execute capital plan for THIS turnover (if any)
        3. Create next speculative lease with NEW state (rollover profile)
        4. The next lease automatically has correct behavior baked in
        
        No mutable flags, no state tracking - state is the TYPE of rollover profile.
        
        Returns:
            DataFrame with aggregated cash flows from current lease + future leases + capital plans
            Columns must match orchestrator's expected component names for proper aggregation
        """
        all_dfs = []
        
        # Add current lease cash flow with correct component naming
        current_cf = self.compute_cf(context)
        if current_cf and "base_rent" in current_cf:
            # Convert to DataFrame with proper component column naming
            current_df = pd.DataFrame({
                "base_rent": current_cf["base_rent"]
            })
            all_dfs.append(current_df)

        # For the initial lease period, we only want current lease cash flows
        # Future lease transitions will be handled by subsequent lease instances
        # This prevents double-counting in the first month
        
        # Note: Rollover logic is handled when lease instances are created by the assembler
        # Each lease represents its own period, not future speculative periods

        # Combine all DataFrames
        if all_dfs:
            # For residential leases, we typically only have current lease cash flows
            result_df = all_dfs[0]
            return result_df
        else:
            # Return empty DataFrame with correct index
            return pd.DataFrame(index=self.timeline.period_index)
    
    def _create_speculative_lease_instance(
        self, context: "AnalysisContext"
    ) -> Optional["ResidentialLease"]:
        """
        Create the next lease instance with proper state transition.
        
        PURE STATE MACHINE LOGIC:
        1. Get blended lease terms from current rollover profile
        2. Determine next rent (with any renovation premiums)
        3. Create new lease with NEXT rollover profile (state transition)
        4. The new lease has its future behavior baked in
        
        Returns:
            New ResidentialLease instance with transitioned state, or None if no transition
        """
        if not self.rollover_profile:
            return None
            
        # Calculate timeline for next lease
        downtime_months = self.rollover_profile.downtime_months
        next_start_date = (self.timeline.end_date + 1 + downtime_months).start_time.date()
        
        # Check if new lease starts within analysis timeline
        analysis_end_date = context.timeline.end_date.to_timestamp().date()
        if next_start_date > analysis_end_date:
            return None
            
        # Get blended lease terms
        blended_terms = self.rollover_profile.blend_lease_terms()
        
        # Calculate next rent (including any post-renovation premiums)
        next_rent = blended_terms.effective_market_rent
        
        # Create timeline for next lease
        next_timeline = Timeline(
            start_date=next_start_date,
            duration_months=blended_terms.term_months or 12
        )
        
        # Determine next state (rollover profile for future turnovers)
        # This is the key to the state machine: the NEXT lease gets a different profile
        next_profile = self.next_rollover_profile  # Direct object reference
        
        # Determine capital plan for the NEXT turnover (not this one)
        next_capital_plan = None
        if next_profile and next_profile.market_terms.capital_plan_id:
            next_capital_plan = context.capital_plan_lookup.get(next_profile.market_terms.capital_plan_id)
        
        return ResidentialLease(
            name=f"Speculative Lease - {self.name}",
            timeline=next_timeline,
            status=self.status,  # Copy status
            area=self.area,  # Copy area
            suite=self.suite,  # Copy suite
            floor=self.floor,  # Copy floor
            upon_expiration=self.upon_expiration,  # Copy expiration handling
            monthly_rent=next_rent,
            value=next_rent,  # Same as monthly_rent for CashFlowModel
            unit_of_measure=self.unit_of_measure,
            frequency=self.frequency,
            rollover_profile=next_profile,  # STATE TRANSITION: New profile defines new behavior
            turnover_capital_plan=next_capital_plan,  # Capital plan for NEXT turnover
            next_rollover_profile=next_profile,  # Could transition again if needed
        ) 