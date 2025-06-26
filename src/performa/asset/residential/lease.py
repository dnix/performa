from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Dict, Optional

import pandas as pd
from pydantic import Field

from ...common.base import LeaseBase
from ...common.primitives import (
    FrequencyEnum,
    LeaseStatusEnum,
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from .rent_roll import ResidentialUnitSpec
from .rollover import ResidentialRolloverProfile

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext

    from .rollover import ResidentialRolloverLeaseTerms


logger = logging.getLogger(__name__)


class ResidentialLease(LeaseBase):
    """
    Residential lease model for multifamily properties.
    
    Key architectural differences from commercial leases:
    - Simple monthly rent calculation (no complex escalations)
    - No recovery methods (residents don't reimburse expenses)
    - Simple turnover costs (per-unit make-ready and leasing fees)
    - Straightforward rollover logic (renewal % vs market rate)
    
    This model represents a single apartment unit lease and knows how to:
    1. Calculate its own cash flows during the lease term
    2. Handle its own expiration and rollover to the next lease
    3. Create turnover cost models when units turn over
    """
    
    # Residential-specific fields
    rollover_profile: Optional[ResidentialRolloverProfile] = None
    source_spec: Optional[ResidentialUnitSpec] = Field(default=None, exclude=True)
    
    # Simplified defaults for residential
    unit_of_measure: UnitOfMeasureEnum = UnitOfMeasureEnum.CURRENCY  # Monthly rent
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    
    def compute_cf(self, context: "AnalysisContext") -> Dict[str, pd.Series]:
        """
        Compute cash flows for this residential lease term.
        
        Much simpler than commercial leases:
        1. Base monthly rent (already in currency, no complex unit conversions)
        2. Simple abatement (just free months, no complex structures)
        3. No recovery calculations (residential tenants don't reimburse expenses)
        4. No TI/LC during lease term (those are handled at turnover)
        
        Returns:
            Dictionary with rent and abatement cash flow series
        """
        # --- Base Rent Calculation ---
        if isinstance(self.value, (int, float)):
            # Value is monthly rent in dollars
            base_rent = pd.Series(self.value, index=self.timeline.period_index)
        elif isinstance(self.value, pd.Series):
            # Handle variable rent (rare in residential, but supported)
            base_rent = self.value.reindex(self.timeline.period_index, fill_value=0.0)
        else:
            raise TypeError(f"Unsupported rent value type: {type(self.value)}")
        
        # --- Simple Abatement (Free Rent Months) ---
        abatement_cf = pd.Series(0.0, index=self.timeline.period_index)
        
        if self.rent_abatement:
            # Residential abatement is simple: X months free at the beginning
            periods = self.timeline.period_index
            abatement_months = getattr(self.rent_abatement, 'months', 0)
            
            if abatement_months > 0:
                # Apply abatement to first N months of lease
                abatement_mask = periods[:min(abatement_months, len(periods))]
                abatement_amount = base_rent.loc[abatement_mask]
                
                # Reduce base rent for abated months
                base_rent.loc[abatement_mask] = 0.0
                
                # Track abatement amount (negative to show concession)
                abatement_cf.loc[abatement_mask] = -abatement_amount
        
        # Final rent after abatement
        final_rent = base_rent
        
        return {
            "base_rent": final_rent.fillna(0.0),
            "abatement": abatement_cf.fillna(0.0),
            "revenue": final_rent.fillna(0.0),  # Total revenue (no recoveries in residential)
            "net": final_rent.fillna(0.0),     # Net is same as revenue (no TI/LC during term)
        }
    
    def project_future_cash_flows(
        self, context: "AnalysisContext", recursion_depth: int = 0
    ) -> pd.DataFrame:
        """
        Project cash flows for this lease and all subsequent rollovers.
        
        Handles the full lifecycle:
        1. Current lease cash flows 
        2. Turnover costs and downtime when lease expires
        3. Next lease creation based on renewal probability
        4. Recursive projection of future leases
        """
        # Get current lease cash flows
        current_cf_dict = self.compute_cf(context)
        all_cfs = [pd.DataFrame(current_cf_dict)]
        
        lease_end_period = self.timeline.end_date
        analysis_end_period = context.timeline.end_date
        
        # Handle rollover if lease expires before analysis ends
        if self.rollover_profile and lease_end_period < analysis_end_period:
            profile = self.rollover_profile
            action = self.upon_expiration
            
            logger.debug(f"Residential lease '{self.name}' expires {lease_end_period}. "
                        f"Action: {action}. Projecting rollover...")
            
            # Calculate downtime and next lease start
            downtime_months = profile.downtime_months if action in [
                UponExpirationEnum.MARKET, UponExpirationEnum.VACATE
            ] else 0
            
            next_lease_start_date = (
                lease_end_period.to_timestamp() + pd.DateOffset(months=downtime_months + 1)
            ).date()
            
            # Handle downtime period (vacancy loss)
            if downtime_months > 0:
                downtime_start_date = (lease_end_period + 1).start_time.date()
                downtime_timeline = Timeline(
                    start_date=downtime_start_date, 
                    duration_months=downtime_months
                )
                
                # Calculate market rent for vacancy loss
                market_rent = profile._calculate_rent(
                    terms=profile.market_terms,
                    as_of_date=downtime_start_date,
                    global_settings=context.settings
                )
                
                # Create vacancy loss series
                vacancy_loss_series = pd.Series(
                    -market_rent,  # Negative for lost revenue
                    index=downtime_timeline.period_index,
                    name="vacancy_loss"
                )
                all_cfs.append(vacancy_loss_series.to_frame())
            
            # Determine next lease terms based on action
            next_lease_terms = None
            tenant_name = self.name.split(' - ')[0]  # Extract tenant name
            name_suffix = ""
            
            if action == UponExpirationEnum.RENEW:
                next_lease_terms = profile.renewal_terms  
                name_suffix = f" (Renewal {recursion_depth + 1})"
            elif action in [UponExpirationEnum.MARKET, UponExpirationEnum.VACATE]:
                # Use blended terms (combines renewal and market based on probability)
                next_lease_terms = profile.blend_lease_terms()
                tenant_name = f"Resident {self.suite}"  # New tenant
                name_suffix = f" (Rollover {recursion_depth + 1})"
            elif action == UponExpirationEnum.REABSORB:
                logger.debug(f"Lease '{self.name}' set to REABSORB. Stopping projection.")
                # No next lease - unit goes back to market
            
            # Create next lease if applicable
            if (next_lease_terms and 
                pd.Period(next_lease_start_date, freq='M') <= analysis_end_period):
                
                # Calculate next lease rent
                new_rent_rate = profile._calculate_rent(
                    terms=next_lease_terms,
                    as_of_date=next_lease_start_date,
                    global_settings=context.settings
                )
                
                # Create turnover cost models and next lease
                turnover_costs_cf = self._create_turnover_costs(
                    next_lease_terms, next_lease_start_date
                )
                if not turnover_costs_cf.empty:
                    all_cfs.append(turnover_costs_cf.to_frame("turnover_costs"))
                
                # Create speculative next lease
                next_lease = self._create_speculative_lease_instance(
                    start_date=next_lease_start_date,
                    lease_terms=next_lease_terms,
                    rent_rate=new_rent_rate,
                    tenant_name=tenant_name,
                    name_suffix=name_suffix,
                )
                
                logger.debug(f"Created next residential lease '{next_lease.name}' "
                           f"starting {next_lease_start_date} at ${new_rent_rate:.0f}/month")
                
                # Recursively project future cash flows
                future_cf = next_lease.project_future_cash_flows(
                    context, recursion_depth=recursion_depth + 1
                )
                all_cfs.append(future_cf)
        
        # Combine all cash flows
        if not all_cfs:
            return pd.DataFrame(index=context.timeline.period_index).fillna(0)
        
        combined_df = pd.concat(all_cfs, sort=False).fillna(0)
        final_df = combined_df.groupby(combined_df.index).sum()
        
        # Ensure standard columns exist
        standard_columns = ["base_rent", "abatement", "revenue", "net"]
        for col in standard_columns:
            if col not in final_df.columns:
                final_df[col] = 0.0
        
        # Add optional columns if present
        if 'vacancy_loss' not in final_df.columns:
            final_df['vacancy_loss'] = 0.0
        if 'turnover_costs' not in final_df.columns:
            final_df['turnover_costs'] = 0.0
        
        return final_df.reindex(context.timeline.period_index, fill_value=0.0)
    
    def _create_turnover_costs(
        self, 
        lease_terms: "ResidentialRolloverLeaseTerms", 
        start_date: date
    ) -> pd.Series:
        """
        Create turnover cost cash flows for unit make-ready and leasing fees.
        
        Residential turnover costs are simple:
        - Make-ready cost per unit (painting, cleaning, minor repairs)
        - Leasing fee per unit (marketing, showing, application processing)
        
        Both are typically paid in the month before the new lease starts.
        """
        # Calculate total turnover costs
        make_ready_cost = getattr(lease_terms, 'turnover_make_ready_cost_per_unit', 0.0)
        leasing_fee = getattr(lease_terms, 'turnover_leasing_fee_per_unit', 0.0)
        total_turnover_cost = make_ready_cost + leasing_fee
        
        if total_turnover_cost <= 0:
            return pd.Series(dtype=float)
        
        # Costs are typically incurred in the month before lease starts
        cost_date = (pd.Period(start_date, freq='M') - 1).start_time.date()
        cost_period = pd.Period(cost_date, freq='M')
        
        # Create single-period cost series
        return pd.Series(
            [-total_turnover_cost],  # Negative for expense
            index=[cost_period],
            name="turnover_costs"
        )
    
    def _create_speculative_lease_instance(
        self,
        start_date: date,
        lease_terms: "ResidentialRolloverLeaseTerms",
        rent_rate: float,
        tenant_name: str,
        name_suffix: str,
    ) -> "ResidentialLease":
        """
        Create the next lease instance after turnover.
        
        Much simpler than commercial - just basic lease terms:
        - Monthly rent rate
        - Standard 12-month term
        - Same rollover profile for future turnovers
        - Simple concessions (free months)
        """
        # Create timeline for next lease
        term_months = getattr(lease_terms, 'term_months', None) or self.rollover_profile.term_months
        new_timeline = Timeline(start_date=start_date, duration_months=term_months)
        
        # Handle simple concessions (free months)
        rent_abatement = None
        concessions_months = getattr(lease_terms, 'concessions_months', 0)
        if concessions_months > 0:
            # Create simple abatement object for free months
            from ...common.base.lease_components import RentAbatementBase
            
            rent_abatement = RentAbatementBase(
                start_month=1,  # Start from month 1
                months=concessions_months,
                abated_ratio=1.0  # 100% abated (free)
            )
        
        return ResidentialLease(
            name=f"{tenant_name}{name_suffix}",
            timeline=new_timeline,
            status=LeaseStatusEnum.SPECULATIVE,
            area=self.area,
            suite=self.suite,
            floor=self.floor,
            upon_expiration=self.upon_expiration,
            value=rent_rate,  # Monthly rent in dollars
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            frequency=FrequencyEnum.MONTHLY,
            rent_abatement=rent_abatement,
            rollover_profile=self.rollover_profile,
            source_spec=self.source_spec,
            settings=self.settings,
        ) 