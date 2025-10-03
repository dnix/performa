# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

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

from dateutil.relativedelta import relativedelta
from pydantic import Field

from ...core.base import (
    AbsorptionPlanBase,
    CustomSchedulePace,
    DirectLeaseTerms,
    EqualSpreadPace,
    FixedQuantityPace,
    SpaceFilter,
)
from ...core.primitives import (
    CashFlowCategoryEnum,
    GlobalSettings,
    PercentageGrowthRate,
    PropertyAttributeKey,
    StartDateAnchorEnum,
    Timeline,
)
from .expense import ResidentialCapExItem, ResidentialExpenses, ResidentialOpExItem
from .loss import (
    ResidentialCreditLoss,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
)
from .misc_income import ResidentialMiscIncome
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
        description="Filter by unit type names (e.g., 'Studio', '1BR', '2BR')",
    )
    min_rent: Optional[float] = Field(
        default=None, description="Minimum market rent filter"
    )
    max_rent: Optional[float] = Field(
        default=None, description="Maximum market rent filter"
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
        default=None, description="Monthly rent amount"
    )
    lease_term_months: Optional[int] = Field(
        default=12, description="Lease term in months (typically 12 for residential)"
    )
    security_deposit_months: Optional[float] = Field(
        default=1.0, description="Security deposit as months of rent"
    )
    concessions_months: Optional[int] = Field(
        default=0, description="Free rent months as concession"
    )
    stabilized_renewal_probability: Optional[float] = Field(
        default=0.7,
        description="Renewal probability for stabilized post-renovation units (0.0-1.0)",
    )
    stabilized_downtime_months: Optional[int] = Field(
        default=1,
        description="Downtime months for stabilized post-renovation units on turnover",
    )


class ResidentialAbsorptionPlan(
    AbsorptionPlanBase[ResidentialExpenses, ResidentialLosses, ResidentialMiscIncome]
):
    """
    Defines and executes a complete plan for leasing up vacant residential units.

    This class orchestrates unit-based absorption by:
    1. Filtering available vacant units by criteria
    2. Applying pace strategies designed for unit counts
    3. Creating stabilized unit specifications for absorbed units
    4. Handling residential-specific leasing logic

    Example:
        ```python
        # Create with required stabilized operating assumptions
        absorption_plan = ResidentialAbsorptionPlan(
            name="Phase 1 Lease-Up",
            space_filter=ResidentialUnitFilter(unit_types=["1BR", "2BR"]),
            pace=FixedQuantityPace(quantity=10, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(monthly_rent=2500),
            stabilized_expenses=ResidentialExpenses(...),
            stabilized_losses=ResidentialLosses(...),
            stabilized_misc_income=ResidentialMiscIncome(...)
        )

        # Or use factory method with typical assumptions
        absorption_plan = ResidentialAbsorptionPlan.with_typical_assumptions(
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

    # Required stabilized operating assumptions (no silent defaults)
    stabilized_expenses: ResidentialExpenses = Field(
        ..., description="Stabilized operating expenses for absorbed units"
    )
    stabilized_losses: ResidentialLosses = Field(
        ..., description="Stabilized loss assumptions for absorbed units"
    )
    stabilized_misc_income: List[ResidentialMiscIncome] = Field(
        ..., description="Stabilized miscellaneous income for absorbed units"
    )

    @classmethod
    def with_typical_assumptions(
        cls,
        name: str,
        space_filter: Optional[ResidentialUnitFilter] = None,
        pace: Union[FixedQuantityPace, EqualSpreadPace, CustomSchedulePace] = None,
        leasing_assumptions: Union[str, ResidentialDirectLeaseTerms] = None,
        start_date_anchor: Union[
            date, StartDateAnchorEnum
        ] = StartDateAnchorEnum.ANALYSIS_START,
        **kwargs,
    ) -> "ResidentialAbsorptionPlan":
        """
        Create a ResidentialAbsorptionPlan with standard operating assumptions.

        This factory method creates an absorption plan with the following assumptions:

        Expenses (per unit per month):
        - Property Management: $150/unit/month
        - Maintenance & Repairs: $100/unit/month
        - Utilities: $75/unit/month
        - Insurance: $50/unit/month
        - Property Taxes: $200/unit/month

        Capital Expenditures:
        - Unit Turnover: $800/unit
        - Building Improvements: $500/unit/year

        Losses:
        - General Vacancy: 5%
        - Credit Loss: 1%

        Miscellaneous Income:
        - Empty list

        Example:
            ```python
            from datetime import date
            from performa.asset.residential.absorption import (
                ResidentialAbsorptionPlan, ResidentialUnitFilter, FixedQuantityPace,
                ResidentialDirectLeaseTerms
            )

            plan = ResidentialAbsorptionPlan.with_typical_assumptions(
                name="Apartment Lease-Up",
                space_filter=ResidentialUnitFilter(unit_types=["1BR", "2BR"]),
                pace=FixedQuantityPace(
                    type="FixedQuantity",
                    quantity=20,
                    unit="Units",
                    frequency_months=1
                ),
                leasing_assumptions=ResidentialDirectLeaseTerms(
                    monthly_rent=2800.0,
                    lease_term_months=12,
                    security_deposit_months=1.0
                ),
                start_date_anchor=date(2024, 6, 1)
            )
            ```

        For custom operating assumptions, use the direct constructor:
            ```python
            plan = ResidentialAbsorptionPlan(
                stabilized_expenses=custom_residential_expenses,
                stabilized_losses=custom_residential_losses,
                stabilized_misc_income=custom_misc_income,
                ...
            )
            ```

        Args:
            name: Name for the absorption plan
            space_filter: Criteria for which vacant units to include
            pace: Leasing velocity strategy
            leasing_assumptions: Financial terms for new leases
            start_date_anchor: When leasing begins
            **kwargs: Additional arguments passed to constructor

        Returns:
            ResidentialAbsorptionPlan with standard operating assumptions
        """
        # Create a basic timeline for the expense items
        timeline = Timeline(
            start_date=date(2024, 1, 1),
            duration_months=120,  # 10 years
        )

        # Create typical residential operating assumptions
        typical_expenses = ResidentialExpenses(
            operating_expenses=[
                ResidentialOpExItem(
                    name="Property Management",
                    category=CashFlowCategoryEnum.EXPENSE,
                    timeline=timeline,
                    value=150.0,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Property Management Growth", value=0.03
                    ),
                ),
                ResidentialOpExItem(
                    name="Maintenance & Repairs",
                    category=CashFlowCategoryEnum.EXPENSE,
                    timeline=timeline,
                    value=100.0,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Maintenance Growth", value=0.035
                    ),
                ),
                ResidentialOpExItem(
                    name="Utilities",
                    category=CashFlowCategoryEnum.EXPENSE,
                    timeline=timeline,
                    value=75.0,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Utilities Growth", value=0.04
                    ),
                ),
            ],
            capital_expenses=[
                ResidentialCapExItem(
                    name="Maintenance Reserve",
                    category=CashFlowCategoryEnum.EXPENSE,
                    timeline=timeline,
                    value=300.0,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(name="CapEx Growth", value=0.03),
                )
            ],
        )

        typical_losses = ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(
                rate=0.05,  # 5% residential vacancy
            ),
            credit_loss=ResidentialCreditLoss(
                rate=0.02,  # 2% collection loss
            ),
        )

        typical_misc_income = ResidentialMiscIncome(
            name="Ancillary Income",
            category=CashFlowCategoryEnum.REVENUE,
            timeline=timeline,
            value=50.0,  # $50/unit/month (parking, laundry, etc.)
            reference=PropertyAttributeKey.UNIT_COUNT,
            growth_rate=PercentageGrowthRate(name="Misc Income Growth", value=0.025),
        )

        return cls(
            name=name,
            space_filter=space_filter or ResidentialUnitFilter(),
            pace=pace
            or FixedQuantityPace(quantity=5, unit="Units", frequency_months=1),
            leasing_assumptions=leasing_assumptions or ResidentialDirectLeaseTerms(),
            start_date_anchor=start_date_anchor,
            stabilized_expenses=typical_expenses,
            stabilized_losses=typical_losses,
            stabilized_misc_income=[typical_misc_income],
            **kwargs,
        )

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
            global_settings=global_settings,
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
            unit for unit in available_vacant_units if self.space_filter.matches(unit)
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
            global_settings=global_settings,
        )

    def _resolve_start_date(self, analysis_start_date: date) -> date:
        """Determine the initial start date for absorption.
        
        Args:
            analysis_start_date: The analysis start date to use as anchor
            
        Returns:
            The resolved start date for absorption, with offset applied if configured
        """
        # If start_date_anchor is an absolute date, use it directly
        if isinstance(self.start_date_anchor, date):
            return self.start_date_anchor
        
        # For anchor enums (ANALYSIS_START), apply the offset
        if self.start_offset_months > 0:
            return analysis_start_date + relativedelta(months=self.start_offset_months)
        
        return analysis_start_date

    def _resolve_leasing_terms(
        self, lookup_fn
    ) -> Optional[Union[ResidentialRolloverLeaseTerms, ResidentialDirectLeaseTerms]]:
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
        global_settings: Optional[GlobalSettings],
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
        lease_terms: Union[ResidentialRolloverLeaseTerms, ResidentialDirectLeaseTerms],
    ) -> List[ResidentialUnitSpec]:
        """Execute fixed quantity pace absorption for residential units."""
        absorbed_specs = []

        if self.pace.unit == "Units":
            # Absorb specified number of units per period
            units_per_period = int(self.pace.quantity)
            current_date = start_date

            # Create a working copy with unit counts to track remaining inventory
            working_inventory = []
            for vacant_unit in remaining_units:
                working_inventory.append({
                    "vacant_unit": vacant_unit,
                    "remaining_count": vacant_unit.unit_count,
                })

            while current_date <= end_date:
                # Check if any units remain
                total_remaining = sum(
                    item["remaining_count"] for item in working_inventory
                )
                if total_remaining == 0:
                    break

                # Absorb up to the target quantity for this period
                units_to_absorb_this_period = min(units_per_period, total_remaining)
                units_absorbed_this_period = 0

                # Absorb units from available inventory
                for item in working_inventory:
                    if units_absorbed_this_period >= units_to_absorb_this_period:
                        break

                    if item["remaining_count"] > 0:
                        # Determine how many units to absorb from this type
                        units_from_this_type = min(
                            item["remaining_count"],
                            units_to_absorb_this_period - units_absorbed_this_period,
                        )

                        if units_from_this_type > 0:
                            # Create unit spec for absorbed units
                            unit_spec = self._create_unit_spec_from_vacant(
                                item["vacant_unit"],
                                lease_terms,
                                current_date,
                                units_from_this_type,
                            )
                            if unit_spec:
                                absorbed_specs.append(unit_spec)

                            # Update remaining count
                            item["remaining_count"] -= units_from_this_type
                            units_absorbed_this_period += units_from_this_type

                # Move to next period
                current_date = date(
                    current_date.year
                    + (current_date.month + self.pace.frequency_months - 1) // 12,
                    ((current_date.month + self.pace.frequency_months - 1) % 12) + 1,
                    current_date.day,
                )

        return absorbed_specs

    def _execute_equal_spread_absorption(
        self,
        remaining_units: List[ResidentialVacantUnit],
        start_date: date,
        end_date: date,
        lease_terms: Union[ResidentialRolloverLeaseTerms, ResidentialDirectLeaseTerms],
    ) -> List[ResidentialUnitSpec]:
        """Execute equal spread pace absorption for residential units."""
        absorbed_specs = []

        # Calculate total available units across all vacant unit types
        total_units = sum(vacant_unit.unit_count for vacant_unit in remaining_units)

        if total_units == 0 or self.pace.total_deals == 0:
            return []

        # Create a working copy with unit counts to track remaining inventory
        working_inventory = []
        for vacant_unit in remaining_units:
            working_inventory.append({
                "vacant_unit": vacant_unit,
                "remaining_count": vacant_unit.unit_count,
            })

        units_per_deal = max(1, total_units // self.pace.total_deals)
        current_date = start_date

        for deal_num in range(self.pace.total_deals):
            if current_date > end_date:
                break

            # Check if any units remain
            total_remaining = sum(item["remaining_count"] for item in working_inventory)
            if total_remaining == 0:
                break

            units_to_absorb_this_deal = min(units_per_deal, total_remaining)
            units_absorbed_this_deal = 0

            # Absorb units from available inventory
            for item in working_inventory:
                if units_absorbed_this_deal >= units_to_absorb_this_deal:
                    break

                if item["remaining_count"] > 0:
                    # Determine how many units to absorb from this type
                    units_from_this_type = min(
                        item["remaining_count"],
                        units_to_absorb_this_deal - units_absorbed_this_deal,
                    )

                    if units_from_this_type > 0:
                        # Create unit spec for absorbed units
                        unit_spec = self._create_unit_spec_from_vacant(
                            item["vacant_unit"],
                            lease_terms,
                            current_date,
                            units_from_this_type,
                        )
                        if unit_spec:
                            absorbed_specs.append(unit_spec)

                        # Update remaining count
                        item["remaining_count"] -= units_from_this_type
                        units_absorbed_this_deal += units_from_this_type

            # Move to next deal period
            current_date = date(
                current_date.year
                + (current_date.month + self.pace.frequency_months - 1) // 12,
                ((current_date.month + self.pace.frequency_months - 1) % 12) + 1,
                current_date.day,
            )

        return absorbed_specs

    def _create_unit_spec_from_vacant(
        self,
        vacant_unit: ResidentialVacantUnit,
        lease_terms: Union[ResidentialRolloverLeaseTerms, ResidentialDirectLeaseTerms],
        lease_start_date: date,
        unit_count: int = 1,
    ) -> Optional[ResidentialUnitSpec]:
        """
        Create a ResidentialUnitSpec from a vacant unit and lease terms.

        This converts absorbed vacant units into leased unit specifications.

        Args:
            vacant_unit: The vacant unit template to convert
            lease_terms: Lease terms to apply
            lease_start_date: When the lease starts (CRITICAL for progressive absorption)
            unit_count: Number of units to include in this spec (default: 1)
        """
        # Determine rent from lease terms
        if isinstance(lease_terms, ResidentialDirectLeaseTerms):
            current_rent = lease_terms.monthly_rent or vacant_unit.market_rent
        else:
            current_rent = lease_terms.market_rent

        # Create unit spec with progressive lease start date (THE FIX!)
        return ResidentialUnitSpec(
            unit_type_name=vacant_unit.unit_type_name,
            unit_count=unit_count,  # Use the specified unit count
            avg_area_sf=vacant_unit.avg_area_sf,
            current_avg_monthly_rent=current_rent,
            rollover_profile=vacant_unit.rollover_profile,
            lease_start_date=lease_start_date,  # Store the progressive date!
        )
