# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Optional

import pandas as pd
from pydantic import field_validator

from ...core.base import LeaseBase
from ...core.primitives import (
    FrequencyEnum,
    PositiveFloat,
    Timeline,
    UponExpirationEnum,
)

if TYPE_CHECKING:
    from ...analysis import AnalysisContext
    from .rollover import ResidentialRolloverProfile

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
       - Rent calculations → ResidentialRolloverLeaseTerms.market_rent
       - Capital plan management → Property-level CapitalPlan primitives
       - Blended rollover terms → ResidentialRolloverProfile.blend_lease_terms()
       - UUID resolution → ResidentialAnalysisScenario.prepare_models()
       - State transitions → rollover profile definitions

    3. ASSEMBLER PATTERN USAGE
       ========================
       Assembly time:
       - AnalysisScenario resolves UUIDs to direct object references
       - Resolves rollover profile references for renewal calculations

       Runtime:
       - Direct attribute access (no UUID lookups)
       - Simple monthly rent calculation

    RESIDENTIAL-SPECIFIC FEATURES:
    - Monthly rent payments (no complex escalation schedules)
    - No recovery methods (residents don't pay building expenses)
    - State machine rollover logic for rent transitions
    - Renewal vs market rate logic via rollover profiles

    ADVANCED CAPABILITIES:
    All residential modeling features work through proper delegation:
    - Rent premiums via rollover profile logic
    - Capital plan management via property-level primitives
    - Rollover calculations via rollover profile logic
    """

    # === BASIC LEASE TERMS ===
    monthly_rent: PositiveFloat  # Base monthly rent
    rollover_profile: Optional[ResidentialRolloverProfile] = None

    # === RUNTIME OBJECT REFERENCES (Injected by Assembler) ===
    # These hold direct object references, passed in by the AnalysisScenario.
    # They are for runtime use and not part of the input specification.

    # Override base class defaults for residential rent
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY

    @field_validator("value", mode="before")
    @classmethod
    def set_value_from_monthly_rent(cls, v, info):
        """Set value field from monthly_rent if not explicitly provided."""
        if v is None and "monthly_rent" in info.data:
            return info.data["monthly_rent"]
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
            name=f"{self.name}_rent",
        )

        # Return in component dictionary format expected by orchestrator
        return {"base_rent": rent_series}

    def project_future_cash_flows(self, context: "AnalysisContext") -> pd.DataFrame:
        """
        Project lease cash flows and handle state transitions.

        Generates the complete lease lifecycle cash flows:
        1. Current lease rent stream
        2. Speculative future lease with rollover profile state transitions
        3. Recursive projection of subsequent lease periods

        Returns:
            DataFrame with aggregated cash flows from current lease + future lease rollovers
            Columns must match orchestrator's expected component names for proper aggregation
        """
        all_dfs = []

        # Add current lease cash flow with correct component naming
        current_cf = self.compute_cf(context)
        if current_cf and "base_rent" in current_cf:
            # Convert to DataFrame with proper component column naming
            current_df = pd.DataFrame({"base_rent": current_cf["base_rent"]})
            all_dfs.append(current_df)

        # Create speculative lease for future periods if this lease expires within timeline
        if self.rollover_profile and self.timeline.end_date < context.timeline.end_date:
            try:
                # ITERATIVE ROLLOVER: Process all renewals iteratively instead of recursively
                # This maintains correctness while avoiding deep recursion performance issues
                current_lease = self
                renewal_count = 0
                max_renewals = 50  # Safety limit to prevent infinite loops

                while (
                    current_lease.rollover_profile
                    and current_lease.timeline.end_date < context.timeline.end_date
                    and renewal_count < max_renewals
                ):
                    next_lease = current_lease._create_speculative_lease_instance(
                        context
                    )
                    if not next_lease:
                        break

                    # Add cash flows from this renewal period only (not recursive)
                    next_cf = next_lease.compute_cf(context)
                    if next_cf and "base_rent" in next_cf:
                        next_df = pd.DataFrame({"base_rent": next_cf["base_rent"]})
                        all_dfs.append(next_df)

                    current_lease = next_lease
                    renewal_count += 1

            except Exception as e:
                # Log the error but continue with current lease cash flows
                logger.warning(
                    f"Failed to create speculative lease for {self.name}: {e}"
                )

        # Combine all DataFrames
        if all_dfs:
            # Concatenate all lease periods with proper index alignment
            combined_df = pd.concat(all_dfs, axis=0, sort=True)

            # Group by period and sum (in case of overlapping periods)
            combined_df = combined_df.groupby(combined_df.index).sum()

            # Ensure we have the full analysis timeline
            full_index = context.timeline.period_index
            result_df = combined_df.reindex(full_index, fill_value=0.0)

            return result_df
        else:
            # Return empty DataFrame with correct index
            return pd.DataFrame(index=context.timeline.period_index)

    def _create_speculative_lease_instance(
        self, context: "AnalysisContext"
    ) -> Optional["ResidentialLease"]:
        """
        Create the next lease instance for rollover scenarios.

        ROLLOVER LOGIC:
        1. Get blended lease terms from current rollover profile
        2. Determine next rent (with any market adjustments)
        3. Create new lease instance for the next lease term

        Returns:
            New ResidentialLease instance for the next term, or None if rollover is outside timeline
        """
        if not self.rollover_profile:
            return None

        # Calculate timeline for next lease
        downtime_months = self.rollover_profile.downtime_months
        next_start_date = (
            self.timeline.end_date + 1 + downtime_months
        ).start_time.date()

        # Check if new lease starts within analysis timeline
        analysis_end_date = context.timeline.end_date.to_timestamp().date()
        if next_start_date > analysis_end_date:
            return None

        # Determine lease terms based on upon_expiration behavior (like office module)
        action = self.upon_expiration
        profile = self.rollover_profile

        if action == UponExpirationEnum.RENEW:
            # Tenant renews → Use renewal terms directly
            lease_terms = profile.renewal_terms
        elif action == UponExpirationEnum.VACATE:
            # Tenant vacates → New tenant at market terms
            lease_terms = profile.market_terms
        elif action == UponExpirationEnum.MARKET:
            # Probabilistic outcome → Use blended terms
            lease_terms = profile.blend_lease_terms()
        elif action == UponExpirationEnum.REABSORB:
            # Stop generating leases (end of useful life, major renovation, etc.)
            return None
        else:
            # Default fallback to blended terms
            lease_terms = profile.blend_lease_terms()

        # Calculate next rent based on chosen terms
        next_rent = lease_terms.market_rent

        # === LEASE TERM CONFIGURATION ===
        # Use lease term from chosen terms, or fallback to rollover profile default
        lease_term_months = lease_terms.term_months or self.rollover_profile.term_months

        # Create timeline for next lease
        next_timeline = Timeline(
            start_date=next_start_date, duration_months=lease_term_months
        )

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
            reference=self.reference,  # Copy reference attribute for cash flow modeling
            frequency=self.frequency,
            rollover_profile=self.rollover_profile,  # Continue with same rollover profile
        )
