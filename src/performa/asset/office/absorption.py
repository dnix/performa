# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
This module defines the logic for modeling the lease-up of vacant office space.

The core components are:
- **OfficeAbsorptionPlan**: The main entry point that defines a complete lease-up
  scenario. It specifies which vacant suites to target (`space_filter`), when the
  absorption should begin (`start_date_anchor`), the leasing velocity (`pace`),
  and the financial terms for the new leases (`leasing_assumptions`).

- **Pace Models**: Concrete data classes (`FixedQuantityPace`, `EqualSpreadPace`,
  `CustomSchedulePace`) that describe different methods of controlling the
  leasing velocity (e.g., lease 10,000 SF every quarter).

- **PaceStrategy Classes**: The logic that implements the leasing velocity defined
  by the Pace Models. Each strategy (`FixedQuantityPaceStrategy`, etc.)
  contains a `generate` method that produces a list of `OfficeLeaseSpec`
  objects representing the newly signed leases.

A key feature of this module is the ability to handle **dynamic suite
subdivision**. A large `OfficeVacantSuite` can be marked as `is_divisible=True`
and provided with subdivision parameters. The pace strategies will then
intelligently "carve out" smaller leases from this large space according to the
absorption targets, a common scenario in real-world leasing of large floorplates.

The process is managed by passing a `PaceContext` object, which holds the
state of the absorption (like the remaining area of divisible suites), to the
strategy's `generate` method.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Union,
)
from uuid import UUID

import pandas as pd
from pydantic import Field

from ...core.base import (
    AbsorptionPlanBase,
    SuiteAbsorptionState,
)
from ...core.base import (
    BasePace as CoreBasePace,
)
from ...core.base import (
    DirectLeaseTerms as CoreDirectLeaseTerms,
)
from ...core.base import (
    PaceContext as CorePaceContext,
)
from ...core.base import (
    PaceStrategy as CorePaceStrategy,
)
from ...core.base import (
    SpaceFilter as CoreSpaceFilter,
)
from ...core.base.absorption import AnchorLogic
from ...core.primitives import (
    GlobalSettings,
    LeaseTypeEnum,
    ProgramUseEnum,
    StartDateAnchorEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from .expense import OfficeExpenses, OfficeOpExItem
from .lease_spec import OfficeLeaseSpec
from .losses import OfficeCollectionLoss, OfficeGeneralVacancyLoss, OfficeLosses
from .misc_income import OfficeMiscIncome
from .rollover import OfficeRolloverProfile

if TYPE_CHECKING:
    from .lc import OfficeLeasingCommission
    from .recovery import OfficeRecoveryMethod
    from .rent_abatement import OfficeRentAbatement
    from .rent_escalation import OfficeRentEscalation
    from .rent_roll import OfficeVacantSuite
    from .rollover import OfficeRolloverLeaseTerms
    from .ti import OfficeTenantImprovement


logger = logging.getLogger(__name__)


class SpaceFilter(CoreSpaceFilter):
    """
    Defines criteria to filter which vacant office suites are included in an
    absorption plan. Inherits from the common `SpaceFilter` and is specialized
    for `OfficeVacantSuite`.
    """
    def matches(self, suite: OfficeVacantSuite) -> bool:
        """Checks if a given office suite matches the filter criteria."""
        return super().matches(suite)


class BasePace(CoreBasePace):
    """Abstract base class for all pace models."""
    pass


class FixedQuantityPace(BasePace):
    """
    Defines an absorption pace based on leasing a fixed quantity of space
    or a fixed number of units per period.

    Attributes:
        type: The discriminator field for Pydantic.
        quantity: The amount of space (in SF) or number of units to lease.
        unit: The unit of measure for `quantity` ("SF" or "Units").
        frequency_months: The number of months in each leasing period.
    """
    type: Literal["FixedQuantity"] = "FixedQuantity"
    quantity: float
    unit: Literal["SF", "Units"]
    frequency_months: int = 1


class EqualSpreadPace(BasePace):
    """
    Defines an absorption pace where a total number of deals are spread
    equally over the lease-up period.

    The total area of the target suites is divided by `total_deals` to determine
    the target area to be leased in each deal period.

    Attributes:
        type: The discriminator field for Pydantic.
        total_deals: The total number of deals to be made.
        frequency_months: The number of months between the start of each deal.
    """
    type: Literal["EqualSpread"] = "EqualSpread"
    total_deals: int
    frequency_months: int = 1


class CustomSchedulePace(BasePace):
    """
    Defines an absorption pace based on a user-provided schedule of
    SF to be leased on specific dates.

    Attributes:
        type: The discriminator field for Pydantic.
        schedule: A dictionary where keys are dates and values are the
                  target square footage to be leased on that date.
    """
    type: Literal["CustomSchedule"] = "CustomSchedule"
    schedule: Dict[date, float]


class DirectLeaseTerms(CoreDirectLeaseTerms):
    """
    Defines the specific, direct financial terms for leases generated by an
    absorption plan. This is used when not referencing a shared `RolloverProfile`.

    This class extends the common `DirectLeaseTerms` with office-specific
    financial model types.
    """
    rent_escalation: Optional[OfficeRentEscalation] = None
    rent_abatement: Optional[OfficeRentAbatement] = None
    recovery_method: Optional[OfficeRecoveryMethod] = None
    ti_allowance: Optional[OfficeTenantImprovement] = None
    leasing_commission: Optional[OfficeLeasingCommission] = None


@dataclass
class PaceContext(CorePaceContext):
    """
    A data container that holds the state and configuration for a pace
    strategy's `generate` method call.

    It provides the strategy with access to the remaining vacant suites,
    the leasing terms, analysis dates, and helper functions to create
    lease specs. It is a key part of managing the state of the absorption
    process, especially for tracking the remaining area of divisible suites.
    """
    remaining_suites: List[OfficeVacantSuite]
    market_lease_terms: Optional[OfficeRolloverLeaseTerms]
    direct_terms: Optional[DirectLeaseTerms]
    create_spec_fn: Callable[..., Optional[OfficeLeaseSpec]]
    create_subdivided_spec_fn: Callable[..., Optional[OfficeLeaseSpec]]
    total_target_area: float
    _suite_states: Dict[str, SuiteAbsorptionState]


class PaceStrategy(CorePaceStrategy):
    """Abstract base class for all pace strategy implementations."""
    @abstractmethod
    def generate(
        self, pace_model: BasePace, context: PaceContext
    ) -> List[OfficeLeaseSpec]:
        """
        Generates a list of `OfficeLeaseSpec` objects based on the pace model.

        Args:
            pace_model: The data model defining the pace (e.g., `FixedQuantityPace`).
            context: The context object containing state and configuration.

        Returns:
            A list of newly generated `OfficeLeaseSpec` objects.
        """
        pass


class FixedQuantityPaceStrategy(PaceStrategy):
    """
    Implements the logic for a fixed quantity absorption pace.

    This strategy iterates through leasing periods. In each period, it attempts
    to lease a specified `quantity` of space, either in "SF" or by "Units".
    It prioritizes leasing whole, non-divisible suites first (largest to smallest)
    and then uses divisible suites to meet the target.
    """
    def generate(
        self, pace_model: FixedQuantityPace, context: PaceContext
    ) -> List[OfficeLeaseSpec]:
        """
        Generates lease specs by absorbing a fixed quantity each period.

        - If `unit` is "SF", it performs a greedy packing of whole suites. If the
          target is not met, it carves out space from the largest available
          divisible suite.
        - If `unit` is "Units", it first leases whole non-divisible suites. If more
          units are needed, it carves them out of the largest divisible suite,
          each with the `subdivision_average_lease_area`.

        The process continues until all target suites are leased or the analysis
        end date is reached.
        """
        generated_specs: List[OfficeLeaseSpec] = []
        current_period_start = context.initial_start_date
        
        # Sort suites once: largest to smallest for whole-suite packing, 
        # but we also need to find the first available divisible suite.
        local_remaining_suites = sorted(context.remaining_suites, key=lambda s: s.area, reverse=True)

        while any(s.area > 0 for s in local_remaining_suites) and current_period_start <= context.analysis_end_date:
            quantity_remaining_this_period = pace_model.quantity
            suites_leased_this_period = 0
            
            # --- Handle by SF ---
            if pace_model.unit == "SF":
                suites_to_remove = []
                for suite in local_remaining_suites:
                    if quantity_remaining_this_period <= 0: break
                    
                    suite_state = context._suite_states[suite.suite]
                    
                    if suite.is_divisible:
                        avg_lease_size = suite.subdivision_average_lease_area
                        min_lease_size = suite.subdivision_minimum_lease_area or avg_lease_size

                        while suite_state.remaining_area >= min_lease_size and quantity_remaining_this_period >= min_lease_size:
                            area_to_lease = min(suite_state.remaining_area, avg_lease_size, quantity_remaining_this_period)
                            if area_to_lease < min_lease_size:
                                # If the largest possible lease is smaller than min, try to take it only if it's all that's left of the suite
                                if suite_state.remaining_area < min_lease_size and quantity_remaining_this_period >= suite_state.remaining_area:
                                    area_to_lease = suite_state.remaining_area
                                else:
                                    break

                            suite_state.units_created += 1
                            spec = context.create_subdivided_spec_fn(
                                master_suite=suite,
                                subdivided_area=area_to_lease,
                                sub_unit_count=suite_state.units_created,
                                start_date=current_period_start,
                                deal_number=len(generated_specs) + 1,
                                profile_market_terms=context.market_lease_terms,
                                direct_terms=context.direct_terms,
                                global_settings=context.global_settings,
                            )
                            if spec:
                                generated_specs.append(spec)
                                suite_state.remaining_area -= area_to_lease
                                quantity_remaining_this_period -= area_to_lease
                    
                    elif not suite.is_divisible and suite_state.remaining_area > 0 and quantity_remaining_this_period >= suite.area:
                        # Lease whole, non-divisible suite
                        spec = context.create_spec_fn(
                            suite=suite,
                            start_date=current_period_start,
                            deal_number=len(generated_specs) + 1,
                            profile_market_terms=context.market_lease_terms,
                            direct_terms=context.direct_terms,
                            global_settings=context.global_settings,
                        )
                        if spec:
                            generated_specs.append(spec)
                            quantity_remaining_this_period -= suite.area
                            suite_state.remaining_area = 0 # Mark as fully leased
                
                # Filter out fully leased suites
                local_remaining_suites = [s for s in local_remaining_suites if context._suite_states[s.suite].remaining_area > 0]

            # --- Handle by Units ---
            elif pace_model.unit == "Units":
                suites_to_lease_this_period = []
                # Take the largest available whole suites first
                for suite in local_remaining_suites:
                    if len(suites_to_lease_this_period) >= quantity_remaining_this_period: break
                    if not suite.is_divisible and context._suite_states[suite.suite].remaining_area > 0:
                        suites_to_lease_this_period.append(suite)
                
                # If we still need more units, start carving them from the largest divisible suite
                if len(suites_to_lease_this_period) < quantity_remaining_this_period:
                    divisible_suites = sorted([s for s in local_remaining_suites if s.is_divisible and context._suite_states[s.suite].remaining_area > 0], key=lambda s: s.area, reverse=True)
                    if divisible_suites:
                        suite_to_divide = divisible_suites[0]
                        suite_state = context._suite_states[suite_to_divide.suite]
                        avg_lease_size = suite_to_divide.subdivision_average_lease_area
                        min_lease_size = suite_to_divide.subdivision_minimum_lease_area or avg_lease_size

                        while len(suites_to_lease_this_period) < quantity_remaining_this_period and suite_state.remaining_area >= min_lease_size:
                            area_to_lease = min(suite_state.remaining_area, avg_lease_size)
                            suite_state.units_created += 1
                            spec = context.create_subdivided_spec_fn(
                                master_suite=suite_to_divide,
                                subdivided_area=area_to_lease,
                                sub_unit_count=suite_state.units_created,
                                start_date=current_period_start,
                                deal_number=len(generated_specs) + 1,
                                profile_market_terms=context.market_lease_terms,
                                direct_terms=context.direct_terms,
                                global_settings=context.global_settings,
                            )
                            if spec:
                                generated_specs.append(spec)
                                suite_state.remaining_area -= area_to_lease
                                suites_to_lease_this_period.append(suite_to_divide) # Dummy append to count units

                # Mark non-divisible suites as leased
                for suite in suites_to_lease_this_period:
                     if not suite.is_divisible:
                         context._suite_states[suite.suite].remaining_area = 0
                
                local_remaining_suites = [s for s in local_remaining_suites if context._suite_states[s.suite].remaining_area > 0]

            current_period_start = (pd.Timestamp(current_period_start) + pd.DateOffset(months=pace_model.frequency_months)).date()

        return generated_specs


class EqualSpreadPaceStrategy(PaceStrategy):
    """
    Implements the logic for an equal spread absorption pace.

    This strategy calculates a target area per deal and then iterates through
    each deal period, attempting to lease that target area. It uses a greedy
    packing algorithm, first leasing whole non-divisible suites that fit within
    the deal's remaining target area, and then carving a single lease from a
    divisible suite to "top off" the deal to the target area.
    """
    def generate(
        self, pace_model: EqualSpreadPace, context: PaceContext
    ) -> List[OfficeLeaseSpec]:
        """
        Generates lease specs by spreading absorption over a set number of deals.
        
        For each deal, it attempts to fill a `target_area_per_deal`. It does this by:
        1. Greedily packing in the largest available non-divisible suites that fit.
        2. If area is still needed, creating a single subdivided lease from the
           largest available divisible suite to meet the target.
        """
        generated_specs: List[OfficeLeaseSpec] = []
        if pace_model.total_deals <= 0 or context.total_target_area <= 0:
            return []

        target_area_per_deal = context.total_target_area / pace_model.total_deals
        current_deal_start_date = context.initial_start_date
        local_remaining_suites = sorted(context.remaining_suites, key=lambda s: s.area, reverse=True)

        for deal_num in range(1, pace_model.total_deals + 1):
            if not any(s.area > 0 for s in local_remaining_suites) or current_deal_start_date > context.analysis_end_date:
                break

            area_to_absorb_this_deal = target_area_per_deal
            
            # --- First, pack whole, non-divisible suites ---
            suites_leased_this_deal = []
            for suite in local_remaining_suites:
                suite_state = context._suite_states[suite.suite]
                if not suite.is_divisible and suite_state.remaining_area > 0 and area_to_absorb_this_deal >= suite.area:
                    spec = context.create_spec_fn(
                        suite=suite, start_date=current_deal_start_date, deal_number=len(generated_specs) + 1,
                        profile_market_terms=context.market_lease_terms, direct_terms=context.direct_terms, global_settings=context.global_settings,
                    )
                    if spec:
                        generated_specs.append(spec)
                        area_to_absorb_this_deal -= suite.area
                        suite_state.remaining_area = 0
                        suites_leased_this_deal.append(suite)

            # --- Second, top off with a divisible suite ---
            if area_to_absorb_this_deal > 0:
                # Find the largest divisible suite with enough remaining area
                divisible_suites = sorted([s for s in local_remaining_suites if s.is_divisible and context._suite_states[s.suite].remaining_area > 0], key=lambda s: s.area, reverse=True)
                for suite in divisible_suites:
                    suite_state = context._suite_states[suite.suite]
                    min_lease_size = suite.subdivision_minimum_lease_area or 1.0 # a small number to allow topping off
                    
                    if suite_state.remaining_area > 0 and area_to_absorb_this_deal > 0:
                        area_to_lease = min(area_to_absorb_this_deal, suite_state.remaining_area)
                        if area_to_lease < min_lease_size and area_to_lease < suite_state.remaining_area:
                            continue

                        suite_state.units_created += 1
                        spec = context.create_subdivided_spec_fn(
                            master_suite=suite, subdivided_area=area_to_lease, sub_unit_count=suite_state.units_created,
                            start_date=current_deal_start_date, deal_number=len(generated_specs) + 1,
                            profile_market_terms=context.market_lease_terms, direct_terms=context.direct_terms, global_settings=context.global_settings,
                        )
                        if spec:
                            generated_specs.append(spec)
                            suite_state.remaining_area -= area_to_lease
                            area_to_absorb_this_deal -= area_to_lease
                        
                        if area_to_absorb_this_deal <= 0:
                            break # Move to next deal

            # Filter out fully leased suites and advance date
            local_remaining_suites = [s for s in context.remaining_suites if context._suite_states[s.suite].remaining_area > 0]
            current_deal_start_date = (pd.Timestamp(current_deal_start_date) + pd.DateOffset(months=pace_model.frequency_months)).date()

        return generated_specs


class CustomSchedulePaceStrategy(PaceStrategy):
    """
    Implements the logic for a custom schedule absorption pace.

    This strategy iterates through a user-defined schedule of dates and
    target square footages. For each scheduled entry, it attempts to lease the
    specified SF amount. The logic is similar to `FixedQuantityPaceStrategy`,
    prioritizing whole non-divisible suites before carving out space from
    divisible suites.
    """
    def generate(
        self, pace_model: CustomSchedulePace, context: PaceContext
    ) -> List[OfficeLeaseSpec]:
        """
        Generates lease specs based on a user-defined schedule.

        For each date and quantity in the `pace_model.schedule`, this method
        will attempt to absorb that amount of SF by first leasing whole,
        non-divisible suites and then topping off the required amount by
        subdividing a larger divisible suite.
        """
        generated_specs: List[OfficeLeaseSpec] = []
        
        # Start with all suites, sorted largest to smallest.
        local_remaining_suites = sorted(context.remaining_suites, key=lambda s: s.area, reverse=True)

        for schedule_date, quantity_sf in sorted(pace_model.schedule.items()):
            if not any(context._suite_states[s.suite].remaining_area > 0 for s in local_remaining_suites) or schedule_date > context.analysis_end_date:
                break
            
            quantity_remaining_this_period = quantity_sf

            # --- Handle Non-Divisible Suites First ---
            # This is a greedy packing approach for whole suites.
            suites_to_remove = []
            for suite in local_remaining_suites:
                suite_state = context._suite_states[suite.suite]
                if not suite.is_divisible and suite_state.remaining_area > 0 and quantity_remaining_this_period >= suite.area:
                    spec = context.create_spec_fn(
                        suite=suite, start_date=schedule_date, deal_number=len(generated_specs) + 1,
                        profile_market_terms=context.market_lease_terms, direct_terms=context.direct_terms,
                        global_settings=context.global_settings,
                    )
                    if spec:
                        generated_specs.append(spec)
                        quantity_remaining_this_period -= suite.area
                        suite_state.remaining_area = 0
                        suites_to_remove.append(suite)

            # --- Top off with Divisible Suites ---
            # If there's still quantity to absorb, use divisible suites.
            if quantity_remaining_this_period > 0:
                # Iterate through divisible suites, largest first.
                divisible_suites = [s for s in local_remaining_suites if s.is_divisible]
                
                for suite in divisible_suites:
                    if quantity_remaining_this_period <= 0: break
                    
                    suite_state = context._suite_states[suite.suite]
                    if suite_state.remaining_area <= 0: continue

                    avg_lease_size = suite.subdivision_average_lease_area
                    min_lease_size = suite.subdivision_minimum_lease_area or avg_lease_size

                    while suite_state.remaining_area > 0 and quantity_remaining_this_period > 0:
                        area_to_lease = min(suite_state.remaining_area, avg_lease_size, quantity_remaining_this_period)
                        
                        if area_to_lease < min_lease_size and area_to_lease < suite_state.remaining_area:
                            break
                        
                        suite_state.units_created += 1
                        spec = context.create_subdivided_spec_fn(
                            master_suite=suite, subdivided_area=area_to_lease, sub_unit_count=suite_state.units_created,
                            start_date=schedule_date, deal_number=len(generated_specs) + 1,
                            profile_market_terms=context.market_lease_terms, direct_terms=context.direct_terms, global_settings=context.global_settings,
                        )
                        if spec:
                            generated_specs.append(spec)
                            suite_state.remaining_area -= area_to_lease
                            quantity_remaining_this_period -= area_to_lease
            
        return generated_specs


class OfficeAbsorptionPlan(AbsorptionPlanBase[OfficeExpenses, OfficeLosses, OfficeMiscIncome]):
    """
    Defines and executes a complete plan for leasing up vacant office space.

    This class orchestrates the process by:
    1. Filtering available vacant suites.
    2. Determining the start date and leasing terms.
    3. Selecting the appropriate `PaceStrategy` based on the `pace` model.
    4. Preparing and passing the `PaceContext` to the strategy.
    5. Returning the final list of generated `OfficeLeaseSpec` objects.
    """
    space_filter: SpaceFilter
    pace: Annotated[
        Union[FixedQuantityPace, EqualSpreadPace, CustomSchedulePace],
        Field(discriminator="type"),
    ]
    leasing_assumptions: Union[str, DirectLeaseTerms]

    # Required stabilized operating assumptions (no silent defaults)
    stabilized_expenses: OfficeExpenses = Field(
        ..., 
        description="Stabilized operating expenses for absorbed units"
    )
    stabilized_losses: OfficeLosses = Field(
        ..., 
        description="Stabilized loss assumptions for absorbed units"
    )
    stabilized_misc_income: List[OfficeMiscIncome] = Field(
        ..., 
        description="Stabilized miscellaneous income for absorbed units"
    )

    @classmethod
    def with_typical_assumptions(
        cls,
        name: str,
        space_filter: SpaceFilter,
        start_date_anchor: Union[date, StartDateAnchorEnum, AnchorLogic], 
        pace: Annotated[Union[FixedQuantityPace, EqualSpreadPace, CustomSchedulePace], Field(discriminator="type")],
        leasing_assumptions: Union[str, DirectLeaseTerms]
    ) -> "OfficeAbsorptionPlan":
        """
        Create an OfficeAbsorptionPlan with standard operating assumptions.
        
        This factory method creates an absorption plan with the following assumptions:
        
        Expenses:
        - Management Fee: 5% of Effective Gross Income
        - Operating Costs: $8.00/SF/year
        - Taxes & Insurance: $2.00/SF/year
        
        Losses:
        - General Vacancy: 5%
        - Collection Loss: 1%
        
        Miscellaneous Income:
        - Empty list
        
        Example:
            ```python
            from datetime import date
            from performa.asset.office.absorption import (
                OfficeAbsorptionPlan, SpaceFilter, FixedQuantityPace, DirectLeaseTerms
            )
            
            plan = OfficeAbsorptionPlan.with_typical_assumptions(
                name="Office Lease-Up",
                space_filter=SpaceFilter(use_types=["office"]),
                start_date_anchor=date(2024, 6, 1),
                pace=FixedQuantityPace(
                    type="FixedQuantity",
                    quantity=25000,
                    unit="SF", 
                    frequency_months=6
                ),
                leasing_assumptions=DirectLeaseTerms(
                    base_rent_value=45.0,
                    base_rent_unit_of_measure="per_unit",
                    base_rent_frequency="annual",
                    term_months=60,
                    upon_expiration="market"
                )
            )
            ```
        
        For custom operating assumptions, use the direct constructor:
            ```python
            plan = OfficeAbsorptionPlan(
                stabilized_expenses=custom_office_expenses,
                stabilized_losses=custom_office_losses,
                stabilized_misc_income=custom_misc_income,
                ...
            )
            ```
        
        Args:
            name: Name for the absorption plan
            space_filter: Criteria for which vacant suites to include
            start_date_anchor: When leasing begins
            pace: Leasing velocity strategy
            leasing_assumptions: Financial terms for new leases
        
        Returns:
            OfficeAbsorptionPlan with standard operating assumptions
        """
        return cls(
            name=name,
            space_filter=space_filter,
            start_date_anchor=start_date_anchor,
            pace=pace,
            leasing_assumptions=leasing_assumptions,
            stabilized_expenses=cls._create_typical_expenses(),
            stabilized_losses=cls._create_typical_losses(),
            stabilized_misc_income=[]  # No misc income by default
        )

    @classmethod
    def _create_typical_expenses(cls) -> OfficeExpenses:
        """Create typical office operating expenses."""
        from datetime import date

        from ...core.primitives import PercentageGrowthRate, Timeline
        
        # Create a basic timeline for the expense items
        timeline = Timeline(
            start_date=date(2024, 1, 1),
            duration_months=120  # 10 years
        )
        
        # Create typical office operating expenses
        return OfficeExpenses(
            operating_expenses=[
                OfficeOpExItem(
                    name="Property Management",
                    category="Expense",
                    timeline=timeline,
                    value=5.0,  # $5/SF annually
                    unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
                    growth_rate=PercentageGrowthRate(name="Property Management Growth", value=0.03)
                ),
                OfficeOpExItem(
                    name="Operating Costs",
                    category="Expense",
                    timeline=timeline,
                    value=8.0,  # $8/SF annually
                    unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
                    growth_rate=PercentageGrowthRate(name="OpEx Growth", value=0.035)
                ),
                OfficeOpExItem(
                    name="Taxes & Insurance",
                    category="Expense",
                    timeline=timeline,
                    value=2.0,  # $2/SF annually
                    unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
                    growth_rate=PercentageGrowthRate(name="Tax Growth", value=0.025)
                )
            ]
        )

    @classmethod
    def _create_typical_losses(cls) -> OfficeLosses:
        """Create typical office loss assumptions."""
        return OfficeLosses(
            general_vacancy=OfficeGeneralVacancyLoss(
                vacancy_rate=0.05,  # 5% office vacancy
                applied_to_base_rent=True
            ),
            collection_loss=OfficeCollectionLoss(
                loss_rate=0.01,  # 1% collection loss
                applied_to_base_rent=True
            )
        )

    def generate_lease_specs(
        self,
        available_vacant_suites: List[OfficeVacantSuite],
        analysis_start_date: date,
        analysis_end_date: date,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> List[OfficeLeaseSpec]:
        """
        Generates speculative lease specs based on the absorption plan.

        This is the main entry point for an absorption analysis. It takes the
        property's vacant suites and analysis dates, and executes the plan
        defined by the instance attributes.

        Args:
            available_vacant_suites: A list of all `OfficeVacantSuite` objects
                available for lease-up.
            analysis_start_date: The start date of the overall analysis.
            analysis_end_date: The end date of the overall analysis.
            lookup_fn: A function used to resolve string-based references,
                typically for finding a `OfficeRolloverProfile`.
            global_settings: Global settings for the analysis.

        Returns:
            A list of newly generated `OfficeLeaseSpec` instances.
        """
        target_suites = sorted(
            [s for s in available_vacant_suites if self.space_filter.matches(s)],
            key=lambda s: s.area,
            reverse=True,
        )
        if not target_suites:
            return []

        initial_start_date = self._resolve_start_date(analysis_start_date)
        if initial_start_date > analysis_end_date:
            return []

        market_lease_terms, direct_terms = self._resolve_leasing_terms(lookup_fn)
        if not market_lease_terms and not direct_terms:
            return []

        strategy = self._get_strategy()

        context = PaceContext(
            plan_name=self.name,
            remaining_suites=target_suites.copy(),
            initial_start_date=initial_start_date,
            analysis_end_date=analysis_end_date,
            market_lease_terms=market_lease_terms,
            direct_terms=direct_terms,
            global_settings=global_settings,
            create_spec_fn=self._create_lease_spec,
            create_subdivided_spec_fn=self._create_subdivided_lease_spec,
            total_target_area=sum(s.area for s in target_suites),
            _suite_states={
                s.suite: SuiteAbsorptionState(remaining_area=s.area)
                for s in target_suites
            },
        )

        return strategy.generate(self.pace, context)

    def _get_strategy(self) -> PaceStrategy:
        """
        Selects the appropriate pace strategy based on the `pace.type` field.
        """
        strategy_map = {
            "FixedQuantity": FixedQuantityPaceStrategy(),
            "EqualSpread": EqualSpreadPaceStrategy(),
            "CustomSchedule": CustomSchedulePaceStrategy(),
        }
        return strategy_map[self.pace.type]

    def _resolve_leasing_terms(self, lookup_fn):
        """
        Resolves the `leasing_assumptions` field to get market or direct terms.
        """
        market_terms, direct_terms = None, None
        if isinstance(self.leasing_assumptions, DirectLeaseTerms):
            direct_terms = self.leasing_assumptions
        elif isinstance(self.leasing_assumptions, str) and lookup_fn:
            profile = lookup_fn(self.leasing_assumptions)
            if isinstance(profile, OfficeRolloverProfile):
                market_terms = profile.market_terms
        return market_terms, direct_terms

    def _resolve_start_date(self, analysis_start_date: date) -> date:
        """
        Determines the initial start date for the absorption plan.
        """
        if isinstance(self.start_date_anchor, date):
            return self.start_date_anchor
        return analysis_start_date

    def _create_lease_spec(
        self, suite: OfficeVacantSuite, start_date: date, deal_number: int, **kwargs
    ) -> Optional[OfficeLeaseSpec]:
        """
        Helper method to create a single `OfficeLeaseSpec` for a whole suite.
        """
        direct_terms = kwargs.get("direct_terms")
        profile_market_terms = kwargs.get("profile_market_terms")
        if not profile_market_terms and not direct_terms: return None

        final_terms = (direct_terms or profile_market_terms).model_copy(deep=True)
        
        return OfficeLeaseSpec(
            tenant_name=f"{self.name}-Deal{deal_number}-{suite.suite}",
            suite=suite.suite,
            floor=suite.floor,
            area=suite.area,
            use_type=suite.use_type,
            lease_type=LeaseTypeEnum.NET,
            start_date=start_date,
            term_months=final_terms.term_months,
            base_rent_value=final_terms.base_rent_value,
            base_rent_unit_of_measure=final_terms.base_rent_unit_of_measure,
            upon_expiration=final_terms.upon_expiration,
            rent_escalation=final_terms.rent_escalation,
            rent_abatement=final_terms.rent_abatement,
            recovery_method=final_terms.recovery_method,
            ti_allowance=final_terms.ti_allowance,
            leasing_commission=final_terms.leasing_commission,
        )

    def _create_subdivided_lease_spec(
        self, master_suite: OfficeVacantSuite, subdivided_area: float, sub_unit_count: int, **kwargs
    ) -> Optional[OfficeLeaseSpec]:
        """
        Creates a lease spec for a portion of a larger, divisible suite.

        This method is critical for dynamic subdivision. It creates a new lease
        spec using the terms from the plan, but with a specified `subdivided_area`
        and a unique name based on the master suite's naming pattern.

        Args:
            master_suite: The original, divisible `OfficeVacantSuite`.
            subdivided_area: The area for the new, smaller lease spec.
            sub_unit_count: The sequential number of this subdivided unit, used
                for unique naming.
            **kwargs: Additional context passed from the pace strategy.

        Returns:
            A new `OfficeLeaseSpec` for the subdivided space.
        """
        # Create a base spec using the master suite's info, but don't use its full area yet.
        # The key is to pass the correct area at creation time.
        
        # We need to get the terms from kwargs to pass them to the creator
        direct_terms = kwargs.get("direct_terms")
        profile_market_terms = kwargs.get("profile_market_terms")
        deal_number = kwargs.get("deal_number")
        start_date = kwargs.get("start_date")

        if not profile_market_terms and not direct_terms:
            return None

        final_terms = (direct_terms or profile_market_terms).model_copy(deep=True)

        return OfficeLeaseSpec(
            tenant_name=master_suite.subdivision_naming_pattern.format(
                master_suite_id=master_suite.suite,
                count=sub_unit_count
            ),
            suite=master_suite.suite, # Still links to the master suite ID
            floor=master_suite.floor,
            area=subdivided_area, # Use the subdivided area directly
            use_type=master_suite.use_type,
            lease_type=LeaseTypeEnum.NET,
            start_date=start_date,
            term_months=final_terms.term_months,
            base_rent_value=final_terms.base_rent_value,
            base_rent_unit_of_measure=final_terms.base_rent_unit_of_measure,
            upon_expiration=final_terms.upon_expiration,
            rent_escalation=final_terms.rent_escalation,
            rent_abatement=final_terms.rent_abatement,
            recovery_method=final_terms.recovery_method,
            ti_allowance=final_terms.ti_allowance,
            leasing_commission=final_terms.leasing_commission,
        )