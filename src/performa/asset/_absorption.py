from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import Enum
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
from pydantic import Field, PositiveFloat, PositiveInt

# Core imports
from ..core._enums import (
    LeaseTypeEnum,
    ProgramUseEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from ..core._model import Model
from ._lc import LeasingCommission

# Asset imports
from ._lease import LeaseSpec, RentAbatement, RentEscalation
from ._recovery import RecoveryMethod

# Imports to resolve forward references
from ._rent_roll import VacantSuite  # noqa
from ._rollover import RolloverLeaseTerms, RolloverProfile
from ._ti import TenantImprovementAllowance

if TYPE_CHECKING:
    from ..core._settings import GlobalSettings
    from ._rent_roll import VacantSuite
    from ._rollover import RolloverLeaseTerms, RolloverProfile
    # Potentially Property context needed for filtering?

logger = logging.getLogger(__name__)

# --- Supporting Structures for AbsorptionPlan ---


class SpaceFilter(Model):
    """
    Criteria for filtering vacant space for an AbsorptionPlan.
    Defines which `VacantSuite` instances are eligible targets for the plan.
    Uses OR logic within a field (e.g., suite_ids = ['101', '102']) and
    AND logic between fields (e.g., floor=1 AND use_type=OFFICE).

    Attributes:
        suite_ids: Optional list of specific suite identifiers to target.
        floors: Optional list of floor numbers/names to target.
        use_types: Optional list of program use types (e.g., OFFICE, RETAIL) to target.
        min_area: Optional minimum area (inclusive) for a suite to be targeted.
        max_area: Optional maximum area (inclusive) for a suite to be targeted.
    """

    suite_ids: Optional[List[str]] = None
    floors: Optional[List[Union[str, int]]] = None
    use_types: Optional[List[ProgramUseEnum]] = None
    min_area: Optional[PositiveFloat] = None
    max_area: Optional[PositiveFloat] = None

    def matches(self, suite: "VacantSuite") -> bool:
        """Checks if a vacant suite matches the filter criteria."""
        # Check each filter criterion if it's defined
        if self.suite_ids and suite.suite not in self.suite_ids:
            return False
        if self.floors and suite.floor not in self.floors:
            return False
        if self.use_types and suite.use_type not in self.use_types:
            return False
        if self.min_area and suite.area < self.min_area:
            return False
        if self.max_area and suite.area > self.max_area:
            return False
        # If none of the defined filters excluded the suite, it's a match
        return True


# --- Pace Models --- #


class BasePace(Model):
    """Base class for absorption pace models. Defines how quickly space is leased."""

    # TODO: add discriminator here? or use ABC for abstractions?
    pass


class FixedQuantityPace(BasePace):
    """
    Absorbs a fixed quantity (either in square feet or number of units) per period.

    Attributes:
        type: Discriminator field for Pydantic Union.
        quantity: The amount of area (SF) or number of units to absorb.
        unit: Specifies whether `quantity` refers to "SF" or "Units".
        frequency_months: The duration of each absorption period in months (e.g., 1 for monthly, 3 for quarterly).
    """

    type: Literal["FixedQuantity"] = "FixedQuantity"
    quantity: PositiveFloat
    unit: Literal["SF", "Units"]
    frequency_months: PositiveInt = 1


class EqualSpreadPace(BasePace):
    """
    Spreads the total absorption evenly over a fixed number of deals/periods.
    Calculates a target area per deal and attempts to lease suites to meet that target.

    Attributes:
        type: Discriminator field for Pydantic Union.
        total_deals: The total number of absorption deals/periods to spread the leasing over.
        frequency_months: The time lag in months between the start dates of consecutive deals.
    """

    type: Literal["EqualSpread"] = "EqualSpread"
    total_deals: PositiveInt
    frequency_months: PositiveInt = 1


class CustomSchedulePace(BasePace):
    """
    Absorbs according to a user-defined schedule of specific dates and target absorption amounts (SF).

    Attributes:
        type: Discriminator field for Pydantic Union.
        schedule: A dictionary mapping specific dates to the target square footage to be absorbed *starting* on that date.
    """

    type: Literal["CustomSchedule"] = "CustomSchedule"
    schedule: Dict[date, PositiveFloat]  # Date -> Quantity (SF)
    # TODO: Add unit flexibility (SF vs Units)?


# --- Term Models --- #

RolloverProfileIdentifier = str  # Type alias for a string identifier (e.g., name) referencing a reusable RolloverProfile.


class DirectLeaseTerms(Model):
    """
    Specific definition of lease terms, bypassing a stored RolloverProfile.
    Mirrors relevant fields from RolloverLeaseTerms or individual components.
    Allows defining leasing assumptions directly within the AbsorptionPlan.
    Fields defined here will override corresponding fields from a RolloverProfile's market terms.

    Attributes:
        base_rent_value: Direct override for the initial base rent rate.
        base_rent_unit_of_measure: Unit for the `base_rent_value`.
        term_months: Direct override for the lease term length.
        upon_expiration: Direct override for the action upon lease expiration.
        rent_escalation: Optional override for the RentEscalation structure.
        rent_abatement: Optional override for the RentAbatement structure.
        recovery_method: Optional override for the RecoveryMethod structure.
        ti_allowance: Optional override for the TenantImprovementAllowance structure.
        leasing_commission: Optional override for the LeasingCommission structure.
    """

    # Core term definition
    base_rent_value: Optional[PositiveFloat] = None
    base_rent_unit_of_measure: Optional[UnitOfMeasureEnum] = None
    term_months: Optional[PositiveInt] = None
    upon_expiration: Optional[UponExpirationEnum] = None

    # Optional component overrides (reuse existing models)
    rent_escalation: Optional["RentEscalation"] = None
    rent_abatement: Optional["RentAbatement"] = None
    recovery_method: Optional["RecoveryMethod"] = None
    ti_allowance: Optional["TenantImprovementAllowance"] = None
    leasing_commission: Optional["LeasingCommission"] = None

    # TODO: Add downtime_months override?
    # TODO: How to handle market rent if base_rent_value is None?


# --- Anchor Logic --- #


# FIXME: this is now living in core/_enums.py
class StartDateAnchorEnum(str, Enum):
    """Defines how the absorption start date is determined."""

    ANALYSIS_START = "AnalysisStart"  # Start immediately at the analysis start date.
    # RELATIVE_DATE = "RelativeDate" # Placeholder: Start after a specific offset from analysis start.
    # MILESTONE = "Milestone" # Placeholder: Start relative to a development milestone.
    # FIXED_DATE = "FixedDate" # Implicitly handled by passing a date object.


# Placeholder for more complex anchor logic if needed (e.g., relative offsets)
AnchorLogic = Any

# --- Pace Strategy Pattern --- #


@dataclass
class PaceContext:
    """Context object passed to PaceStrategy methods during execution.

    Attributes:
        plan_name: Name of the parent AbsorptionPlan.
        remaining_suites: A mutable list of VacantSuite objects available for leasing.
                          Strategies should remove suites from this list as they are leased.
        initial_start_date: The calculated start date for the first lease/period.
        analysis_end_date: The end date of the overall analysis horizon.
        market_lease_terms: The resolved RolloverLeaseTerms (market terms) if a profile was used.
        direct_terms: The DirectLeaseTerms object if provided in the plan.
        global_settings: Global analysis settings.
        create_spec_fn: Callable reference to AbsorptionPlan._create_lease_spec.
        total_target_area: Total area of all suites matching the space filter initially.
    """

    plan_name: str
    remaining_suites: List["VacantSuite"]
    initial_start_date: date
    analysis_end_date: date
    market_lease_terms: Optional["RolloverLeaseTerms"]
    direct_terms: Optional[DirectLeaseTerms]
    global_settings: Optional["GlobalSettings"]
    create_spec_fn: Callable[..., Optional["LeaseSpec"]]
    total_target_area: float


class PaceStrategy(ABC):
    """Abstract base class for different absorption pace strategies."""

    @abstractmethod
    def generate(
        self,
        pace_model: BasePace,  # The specific pace model instance (Fixed, Equal, Custom)
        context: PaceContext,
    ) -> List["LeaseSpec"]:
        """Generates LeaseSpec objects based on the pace logic.

        Args:
            pace_model: The specific pace configuration object (e.g., FixedQuantityPace).
            context: The PaceContext containing necessary data and helpers.

        Returns:
            A list of generated LeaseSpec objects.
        """
        pass


# --- Concrete Pace Strategy Implementations --- #


class FixedQuantityPaceStrategy(PaceStrategy):
    """Implements the Fixed Quantity pace logic."""

    def generate(
        self, pace_model: FixedQuantityPace, context: PaceContext
    ) -> List["LeaseSpec"]:
        """Generates LeaseSpecs by absorbing a fixed quantity (SF or Units) per period."""
        logger.info(
            f"  Executing FixedQuantityPaceStrategy ({pace_model.quantity} {pace_model.unit} / {pace_model.frequency_months}mo)"
        )
        generated_specs: List["LeaseSpec"] = []
        current_period_start = context.initial_start_date
        absorbed_units = 0
        absorbed_area = 0.0
        local_remaining_suites = context.remaining_suites  # Work on the context's copy

        while (
            local_remaining_suites and current_period_start <= context.analysis_end_date
        ):
            logger.debug(f"    Processing period starting: {current_period_start}")
            area_absorbed_this_period = 0.0
            units_absorbed_this_period = 0
            target_quantity_this_period = pace_model.quantity

            suites_leased_this_period: List["VacantSuite"] = []
            suites_to_remove_indices: List[int] = []

            # Iterate through available suites (currently largest first due to initial sort)
            for i, suite in enumerate(local_remaining_suites):
                if pace_model.unit == "SF":
                    # Check if adding this suite fits within the remaining target SF for the period
                    if (
                        area_absorbed_this_period + suite.area
                        <= target_quantity_this_period
                    ):
                        area_absorbed_this_period += suite.area
                        units_absorbed_this_period += 1
                        suites_leased_this_period.append(suite)
                        suites_to_remove_indices.append(i)
                    # Simple greedy approach: If the largest remaining suite doesn't fit, we don't try smaller ones this period.
                    # Could be enhanced later to pack smaller suites if needed.
                    # TODO: Enhance SF leasing logic to potentially pack smaller suites if the largest doesn't fit the remaining target.
                elif pace_model.unit == "Units":
                    # Check if we've hit the target unit count for the period
                    if units_absorbed_this_period < target_quantity_this_period:
                        area_absorbed_this_period += (
                            suite.area
                        )  # Track area even if target is units
                        units_absorbed_this_period += 1
                        suites_leased_this_period.append(suite)
                        suites_to_remove_indices.append(i)
                    else:
                        break  # Reached target units for this period

            if not suites_leased_this_period:
                logger.debug(
                    f"    No suites could be leased in period starting {current_period_start} (target: {target_quantity_this_period} {pace_model.unit})."
                )
            else:
                logger.debug(
                    f"    Leasing {len(suites_leased_this_period)} suite(s) in period starting {current_period_start}:"
                )
                for suite_to_lease in suites_leased_this_period:
                    deal_number = absorbed_units + 1  # Overall deal number
                    # Call the creation function passed via context
                    spec = context.create_spec_fn(
                        suite=suite_to_lease,
                        start_date=current_period_start,
                        profile_market_terms=context.market_lease_terms,
                        direct_terms=context.direct_terms,
                        deal_number=deal_number,
                        global_settings=context.global_settings,
                    )
                    if spec:
                        generated_specs.append(spec)
                        absorbed_units += 1
                        absorbed_area += suite_to_lease.area
                        logger.debug(
                            f"      - Created LeaseSpec: Deal {deal_number}, Suite {suite_to_lease.suite}, Area {suite_to_lease.area:.0f} SF"
                        )
                    else:
                        logger.error(
                            f"      - Failed to create LeaseSpec for suite {suite_to_lease.suite}"
                        )

                # Remove leased suites from the local list (important: operate on context.remaining_suites)
                for index in sorted(suites_to_remove_indices, reverse=True):
                    del local_remaining_suites[index]

            # Move to the next period start date
            try:
                # Use Timestamp for robust date arithmetic
                current_period_start_dt = pd.Timestamp(current_period_start)
                current_period_start_dt = current_period_start_dt + pd.DateOffset(
                    months=pace_model.frequency_months
                )
                current_period_start = current_period_start_dt.date()
            except OverflowError:
                logger.error(
                    f"  Date overflow error when calculating next period start date from {current_period_start}. Stopping absorption."
                )
                break  # Stop if date calculation fails

        logger.info(
            f"  FixedQuantityPaceStrategy generated {len(generated_specs)} specs ({absorbed_units} units, {absorbed_area:.0f} SF)."
        )
        return generated_specs


class EqualSpreadPaceStrategy(PaceStrategy):
    """Implements the Equal Spread pace logic."""

    def generate(
        self, pace_model: EqualSpreadPace, context: PaceContext
    ) -> List["LeaseSpec"]:
        """Generates LeaseSpecs by spreading total target area evenly across a number of deals."""
        logger.info(
            f"  Executing EqualSpreadPaceStrategy ({pace_model.total_deals} deals / {pace_model.frequency_months}mo)"
        )
        generated_specs: List["LeaseSpec"] = []
        current_deal_start_date = context.initial_start_date
        absorbed_units = 0
        absorbed_area = 0.0
        local_remaining_suites = context.remaining_suites
        remaining_total_target_area = (
            context.total_target_area
        )  # Track overall remaining area

        if pace_model.total_deals <= 0:
            logger.warning(
                "  EqualSpreadPace has total_deals <= 0. No leases generated."
            )
            return []

        target_area_per_deal = (
            (context.total_target_area / pace_model.total_deals)
            if pace_model.total_deals > 0
            else 0
        )
        logger.debug(
            f"    Total Target Area: {context.total_target_area:.0f} SF, Target Area Per Deal: {target_area_per_deal:.0f} SF"
        )

        # Loop through each deal period
        for deal_num in range(1, pace_model.total_deals + 1):
            if (
                not local_remaining_suites
                or current_deal_start_date > context.analysis_end_date
            ):
                logger.warning(
                    f"  Stopping EqualSpreadPace early after {deal_num-1} deals due to lack of suites or exceeding analysis end date."
                )
                break

            logger.debug(
                f"    Processing Deal #{deal_num} starting: {current_deal_start_date}"
            )
            # Target for this specific deal, capped by overall remaining area
            area_targeted_this_deal = min(
                target_area_per_deal, remaining_total_target_area
            )
            area_absorbed_this_deal = 0.0
            logger.debug(
                f"      Target Area for Deal #{deal_num}: {area_targeted_this_deal:.0f} SF (Remaining Total: {remaining_total_target_area:.0f} SF)"
            )

            suites_leased_this_deal: List["VacantSuite"] = []
            suites_to_remove_indices: List[int] = []

            # Greedily select largest suites until target area for this deal is met
            for i, suite in enumerate(local_remaining_suites):
                if area_absorbed_this_deal < area_targeted_this_deal:
                    suites_leased_this_deal.append(suite)
                    suites_to_remove_indices.append(i)
                    area_absorbed_this_deal += suite.area
                    # Stop once the target for *this specific deal* is met or exceeded
                    if area_absorbed_this_deal >= area_targeted_this_deal:
                        break
                else:
                    break  # Already met the target area for this deal

            if not suites_leased_this_deal:
                logger.warning(
                    f"    No suites could be leased for Deal #{deal_num} starting {current_deal_start_date}"
                )
            else:
                logger.debug(
                    f"    Leasing {len(suites_leased_this_deal)} suite(s) for Deal #{deal_num}:"
                )
                for suite_to_lease in suites_leased_this_deal:
                    overall_deal_number = absorbed_units + 1
                    spec = context.create_spec_fn(
                        suite=suite_to_lease,
                        start_date=current_deal_start_date,
                        profile_market_terms=context.market_lease_terms,
                        direct_terms=context.direct_terms,
                        deal_number=overall_deal_number,
                        global_settings=context.global_settings,
                    )
                    if spec:
                        generated_specs.append(spec)
                        absorbed_units += 1
                        absorbed_area += suite_to_lease.area
                        remaining_total_target_area -= (
                            suite_to_lease.area
                        )  # Decrease overall remaining area
                        logger.debug(
                            f"      - Created LeaseSpec: Deal {overall_deal_number}, Suite {suite_to_lease.suite}, Area {suite_to_lease.area:.0f} SF"
                        )
                    else:
                        logger.error(
                            f"      - Failed to create LeaseSpec for suite {suite_to_lease.suite}"
                        )

                # Remove leased suites from the shared remaining list
                for index in sorted(suites_to_remove_indices, reverse=True):
                    del local_remaining_suites[index]

            # Increment date for the next deal
            if deal_num < pace_model.total_deals:
                try:
                    current_deal_start_date_dt = pd.Timestamp(current_deal_start_date)
                    current_deal_start_date_dt = (
                        current_deal_start_date_dt
                        + pd.DateOffset(months=pace_model.frequency_months)
                    )
                    current_deal_start_date = current_deal_start_date_dt.date()
                except OverflowError:
                    logger.error(
                        f"  Date overflow error calculating next deal start date from {current_deal_start_date}. Stopping absorption."
                    )
                    break

        logger.info(
            f"  EqualSpreadPaceStrategy generated {len(generated_specs)} specs ({absorbed_units} units, {absorbed_area:.0f} SF)."
        )
        return generated_specs


class CustomSchedulePaceStrategy(PaceStrategy):
    """Implements the Custom Schedule pace logic."""

    def generate(
        self, pace_model: CustomSchedulePace, context: PaceContext
    ) -> List["LeaseSpec"]:
        """Generates LeaseSpecs based on a specific date/quantity schedule."""
        logger.info("  Executing CustomSchedulePaceStrategy")
        generated_specs: List["LeaseSpec"] = []
        absorbed_units = 0
        absorbed_area = 0.0
        local_remaining_suites = context.remaining_suites

        if not pace_model.schedule:
            logger.warning(
                "  CustomSchedulePace has an empty schedule. No leases generated."
            )
            return []

        sorted_schedule = sorted(pace_model.schedule.items())

        # Iterate through the defined schedule points
        for schedule_date, quantity_sf in sorted_schedule:
            if not local_remaining_suites:
                logger.warning(
                    f"  Stopping CustomSchedulePace early as no vacant suites remain before processing schedule date {schedule_date}."
                )
                break

            if schedule_date > context.analysis_end_date:
                logger.warning(
                    f"  Skipping schedule entry for {schedule_date} as it is after analysis end date {context.analysis_end_date}."
                )
                continue

            if quantity_sf <= 0:
                logger.warning(
                    f"  Skipping schedule entry for {schedule_date} as quantity_sf is not positive ({quantity_sf})."
                )
                continue

            logger.debug(
                f"    Processing Schedule Date: {schedule_date}, Target SF: {quantity_sf:.0f}"
            )
            area_targeted_this_date = quantity_sf
            area_absorbed_this_date = 0.0

            suites_leased_this_date: List["VacantSuite"] = []
            suites_to_remove_indices: List[int] = []

            # Greedily select largest suites until target SF for this date is met
            for i, suite in enumerate(local_remaining_suites):
                if area_absorbed_this_date < area_targeted_this_date:
                    suites_leased_this_date.append(suite)
                    suites_to_remove_indices.append(i)
                    area_absorbed_this_date += suite.area
                    if area_absorbed_this_date >= area_targeted_this_date:
                        break  # Met or exceeded target area for this specific date
                else:
                    break  # Already met target area

            if not suites_leased_this_date:
                logger.warning(
                    f"    No suites could be leased for schedule date {schedule_date} (Target SF: {quantity_sf:.0f})."
                )
            else:
                logger.debug(
                    f"    Leasing {len(suites_leased_this_date)} suite(s) for schedule date {schedule_date}:"
                )
                for suite_to_lease in suites_leased_this_date:
                    overall_deal_number = absorbed_units + 1
                    spec = context.create_spec_fn(
                        suite=suite_to_lease,
                        start_date=schedule_date,  # Use the specific date from the schedule
                        profile_market_terms=context.market_lease_terms,
                        direct_terms=context.direct_terms,
                        deal_number=overall_deal_number,
                        global_settings=context.global_settings,
                    )
                    if spec:
                        generated_specs.append(spec)
                        absorbed_units += 1
                        absorbed_area += suite_to_lease.area
                        # remaining_target_area from context isn't decremented here, target is per-date
                        logger.debug(
                            f"      - Created LeaseSpec: Deal {overall_deal_number}, Suite {suite_to_lease.suite}, Area {suite_to_lease.area:.0f} SF"
                        )
                    else:
                        logger.error(
                            f"      - Failed to create LeaseSpec for suite {suite_to_lease.suite}"
                        )

                # Remove leased suites from the shared remaining list
                for index in sorted(suites_to_remove_indices, reverse=True):
                    del local_remaining_suites[index]

        logger.info(
            f"  CustomSchedulePaceStrategy generated {len(generated_specs)} specs ({absorbed_units} units, {absorbed_area:.0f} SF)."
        )
        return generated_specs


# --- Absorption Plan --- #


class AbsorptionPlan(Model):
    """
    Defines a plan for leasing up vacant space over time.
    Generates LeaseSpec objects based on configured pace and leasing assumptions.
    Uses the Strategy pattern to delegate pace logic implementation.

    Attributes:
        name: A descriptive name for this absorption plan.
        space_filter: Criteria used to select target VacantSuite inventory.
        start_date_anchor: Determines the start date for the first absorption period/deal.
                           Can be a fixed date, relative to analysis start, or linked to a milestone (future).
        pace: The pace configuration object (FixedQuantityPace, EqualSpreadPace, or CustomSchedulePace)
              defining how quickly the filtered space should be leased.
        leasing_assumptions: Defines the economic terms for the generated leases.
                               Can be an identifier for a reusable RolloverProfile (from which market terms are used)
                               or a DirectLeaseTerms object defining terms explicitly.
    """

    name: str
    space_filter: SpaceFilter
    start_date_anchor: Union[date, StartDateAnchorEnum, AnchorLogic]
    pace: Annotated[
        Union[FixedQuantityPace, EqualSpreadPace, CustomSchedulePace],
        Field(discriminator="type"),
    ]
    leasing_assumptions: Union[RolloverProfileIdentifier, DirectLeaseTerms]

    def generate_lease_specs(
        self,
        available_vacant_suites: List["VacantSuite"],
        analysis_start_date: date,
        analysis_end_date: date,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional["GlobalSettings"] = None,
    ) -> List["LeaseSpec"]:
        """
        Generates a list of LeaseSpec objects based on the plan using Pace Strategies.

        Orchestrates the process:
        1. Filters vacant suites based on `space_filter`.
        2. Resolves the initial start date based on `start_date_anchor`.
        3. Resolves leasing terms (fetches profile market terms or uses direct terms).
        4. Selects and instantiates the appropriate `PaceStrategy` based on `pace`.
        5. Creates a `PaceContext` object with necessary data.
        6. Calls the strategy's `generate` method to produce the `LeaseSpec` list.

        Args:
            available_vacant_suites: List of VacantSuite objects representing the current inventory.
            analysis_start_date: Start date of the overall analysis.
            analysis_end_date: End date of the overall analysis.
            lookup_fn: Function to resolve references (e.g., RolloverProfileIdentifier).
            global_settings: Global analysis settings.

        Returns:
            A list of generated LeaseSpec objects, or an empty list if no leases are generated.
        """
        logger.info(f"Generating lease specs for AbsorptionPlan: '{self.name}'")
        # Result list initialization moved inside generate method

        # 1. Filter relevant vacant suites
        target_suites = sorted(
            [
                suite
                for suite in available_vacant_suites
                if self.space_filter.matches(suite)
            ],
            key=lambda s: s.area,
            reverse=True,  # Default: lease largest suites first
        )
        total_target_area = sum(s.area for s in target_suites)
        if not target_suites:
            logger.warning(
                f"  No vacant suites match filter for plan '{self.name}'. Returning empty list."
            )
            return []
        logger.debug(
            f"  Target suites ({len(target_suites)} units, {total_target_area:.0f} SF): {[s.suite for s in target_suites]}"
        )

        # 2. Determine the actual start date for the *first* deal/period
        initial_start_date = self._resolve_start_date(analysis_start_date)
        if initial_start_date > analysis_end_date:
            logger.warning(
                f"  Resolved initial lease start date ({initial_start_date}) is after analysis end date ({analysis_end_date}). No leases will be generated."
            )
            return []
        logger.debug(f"  Resolved initial lease start date: {initial_start_date}")

        # 3. Determine lease terms
        market_lease_terms: Optional["RolloverLeaseTerms"] = None
        direct_terms: Optional[DirectLeaseTerms] = None
        if isinstance(self.leasing_assumptions, DirectLeaseTerms):
            direct_terms = self.leasing_assumptions
            logger.debug("  Using DirectLeaseTerms.")
        elif isinstance(self.leasing_assumptions, str):
            profile_id = self.leasing_assumptions
            market_lease_terms = self._resolve_market_terms_from_profile(
                profile_id, lookup_fn
            )
            if not market_lease_terms:
                logger.error(
                    f"  Could not resolve market terms from profile '{profile_id}'. Cannot generate specs."
                )
                return []
            logger.debug(f"  Resolved market terms from profile: '{profile_id}'")
        else:
            logger.error(
                f"  Invalid leasing_assumptions type: {type(self.leasing_assumptions)}. Cannot generate specs."
            )
            return []
        if not market_lease_terms and not direct_terms:
            logger.error("  No valid lease terms found. Cannot generate specs.")
            return []

        # 4. Select and Execute Pace Strategy
        strategy: Optional[PaceStrategy] = None
        if isinstance(self.pace, FixedQuantityPace):
            strategy = FixedQuantityPaceStrategy()
        elif isinstance(self.pace, EqualSpreadPace):
            strategy = EqualSpreadPaceStrategy()
        elif isinstance(self.pace, CustomSchedulePace):
            strategy = CustomSchedulePaceStrategy()
        # No else needed, Pydantic discriminated union ensures self.pace is one of these

        # 5. Prepare Context and Generate
        context = PaceContext(
            plan_name=self.name,
            remaining_suites=target_suites.copy(),  # Pass a copy
            initial_start_date=initial_start_date,
            analysis_end_date=analysis_end_date,
            market_lease_terms=market_lease_terms,
            direct_terms=direct_terms,
            global_settings=global_settings,
            create_spec_fn=self._create_lease_spec,
            total_target_area=total_target_area,
        )

        generated_specs = strategy.generate(self.pace, context)

        logger.info(
            f"Finished generating {len(generated_specs)} specs for plan '{self.name}'"
        )
        return generated_specs

    def _resolve_start_date(self, analysis_start_date: date) -> date:
        """Determines the actual start date for the absorption plan based on the anchor."""
        if isinstance(self.start_date_anchor, date):
            return self.start_date_anchor
        elif self.start_date_anchor == StartDateAnchorEnum.ANALYSIS_START:
            return analysis_start_date
        # TODO: Implement other AnchorLogic types (RELATIVE_DATE, MILESTONE)
        else:
            logger.warning(
                f"Unknown/unhandled start_date_anchor: {self.start_date_anchor}. Defaulting to analysis start date."
            )
            return analysis_start_date

    def _resolve_market_terms_from_profile(
        self,
        profile_identifier: RolloverProfileIdentifier,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]],
    ) -> Optional["RolloverLeaseTerms"]:
        """Fetches a RolloverProfile using the lookup function and returns its market terms.

        Assumes the lookup_fn can resolve the identifier to a RolloverProfile object.
        Returns None if lookup fails, profile is wrong type, or profile lacks market_terms.
        """
        if not lookup_fn:
            logger.error(
                f"lookup_fn required to resolve RolloverProfileIdentifier '{profile_identifier}'"
            )
            return None
        try:
            profile = lookup_fn(profile_identifier)
            if isinstance(profile, RolloverProfile):
                # Access the market_terms attribute directly
                if hasattr(profile, "market_terms") and isinstance(
                    profile.market_terms, RolloverLeaseTerms
                ):
                    logger.debug(
                        f"  Extracted market terms from profile '{profile_identifier}'"
                    )
                    return profile.market_terms
                else:
                    logger.error(
                        f"  RolloverProfile '{profile_identifier}' does not have valid 'market_terms' attribute."
                    )
                    return None
            else:
                logger.error(
                    f"  Lookup for profile '{profile_identifier}' did not return RolloverProfile object, got {type(profile)}."
                )
                return None
        except Exception as e:
            logger.error(
                f"  Error looking up profile '{profile_identifier}': {e}", exc_info=True
            )
            return None

    def _create_lease_spec(
        self,
        suite: "VacantSuite",
        start_date: date,
        profile_market_terms: Optional["RolloverLeaseTerms"],
        direct_terms: Optional[DirectLeaseTerms],
        deal_number: int,
        global_settings: Optional["GlobalSettings"],
    ) -> Optional["LeaseSpec"]:
        """Helper method (called by Pace Strategies) to create a LeaseSpec.

        Populates a LeaseSpec object using either directly defined terms
        (DirectLeaseTerms) or terms derived from a resolved RolloverProfile's
        market terms (RolloverLeaseTerms).

        Prioritization: DirectLeaseTerms fields override RolloverLeaseTerms fields.

        Args:
            suite: The VacantSuite being leased for this deal.
            start_date: The calculated start date for this specific lease spec.
            profile_market_terms: The resolved market terms from a RolloverProfile (if used).
            direct_terms: The directly defined terms from the AbsorptionPlan (if used).
            deal_number: A sequential number for the generated lease/deal (for naming).
            global_settings: Global analysis settings (needed for rent calculation).

        Returns:
            A populated LeaseSpec object, or None if essential terms cannot be determined.
        """
        from ._lease import LeaseSpec  # Local import

        if not profile_market_terms and not direct_terms:
            logger.error(
                f"  Cannot create lease spec for suite {suite.suite} without profile market terms or direct terms."
            )
            return None

        # --- Determine Lease Parameters (Direct > Profile Market > Default) --- #
        _term_months: Optional[int] = None
        _base_rent_value: Optional[float] = None
        _base_rent_uom: Optional[UnitOfMeasureEnum] = None
        _upon_expiration: Optional[UponExpirationEnum] = None
        _rent_escalation: Optional[RentEscalation] = None
        _rent_abatement: Optional[RentAbatement] = None
        _recovery_method: Optional[RecoveryMethod] = None
        _ti_allowance: Optional[TenantImprovementAllowance] = None
        _leasing_commission: Optional[LeasingCommission] = None
        _rollover_profile_ref: Optional[str] = None

        # Prioritize DirectLeaseTerms
        if direct_terms:
            _term_months = direct_terms.term_months
            _base_rent_value = direct_terms.base_rent_value
            _base_rent_uom = direct_terms.base_rent_unit_of_measure
            _upon_expiration = direct_terms.upon_expiration
            _rent_escalation = direct_terms.rent_escalation
            _rent_abatement = direct_terms.rent_abatement
            _recovery_method = direct_terms.recovery_method
            _ti_allowance = direct_terms.ti_allowance
            _leasing_commission = direct_terms.leasing_commission
            # Note: rollover_profile_ref typically comes from the profile, not direct override

        # Fallback to RolloverProfile Market Terms (if not set by direct_terms)
        if profile_market_terms:
            # Basic terms
            if _term_months is None:
                _term_months = profile_market_terms.term_months
            # Note: RolloverLeaseTerms doesn't typically define upon_expiration directly, it's part of the Profile
            # We'll rely on the override or a default for upon_expiration for the *generated* lease.

            # Components (deep copy needed to avoid modifying shared profile terms)
            if _rent_escalation is None:
                _rent_escalation = (
                    profile_market_terms.rent_escalation.model_copy(deep=True)
                    if profile_market_terms.rent_escalation
                    else None
                )
            if _rent_abatement is None:
                _rent_abatement = (
                    profile_market_terms.rent_abatement.model_copy(deep=True)
                    if profile_market_terms.rent_abatement
                    else None
                )
            if _recovery_method is None:
                _recovery_method = (
                    profile_market_terms.recovery_method.model_copy(deep=True)
                    if profile_market_terms.recovery_method
                    else None
                )
            if _ti_allowance is None:
                _ti_allowance = (
                    profile_market_terms.ti_allowance.model_copy(deep=True)
                    if profile_market_terms.ti_allowance
                    else None
                )
            if _leasing_commission is None:
                _leasing_commission = (
                    profile_market_terms.leasing_commission.model_copy(deep=True)
                    if profile_market_terms.leasing_commission
                    else None
                )

            # Rent value/UoM calculation requires calling the profile's logic
            if _base_rent_value is None:
                try:
                    # Assuming RolloverLeaseTerms has _calculate_rent method
                    _base_rent_value = profile_market_terms._calculate_rent(
                        term_config=profile_market_terms,
                        rollover_date=start_date,
                        global_settings=global_settings,
                    )
                    _base_rent_uom = profile_market_terms.unit_of_measure
                except AttributeError:
                    logger.error(
                        f"  Profile market terms object {type(profile_market_terms)} missing expected '_calculate_rent' or 'unit_of_measure'. Cannot determine base rent."
                    )
                    return None
                except Exception as e:
                    logger.error(
                        f"  Error calculating base rent from profile market terms for deal {deal_number}: {e}",
                        exc_info=True,
                    )
                    return None
            elif _base_rent_uom is None:
                # Use UoM from profile if rent value was overridden directly
                _base_rent_uom = profile_market_terms.unit_of_measure

            # Determine rollover profile ref (needs a way to link back from terms to parent profile)
            if _rollover_profile_ref is None:
                # If the terms came from a profile, assume the generated lease uses the *same* profile for its rollover
                # Find the identifier of the profile that these market terms belong to.
                # This requires the lookup function or context to provide this reverse mapping, or the profile itself.
                # For now, we don't have a clean way, leave as None or try to get from direct_terms if provided.
                # TODO: Improve determination of rollover_profile_ref for generated specs to ensure subsequent rollovers function correctly.
                logger.warning(
                    f"  Cannot determine RolloverProfile reference for generated LeaseSpec Deal {deal_number}. Subsequent rollovers may fail."
                )
                # Example placeholder if direct_terms could specify it:
                # _rollover_profile_ref = direct_terms.rollover_profile_ref if direct_terms and direct_terms.rollover_profile_ref else None

        # Apply Defaults / Final Checks (should ideally rely on RLA/Override having required fields)
        if _term_months is None:
            _term_months = 60
            logger.warning(
                f"  Using default term_months ({_term_months}) for deal {deal_number}"
            )
        if _base_rent_value is None or _base_rent_value <= 0:
            logger.error(
                f"  Invalid base_rent_value ({_base_rent_value}) determined for deal {deal_number}"
            )
            return None
        if _base_rent_uom is None:
            _base_rent_uom = UnitOfMeasureEnum.PER_UNIT
            logger.warning(
                f"  Using default base_rent_uom ({_base_rent_uom}) for deal {deal_number}"
            )
        # Set a default upon_expiration if still None after checking override/profile(which likely doesn't have it)
        if _upon_expiration is None:
            _upon_expiration = UponExpirationEnum.MARKET
            logger.warning(
                f"  Using default upon_expiration ({_upon_expiration}) for deal {deal_number}"
            )

        # Map suite use type to lease type
        lease_type_mapping = {ProgramUseEnum.OFFICE: LeaseTypeEnum.NET}
        lease_type = lease_type_mapping.get(suite.use_type, LeaseTypeEnum.NET)

        # --- Create and Return LeaseSpec --- #
        try:
            spec = LeaseSpec(
                tenant_name=f"{self.name}-Deal{deal_number}-{suite.suite}",
                suite=suite.suite,
                floor=suite.floor,
                area=suite.area,
                use_type=suite.use_type,
                lease_type=lease_type,
                start_date=start_date,
                term_months=_term_months,
                end_date=None,
                base_rent_value=_base_rent_value,
                base_rent_unit_of_measure=_base_rent_uom,
                rent_escalation=_rent_escalation,
                rent_abatement=_rent_abatement,
                recovery_method=_recovery_method,
                ti_allowance=_ti_allowance,
                leasing_commission=_leasing_commission,
                upon_expiration=_upon_expiration,
                rollover_profile_ref=_rollover_profile_ref,
                source="AbsorptionPlan",
            )
            logger.debug(
                f"    Successfully created LeaseSpec for deal {deal_number} / suite {suite.suite}"
            )
            return spec
        except Exception as e:
            logger.error(
                f"    Failed to create LeaseSpec for deal {deal_number} / suite {suite.suite}: {e}",
                exc_info=True,
            )
            return None
