"""
Residential Absorption Plan - Unit-Based Lease-Up Modeling

This module defines the logic for modeling the lease-up of vacant residential units
in multifamily developments. It mirrors the office absorption framework but is
adapted for the unit-centric paradigm of residential real estate.

Key Differences from Office Absorption:
- Unit-based rather than area-based (lease 10 units vs 10,000 SF)
- Works with ResidentialVacantUnit objects
- Creates ResidentialUnitSpec results rather than lease specs
- Handles unit mix and unit type variations
- No subdivision logic (units are atomic)

The core components are:
- **ResidentialAbsorptionPlan**: Main entry point for residential lease-up scenarios
- **Unit-Based Pace Models**: Same pace concepts but measured in units
- **Residential Pace Strategies**: Logic adapted for unit absorption
"""

# FIXME: revisit for subdivision logic

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, List, Optional, Union
from uuid import UUID

from pydantic import Field

from ...core.base import (
    AbsorptionPlanBase,
    CustomSchedulePace,
    DirectLeaseTerms,
    EqualSpreadPace,
    FixedQuantityPace,
    PaceContext,
    SpaceFilter,
)
from ...core.primitives import (
    GlobalSettings,
    StartDateAnchorEnum,
)
from .rent_roll import ResidentialUnitSpec, ResidentialVacantUnit
from .rollover import ResidentialRolloverLeaseTerms, ResidentialRolloverProfile

logger = logging.getLogger(__name__)


class ResidentialUnitFilter(SpaceFilter):
    """
    Defines criteria to filter which vacant residential units are included
    in an absorption plan. Extends the base SpaceFilter for residential context.
    """
    unit_types: Optional[List[str]] = Field(
        default=None, 
        description="Filter by unit type names (e.g., 'Studio', '1BR', '2BR')"
    )
    min_rent: Optional[float] = Field(
        default=None,
        description="Minimum market rent filter"
    )
    max_rent: Optional[float] = Field(
        default=None, 
        description="Maximum market rent filter"
    )

    def matches(self, unit: ResidentialVacantUnit) -> bool:
        """Check if a vacant unit matches the filter criteria."""
        # First check base criteria (use_type, etc.)
        if not super().matches(unit):
            return False
        
        # Check residential-specific criteria
        if self.unit_types and unit.unit_type_name not in self.unit_types:
            return False
        if self.min_rent and unit.market_rent < self.min_rent:
            return False
        if self.max_rent and unit.market_rent > self.max_rent:
            return False
        
        return True


class ResidentialDirectLeaseTerms(DirectLeaseTerms):
    """
    Direct lease terms for residential units.
    
    Simplified compared to commercial terms since residential leases
    are typically much simpler (flat monthly rent, no escalations,
    no recovery methods, etc.).
    """
    monthly_rent: Optional[float] = Field(
        default=None,
        description="Monthly rent amount"
    )
    lease_term_months: Optional[int] = Field(
        default=12,
        description="Lease term in months (typically 12 for residential)"
    )
    security_deposit_months: Optional[float] = Field(
        default=1.0,
        description="Security deposit as months of rent"
    )
    concessions_months: Optional[int] = Field(
        default=0,
        description="Free rent months as concession"
    )


class ResidentialAbsorptionPlan(AbsorptionPlanBase):
    """
    Defines and executes a complete plan for leasing up vacant residential units.
    
    This class orchestrates unit-based absorption by:
    1. Filtering available vacant units by criteria
    2. Applying pace strategies designed for unit counts
    3. Creating stabilized unit specifications for absorbed units
    4. Handling residential-specific leasing logic
    
    Example:
        ```python
        absorption_plan = ResidentialAbsorptionPlan(
            name="Phase 1 Lease-Up",
            space_filter=ResidentialUnitFilter(unit_types=["1BR", "2BR"]),
            pace=FixedQuantityPace(quantity=10, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(monthly_rent=2500)
        )
        
        unit_specs = absorption_plan.generate_unit_specs(
            available_vacant_units=vacant_units,
            analysis_start_date=date(2024, 1, 1),
            analysis_end_date=date(2025, 12, 31)
        )
        ```
    """
    
    space_filter: ResidentialUnitFilter = Field(default_factory=ResidentialUnitFilter)
    leasing_assumptions: Union[str, ResidentialDirectLeaseTerms]
    
    # FIXME: Add stabilized operating assumptions interface? expenses, losses, misc_income, etc.

    def generate_lease_specs(
        self,
        available_vacant_suites: List,
        analysis_start_date: date,
        analysis_end_date: date,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> List:
        """
        Generates lease specs (actually unit specs) from absorption plan.
        
        This method maintains compatibility with the base class interface
        but returns ResidentialUnitSpec objects instead of lease specs.
        """
        return self.generate_unit_specs(
            available_vacant_units=available_vacant_suites,
            analysis_start_date=analysis_start_date,
            analysis_end_date=analysis_end_date,
            lookup_fn=lookup_fn,
            global_settings=global_settings
        )

    def generate_unit_specs(
        self,
        available_vacant_units: List[ResidentialVacantUnit],
        analysis_start_date: date,
        analysis_end_date: date,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> List[ResidentialUnitSpec]:
        """
        Generate residential unit specifications from absorption execution.
        
        This is the main method for residential absorption. It converts
        vacant units into leased unit specifications based on the pace
        and leasing assumptions.
        
        Args:
            available_vacant_units: List of ResidentialVacantUnit objects
            analysis_start_date: Start date for absorption analysis
            analysis_end_date: End date for absorption analysis
            lookup_fn: Function to resolve rollover profile references
            global_settings: Global analysis settings
            
        Returns:
            List of ResidentialUnitSpec objects representing leased units
        """
        # Filter units based on criteria
        target_units = [
            unit for unit in available_vacant_units 
            if self.space_filter.matches(unit)
        ]
        
        if not target_units:
            return []

        # Resolve start date
        initial_start_date = self._resolve_start_date(analysis_start_date)
        if initial_start_date > analysis_end_date:
            return []

        # Resolve leasing terms
        lease_terms = self._resolve_leasing_terms(lookup_fn)
        if not lease_terms:
            return []

        # Execute absorption based on pace type
        return self._execute_unit_absorption(
            target_units=target_units,
            initial_start_date=initial_start_date,
            analysis_end_date=analysis_end_date,
            lease_terms=lease_terms,
            global_settings=global_settings
        )

    def _resolve_start_date(self, analysis_start_date: date) -> date:
        """Determine the initial start date for absorption."""
        if isinstance(self.start_date_anchor, date):
            return self.start_date_anchor
        return analysis_start_date

    def _resolve_leasing_terms(self, lookup_fn) -> Optional[Union[ResidentialRolloverLeaseTerms, ResidentialDirectLeaseTerms]]:
        """Resolve leasing assumptions to actual terms."""
        if isinstance(self.leasing_assumptions, ResidentialDirectLeaseTerms):
            return self.leasing_assumptions
        elif isinstance(self.leasing_assumptions, str) and lookup_fn:
            profile = lookup_fn(self.leasing_assumptions)
            if isinstance(profile, ResidentialRolloverProfile):
                return profile.market_terms
        return None

    def _execute_unit_absorption(
        self,
        target_units: List[ResidentialVacantUnit],
        initial_start_date: date,
        analysis_end_date: date,
        lease_terms: Union[ResidentialRolloverLeaseTerms, ResidentialDirectLeaseTerms],
        global_settings: Optional[GlobalSettings]
    ) -> List[ResidentialUnitSpec]:
        """
        Execute the actual unit absorption based on pace strategy.
        
        This is simplified compared to office absorption since:
        - Units are atomic (no subdivision)
        - Absorption is unit-count based
        - Less complex than office lease spec creation
        """
        absorbed_specs = []
        remaining_units = target_units.copy()
        current_date = initial_start_date

        if self.pace.type == "FixedQuantity":
            absorbed_specs = self._execute_fixed_quantity_absorption(
                remaining_units, current_date, analysis_end_date, lease_terms
            )
        elif self.pace.type == "EqualSpread":
            absorbed_specs = self._execute_equal_spread_absorption(
                remaining_units, current_date, analysis_end_date, lease_terms
            )
        # Add other pace types as needed

        return absorbed_specs

    def _execute_fixed_quantity_absorption(
        self,
        remaining_units: List[ResidentialVacantUnit],
        start_date: date,
        end_date: date,
        lease_terms: Union[ResidentialRolloverLeaseTerms, ResidentialDirectLeaseTerms]
    ) -> List[ResidentialUnitSpec]:
        """Execute fixed quantity pace absorption for residential units."""
        absorbed_specs = []
        
        if self.pace.unit == "Units":
            # Absorb specified number of units per period
            units_per_period = int(self.pace.quantity)
            current_date = start_date
            
            while remaining_units and current_date <= end_date:
                # Take up to the target quantity for this period
                units_this_period = min(units_per_period, len(remaining_units))
                
                for i in range(units_this_period):
                    if remaining_units:
                        vacant_unit = remaining_units.pop(0)
                        unit_spec = self._create_unit_spec_from_vacant(
                            vacant_unit, lease_terms, current_date
                        )
                        if unit_spec:
                            absorbed_specs.append(unit_spec)
                
                # Move to next period
                current_date = date(
                    current_date.year + (current_date.month + self.pace.frequency_months - 1) // 12,
                    ((current_date.month + self.pace.frequency_months - 1) % 12) + 1,
                    current_date.day
                )
        
        return absorbed_specs

    def _execute_equal_spread_absorption(
        self,
        remaining_units: List[ResidentialVacantUnit],
        start_date: date,
        end_date: date,
        lease_terms: Union[ResidentialRolloverLeaseTerms, ResidentialDirectLeaseTerms]
    ) -> List[ResidentialUnitSpec]:
        """Execute equal spread pace absorption for residential units."""
        absorbed_specs = []
        total_units = len(remaining_units)
        
        if total_units == 0 or self.pace.total_deals == 0:
            return []
        
        units_per_deal = max(1, total_units // self.pace.total_deals)
        current_date = start_date
        
        for deal_num in range(self.pace.total_deals):
            if not remaining_units or current_date > end_date:
                break
                
            units_this_deal = min(units_per_deal, len(remaining_units))
            
            for i in range(units_this_deal):
                if remaining_units:
                    vacant_unit = remaining_units.pop(0)
                    unit_spec = self._create_unit_spec_from_vacant(
                        vacant_unit, lease_terms, current_date
                    )
                    if unit_spec:
                        absorbed_specs.append(unit_spec)
            
            # Move to next deal period
            current_date = date(
                current_date.year + (current_date.month + self.pace.frequency_months - 1) // 12,
                ((current_date.month + self.pace.frequency_months - 1) % 12) + 1,
                current_date.day
            )
        
        return absorbed_specs

    def _create_unit_spec_from_vacant(
        self,
        vacant_unit: ResidentialVacantUnit,
        lease_terms: Union[ResidentialRolloverLeaseTerms, ResidentialDirectLeaseTerms],
        lease_start_date: date
    ) -> Optional[ResidentialUnitSpec]:
        """
        Create a ResidentialUnitSpec from a vacant unit and lease terms.
        
        This converts absorbed vacant units into leased unit specifications.
        """
        # Determine rent from lease terms
        if isinstance(lease_terms, ResidentialDirectLeaseTerms):
            current_rent = lease_terms.monthly_rent or vacant_unit.market_rent
        else:
            current_rent = lease_terms.market_rent
        
        # Create unit spec - typically one unit at a time for residential
        return ResidentialUnitSpec(
            unit_type_name=vacant_unit.unit_type_name,
            unit_count=1,  # Absorb one unit at a time
            avg_area_sf=vacant_unit.avg_area_sf,
            current_avg_monthly_rent=current_rent,
            rollover_profile=vacant_unit.rollover_profile
        ) 