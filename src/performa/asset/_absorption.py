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
    StartDateAnchorEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from ..core._model import Model
from ..core._settings import GlobalSettings

# Asset imports
from ._lease_spec import LeaseSpec

if TYPE_CHECKING:
    from ._lc import LeasingCommission
    from ._recovery import RecoveryMethod
    from ._rent_abatement import RentAbatement
    from ._rent_escalation import RentEscalation
    from ._rent_roll import VacantSuite
    from ._rollover import RolloverLeaseTerms, RolloverProfile
    from ._ti import TenantImprovementAllowance
    # TODO: potentially import Property context needed for filtering?

logger = logging.getLogger(__name__)

# --- External State Tracking for Dynamic Subdivision --- #

@dataclass
class SuiteAbsorptionState:
    """
    Mutable state for tracking subdivision progress of a VacantSuite during absorption.
    Used because VacantSuite is an immutable (frozen) Pydantic model.
    """
    remaining_area: float
    units_created: int = 0

# --- Supporting Structures for AbsorptionPlan --- #

# TODO (Dynamic Subdivision - Future Refinements):
# The core dynamic subdivision functionality (suite-centric with external state management)
# has been implemented. Future enhancements or considerations could include:
#
# - More Advanced Subdivision Modes:
#   - `subdivision_mode: Literal['by_number_of_units']` in addition to the current area-based logic.
#     This would allow specifying a target number of leases to divide a suite into, rather than just average area.
#   - Potentially, `target_number_of_leases: Optional[PositiveInt]` as a parameter on `VacantSuite`.
#
# - Impact on VacantSuite Inventory Management (Advanced):
#   - Currently, the original `VacantSuite` object remains unchanged, and its absorption is tracked externally.
#   - Future thought: Should there be an option for the absorption process to output a new set of
#     `VacantSuite` objects representing the *actual* subdivided spaces if that level of detail
#     is needed for other reporting or downstream processes? This would be a significant change.
#
# - Handling of Remainder Areas:
#   - Current logic leases the remainder if it meets the `subdivision_minimum_lease_area`.
#   - Further refinement on how very small, un-leasable remainders are treated or reported, if any.
#
# - Precedents for Further Ideas:
#   - Continue to draw inspiration from Argus "Space Absorption" and Rockport VAL bulk space lease-up features
#     for additional nuanced behaviors or reporting.
# FIXME: remove this comment

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

    def matches(self, suite: VacantSuite) -> bool:
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
    rent_escalation: Optional[RentEscalation] = None
    rent_abatement: Optional[RentAbatement] = None
    recovery_method: Optional[RecoveryMethod] = None
    ti_allowance: Optional[TenantImprovementAllowance] = None
    leasing_commission: Optional[LeasingCommission] = None

    # TODO: Add downtime_months override?
    # TODO: How to handle market rent if base_rent_value is None?


# --- Anchor Logic --- #


# Placeholder for more complex anchor logic if needed (e.g., relative offsets)
AnchorLogic = Any

# --- Pace Strategy Pattern --- #


@dataclass
class PaceContext:
    """
    Context object passed to PaceStrategy methods during execution.

    Attributes:
        plan_name: Name of the parent AbsorptionPlan.
        remaining_suites: A mutable list of VacantSuite objects available for leasing.
        initial_start_date: The calculated start date for the first lease/period.
        analysis_end_date: The end date of the overall analysis horizon.
        market_lease_terms: The resolved RolloverLeaseTerms (market terms) if a profile was used.
        direct_terms: The DirectLeaseTerms object if provided in the plan.
        global_settings: Global analysis settings.
        create_spec_fn: Callable reference to AbsorptionPlan._create_lease_spec (for standard suites).
        create_subdivided_spec_fn: Callable reference to AbsorptionPlan._create_subdivided_lease_spec (for F4).
        total_target_area: Total area of all suites matching the space filter initially.
        _suite_states: Dict mapping suite.suite to SuiteAbsorptionState for all target suites. All mutable state for subdivision must be tracked here, not on the VacantSuite itself. This is a private/internal field.
    """
    plan_name: str
    remaining_suites: List[VacantSuite]
    initial_start_date: date
    analysis_end_date: date
    market_lease_terms: Optional[RolloverLeaseTerms]
    direct_terms: Optional[DirectLeaseTerms]
    global_settings: Optional[GlobalSettings]
    create_spec_fn: Callable[..., Optional[LeaseSpec]]
    create_subdivided_spec_fn: Callable[..., Optional[LeaseSpec]]
    total_target_area: float
    _suite_states: dict  # suite.suite -> SuiteAbsorptionState (private)


class PaceStrategy(ABC):
    """Abstract base class for different absorption pace strategies."""

    @abstractmethod
    def generate(
        self,
        pace_model: BasePace,  # The specific pace model instance (Fixed, Equal, Custom)
        context: PaceContext,
    ) -> List[LeaseSpec]:
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
    """
    Implements the Fixed Quantity pace logic.

    Note:
        All mutable state for dynamic subdivision (such as remaining area and units created) is tracked externally using SuiteAbsorptionState objects, keyed by suite.suite, and stored in the private _suite_states field of PaceContext. Do not mutate any attribute of VacantSuite during absorption; it is an immutable (frozen) Pydantic model.
    """

    def generate(
        self, pace_model: FixedQuantityPace, context: PaceContext
    ) -> List[LeaseSpec]:
        """
        Generates LeaseSpecs by absorbing a fixed quantity (SF or Units) per period.
        Uses external SuiteAbsorptionState for all subdivision state tracking (via context._suite_states).
        """
        logger.info(
            f"  Executing FixedQuantityPaceStrategy ({pace_model.quantity} {pace_model.unit} / {pace_model.frequency_months}mo)"
        )
        generated_specs: List[LeaseSpec] = []
        current_period_start = context.initial_start_date
        absorbed_units_overall = 0
        absorbed_area_overall = 0.0
        local_remaining_suites = context.remaining_suites  # Work on the context's copy

        while (
            local_remaining_suites and current_period_start <= context.analysis_end_date
        ):
            logger.debug(f"    Processing period starting: {current_period_start}")
            area_absorbed_this_period = 0.0
            units_absorbed_this_period = 0  # Tracks LeaseSpecs generated this period
            target_quantity_for_this_period = pace_model.quantity

            suites_processed_indices_this_period: List[int] = []  # Indices of suites fully absorbed or processed

            # Iterate through available suites. Original sort is largest first.
            # The iteration might not go through all suites if period target is met early.
            for i, suite in enumerate(local_remaining_suites):
                if i in suites_processed_indices_this_period:  # Already marked for removal this period by prior divisible processing
                    continue

                current_deal_number = absorbed_units_overall + len(generated_specs) + 1

                # --- Divisible Suite Processing --- #
                if suite.is_divisible:
                    state = context._suite_states[suite.suite]
                    logger.debug(f"      Processing divisible suite: {suite.suite}, current remaining area: {state.remaining_area:.2f}")
                    while state.remaining_area > (suite.subdivision_minimum_lease_area or 0.001):
                        if pace_model.unit == "Units" and units_absorbed_this_period >= target_quantity_for_this_period:
                            logger.debug(f"        Period's UNIT target ({target_quantity_for_this_period}) met. Moving to next suite/period.")
                            break 
                        if pace_model.unit == "SF" and area_absorbed_this_period >= target_quantity_for_this_period:
                            logger.debug(f"        Period's SF target ({target_quantity_for_this_period:.2f}) met. Moving to next suite/period.")
                            break
                        area_for_this_sub_lease = suite.subdivision_average_lease_area
                        if area_for_this_sub_lease is None:
                            logger.error(f"Divisible suite {suite.suite} missing subdivision_average_lease_area.")
                            break
                        area_for_this_sub_lease = min(area_for_this_sub_lease, state.remaining_area)
                        if area_for_this_sub_lease < (suite.subdivision_minimum_lease_area or 0.001) and state.remaining_area >= (suite.subdivision_minimum_lease_area or 0.001):
                            area_for_this_sub_lease = state.remaining_area
                        if area_for_this_sub_lease < (suite.subdivision_minimum_lease_area or 0.001):
                            logger.debug(f"        Sub-lease area {area_for_this_sub_lease:.2f} for {suite.suite} is below minimum. Processing of this divisible suite ends.")
                            state.remaining_area = 0 
                            break 
                        if pace_model.unit == "SF":
                            sf_needed_for_period_target = target_quantity_for_this_period - area_absorbed_this_period
                            if area_for_this_sub_lease > sf_needed_for_period_target:
                                area_for_this_sub_lease = sf_needed_for_period_target
                                if area_for_this_sub_lease < (suite.subdivision_minimum_lease_area or 0.001):
                                    logger.debug(f"        Adjusted sub-lease area {area_for_this_sub_lease:.2f} for SF target is below minimum. Breaking from this divisible suite for the period.")
                                    break # Break from while loop of this divisible suite
                        if area_for_this_sub_lease <= 0:
                            break
                        state.units_created += 1
                        current_deal_number_for_sub = absorbed_units_overall + len(generated_specs) + 1 
                        logger.debug(f"        Attempting to create sub-lease: {suite.subdivision_naming_pattern.format(master_suite_id=suite.suite, count=state.units_created)}, Area {area_for_this_sub_lease:.0f} SF")
                        spec = context.create_subdivided_spec_fn(
                            master_suite=suite,
                            subdivided_area=area_for_this_sub_lease,
                            sub_unit_count=state.units_created,
                            start_date=current_period_start,
                            profile_market_terms=context.market_lease_terms,
                            direct_terms=context.direct_terms,
                            deal_number=current_deal_number_for_sub, 
                            global_settings=context.global_settings,
                        )
                        if spec:
                            logger.info(f"          - Created Subdivided LeaseSpec: {spec.tenant_name}, Area {spec.area:.0f} SF, Sub-unit #{state.units_created} of {suite.suite}")
                            generated_specs.append(spec)
                            area_absorbed_this_period += area_for_this_sub_lease
                            units_absorbed_this_period += 1 
                            state.remaining_area -= area_for_this_sub_lease
                        else:
                            logger.error(f"          - Failed to create Subdivided LeaseSpec for part of suite {suite.suite}")
                            state.units_created -= 1 # Rollback counter if spec creation failed
                            break # Stop processing this divisible suite if spec creation fails for some reason
                    if state.remaining_area < (suite.subdivision_minimum_lease_area or 0.001):
                        state.remaining_area = 0 # Normalize to 0
                        if i not in suites_processed_indices_this_period:
                            suites_processed_indices_this_period.append(i)
                        logger.info(f"      Divisible suite {suite.suite} fully subdivided or remainder too small. Marked for removal from main list if loop continues.")
                    continue

                # --- Standard (non-divisible) suite processing --- #
                if suite.is_divisible and state.remaining_area == 0:
                    if i not in suites_processed_indices_this_period:
                        suites_processed_indices_this_period.append(i) # Ensure it's marked for removal
                    continue # Already processed this divisible suite in a previous iteration of this period or it was too small initially

                logger.debug(f"      Processing standard suite: {suite.suite}, Area: {suite.area:.2f}")
                can_lease_standard_suite = False
                if pace_model.unit == "SF":
                    if (area_absorbed_this_period + suite.area) <= target_quantity_for_this_period:
                        can_lease_standard_suite = True
                elif pace_model.unit == "Units":
                    if units_absorbed_this_period < target_quantity_for_this_period:
                        can_lease_standard_suite = True
                if can_lease_standard_suite:
                    spec = context.create_spec_fn(
                        suite=suite,
                        start_date=current_period_start,
                        profile_market_terms=context.market_lease_terms,
                        direct_terms=context.direct_terms,
                        deal_number=current_deal_number,
                        global_settings=context.global_settings,
                    )
                    if spec:
                        logger.info(f"      - Created LeaseSpec: Deal {current_deal_number}, Suite {suite.suite}, Area {suite.area:.0f} SF")
                        generated_specs.append(spec)
                        area_absorbed_this_period += suite.area
                        units_absorbed_this_period += 1
                        if i not in suites_processed_indices_this_period:
                            suites_processed_indices_this_period.append(i)
                    else:
                        logger.error(f"        - Failed to create LeaseSpec for suite {suite.suite}")
                # else: Standard suite cannot be leased this period due to target limits

                # Check if period's target is met after processing current suite
                if pace_model.unit == "Units" and units_absorbed_this_period >= target_quantity_for_this_period:
                    logger.debug(f"    Period's UNIT target ({target_quantity_for_this_period}) met. Finalizing period.")
                    break 
                if pace_model.unit == "SF" and area_absorbed_this_period >= target_quantity_for_this_period:
                    logger.debug(f"    Period's SF target ({target_quantity_for_this_period:.2f}) met. Finalizing period.")
                    break

            # --- End of processing suites for the current period's targets ---

            if units_absorbed_this_period == 0:
                logger.debug(
                    f"    No suites or sub-suites leased in period starting {current_period_start}. Target: {target_quantity_for_this_period} {pace_model.unit}. Area absorbed: {area_absorbed_this_period:.2f}")

            else:
                absorbed_units_overall += units_absorbed_this_period
                absorbed_area_overall += area_absorbed_this_period

            # Remove fully processed suites from the main list for the next period
            if suites_processed_indices_this_period:
                logger.debug(f"    Removing {len(suites_processed_indices_this_period)} fully processed suites from consideration for next period.")
                for index in sorted(suites_processed_indices_this_period, reverse=True):
                    if index < len(local_remaining_suites):
                        del local_remaining_suites[index]
                    else:
                        logger.warning(f"      Attempted to remove suite at invalid index {index} from local_remaining_suites (length {len(local_remaining_suites)}). This might indicate an issue in tracking processed suites.")

            if not local_remaining_suites:
                logger.debug("    All suites processed. Ending absorption.")
                break
            try:
                current_period_start_dt = pd.Timestamp(current_period_start)
                current_period_start_dt = current_period_start_dt + pd.DateOffset(
                    months=pace_model.frequency_months
                )
                current_period_start = current_period_start_dt.date()
            except OverflowError:
                logger.error(
                    f"  Date overflow error when calculating next period start date from {current_period_start}. Stopping absorption."
                )
                break

        logger.info(
            f"  FixedQuantityPaceStrategy generated {len(generated_specs)} specs ({absorbed_units_overall} total LeaseSpecs created, {absorbed_area_overall:.0f} SF total area absorbed)."
        )
        return generated_specs


class EqualSpreadPaceStrategy(PaceStrategy):
    """
    Implements the Equal Spread pace logic.

    Note:
        All mutable state for dynamic subdivision (such as remaining area and units created) is tracked externally using SuiteAbsorptionState objects, keyed by suite.suite, and stored in the private _suite_states field of PaceContext. Do not mutate any attribute of VacantSuite during absorption; it is an immutable (frozen) Pydantic model.
    """
    def generate(
        self, pace_model: EqualSpreadPace, context: PaceContext
    ) -> List[LeaseSpec]:
        """
        Generates LeaseSpecs by spreading total target area evenly across a number of deals.
        Supports dynamic subdivision using external SuiteAbsorptionState (via context._suite_states).
        """
        logger.info(
            f"  Executing EqualSpreadPaceStrategy ({pace_model.total_deals} deals / {pace_model.frequency_months}mo)"
        )
        generated_specs: List[LeaseSpec] = []
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

            suites_to_remove_indices: List[int] = []

            # Greedily select suites (with subdivision support) until target area for this deal is met
            for i, suite in enumerate(local_remaining_suites):
                if area_absorbed_this_deal >= area_targeted_this_deal:
                    break
                if suite.is_divisible:
                    state = context._suite_states[suite.suite]
                    logger.debug(f"      Processing divisible suite: {suite.suite}, current remaining area: {state.remaining_area:.2f}")
                    while state.remaining_area > (suite.subdivision_minimum_lease_area or 0.001) and area_absorbed_this_deal < area_targeted_this_deal:
                        area_for_this_sub_lease = suite.subdivision_average_lease_area
                        if area_for_this_sub_lease is None:
                            logger.error(f"Divisible suite {suite.suite} missing subdivision_average_lease_area.")
                            break
                        area_for_this_sub_lease = min(area_for_this_sub_lease, state.remaining_area, area_targeted_this_deal - area_absorbed_this_deal)
                        if area_for_this_sub_lease < (suite.subdivision_minimum_lease_area or 0.001) and state.remaining_area >= (suite.subdivision_minimum_lease_area or 0.001):
                            area_for_this_sub_lease = state.remaining_area
                        if area_for_this_sub_lease < (suite.subdivision_minimum_lease_area or 0.001):
                            logger.debug(f"        Sub-lease area {area_for_this_sub_lease:.2f} for {suite.suite} is below minimum. Processing of this divisible suite ends.")
                            state.remaining_area = 0
                            break
                        if area_for_this_sub_lease <= 0:
                            break
                        state.units_created += 1
                        overall_deal_number = absorbed_units + len(generated_specs) + 1
                        logger.debug(f"        Attempting to create sub-lease: {suite.subdivision_naming_pattern.format(master_suite_id=suite.suite, count=state.units_created)}, Area {area_for_this_sub_lease:.0f} SF")
                        spec = context.create_subdivided_spec_fn(
                            master_suite=suite,
                            subdivided_area=area_for_this_sub_lease,
                            sub_unit_count=state.units_created,
                            start_date=current_deal_start_date,
                            profile_market_terms=context.market_lease_terms,
                            direct_terms=context.direct_terms,
                            deal_number=overall_deal_number,
                            global_settings=context.global_settings,
                        )
                        if spec:
                            logger.info(f"          - Created Subdivided LeaseSpec: {spec.tenant_name}, Area {spec.area:.0f} SF, Sub-unit #{state.units_created} of {suite.suite}")
                            generated_specs.append(spec)
                            absorbed_units += 1
                            absorbed_area += area_for_this_sub_lease
                            area_absorbed_this_deal += area_for_this_sub_lease
                            remaining_total_target_area -= area_for_this_sub_lease
                            state.remaining_area -= area_for_this_sub_lease
                        else:
                            logger.error(f"          - Failed to create Subdivided LeaseSpec for part of suite {suite.suite}")
                            state.units_created -= 1
                            break
                    if state.remaining_area < (suite.subdivision_minimum_lease_area or 0.001):
                        state.remaining_area = 0
                        suites_to_remove_indices.append(i)
                        logger.info(f"      Divisible suite {suite.suite} fully subdivided or remainder too small. Marked for removal from main list if loop continues.")
                    continue
                # Standard (non-divisible) suite
                if (area_absorbed_this_deal + suite.area) <= area_targeted_this_deal:
                    overall_deal_number = absorbed_units + len(generated_specs) + 1
                    spec = context.create_spec_fn(
                        suite=suite,
                        start_date=current_deal_start_date,
                        profile_market_terms=context.market_lease_terms,
                        direct_terms=context.direct_terms,
                        deal_number=overall_deal_number,
                        global_settings=context.global_settings,
                    )
                    if spec:
                        logger.info(f"      - Created LeaseSpec: Deal {overall_deal_number}, Suite {suite.suite}, Area {suite.area:.0f} SF")
                        generated_specs.append(spec)
                        absorbed_units += 1
                        absorbed_area += suite.area
                        area_absorbed_this_deal += suite.area
                        remaining_total_target_area -= suite.area
                        suites_to_remove_indices.append(i)
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
    """
    Implements the Custom Schedule pace logic.

    Note:
        All mutable state for dynamic subdivision (such as remaining area and units created) is tracked externally using SuiteAbsorptionState objects, keyed by suite.suite, and stored in the private _suite_states field of PaceContext. Do not mutate any attribute of VacantSuite during absorption; it is an immutable (frozen) Pydantic model.
    """
    def generate(
        self, pace_model: CustomSchedulePace, context: PaceContext
    ) -> List[LeaseSpec]:
        """
        Generates LeaseSpecs based on a specific date/quantity schedule.
        Supports dynamic subdivision using external SuiteAbsorptionState (via context._suite_states).
        """
        logger.info("  Executing CustomSchedulePaceStrategy")
        generated_specs: List[LeaseSpec] = []
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

            suites_to_remove_indices: List[int] = []

            # Greedily select suites (with subdivision support) until target SF for this date is met
            for i, suite in enumerate(local_remaining_suites):
                if area_absorbed_this_date >= area_targeted_this_date:
                    break
                if suite.is_divisible:
                    state = context._suite_states[suite.suite]
                    logger.debug(f"      Processing divisible suite: {suite.suite}, current remaining area: {state.remaining_area:.2f}")
                    while state.remaining_area > (suite.subdivision_minimum_lease_area or 0.001) and area_absorbed_this_date < area_targeted_this_date:
                        area_for_this_sub_lease = suite.subdivision_average_lease_area
                        if area_for_this_sub_lease is None:
                            logger.error(f"Divisible suite {suite.suite} missing subdivision_average_lease_area.")
                            break
                        area_for_this_sub_lease = min(area_for_this_sub_lease, state.remaining_area, area_targeted_this_date - area_absorbed_this_date)
                        if area_for_this_sub_lease < (suite.subdivision_minimum_lease_area or 0.001) and state.remaining_area >= (suite.subdivision_minimum_lease_area or 0.001):
                            area_for_this_sub_lease = state.remaining_area
                        if area_for_this_sub_lease < (suite.subdivision_minimum_lease_area or 0.001):
                            logger.debug(f"        Sub-lease area {area_for_this_sub_lease:.2f} for {suite.suite} is below minimum. Processing of this divisible suite ends.")
                            state.remaining_area = 0
                            break
                        if area_for_this_sub_lease <= 0:
                            break
                        state.units_created += 1
                        overall_deal_number = absorbed_units + len(generated_specs) + 1
                        logger.debug(f"        Attempting to create sub-lease: {suite.subdivision_naming_pattern.format(master_suite_id=suite.suite, count=state.units_created)}, Area {area_for_this_sub_lease:.0f} SF")
                        spec = context.create_subdivided_spec_fn(
                            master_suite=suite,
                            subdivided_area=area_for_this_sub_lease,
                            sub_unit_count=state.units_created,
                            start_date=schedule_date,
                            profile_market_terms=context.market_lease_terms,
                            direct_terms=context.direct_terms,
                            deal_number=overall_deal_number,
                            global_settings=context.global_settings,
                        )
                        if spec:
                            logger.info(f"          - Created Subdivided LeaseSpec: {spec.tenant_name}, Area {spec.area:.0f} SF, Sub-unit #{state.units_created} of {suite.suite}")
                            generated_specs.append(spec)
                            absorbed_units += 1
                            absorbed_area += area_for_this_sub_lease
                            area_absorbed_this_date += area_for_this_sub_lease
                            state.remaining_area -= area_for_this_sub_lease
                        else:
                            logger.error(f"          - Failed to create Subdivided LeaseSpec for part of suite {suite.suite}")
                            state.units_created -= 1
                            break
                    if state.remaining_area < (suite.subdivision_minimum_lease_area or 0.001):
                        state.remaining_area = 0
                        suites_to_remove_indices.append(i)
                        logger.info(f"      Divisible suite {suite.suite} fully subdivided or remainder too small. Marked for removal from main list if loop continues.")
                    continue
                # Standard (non-divisible) suite
                if (area_absorbed_this_date + suite.area) <= area_targeted_this_date:
                    overall_deal_number = absorbed_units + len(generated_specs) + 1
                    spec = context.create_spec_fn(
                        suite=suite,
                        start_date=schedule_date,  # Use the specific date from the schedule
                        profile_market_terms=context.market_lease_terms,
                        direct_terms=context.direct_terms,
                        deal_number=overall_deal_number,
                        global_settings=context.global_settings,
                    )
                    if spec:
                        logger.info(f"      - Created LeaseSpec: Deal {overall_deal_number}, Suite {suite.suite}, Area {suite.area:.0f} SF")
                        generated_specs.append(spec)
                        absorbed_units += 1
                        absorbed_area += suite.area
                        area_absorbed_this_date += suite.area
                        suites_to_remove_indices.append(i)
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

    Note:
        All mutable state for dynamic subdivision (such as remaining area and units created) is tracked externally using SuiteAbsorptionState objects, keyed by suite.suite, and stored in the private _suite_states field of PaceContext. Do not mutate any attribute of VacantSuite during absorption; it is an immutable (frozen) Pydantic model.

    The `AbsorptionPlan` is designed to model the initial lease-up of vacant space.
    It operates on a collection of `VacantSuite` objects that must be pre-defined
    in the input rent roll (e.g., via `Property.rent_roll.vacant_suites`).

    Key Concepts for Usage:
    *   **Pre-defined `VacantSuite`s:** The `AbsorptionPlan` consumes `VacantSuite`
        objects as defined in the input. Each `VacantSuite` represents a distinct,
        leasable unit of space with a specific area.
    *   **Leasing Multiple Suites (F1 Scenario):** If a property has several individual
        vacant suites, an `AbsorptionPlan` can manage their phased lease-up. Its
        `space_filter` identifies the target suites, and its `PaceStrategy` (e.g.,
        `FixedQuantityPace`, `EqualSpreadPace`) determines the timing and grouping
        for when these individual suites are leased. Each selected `VacantSuite`
        will generate one new `LeaseSpec`.
    *   **Leasing a Single Large Suite (F2 Scenario):** If a property has a single large
        vacant space to be leased to one tenant, an `AbsorptionPlan` can also model this.
        The large space should be defined as a single `VacantSuite` in the input.
        The `PaceStrategy` would typically be configured to absorb this one "unit" at a
        specific start date, generating a single `LeaseSpec` for the entire area.
    *   **No Dynamic Subdivision:** The `AbsorptionPlan` does **not** dynamically subdivide
        a single large `VacantSuite` into multiple smaller leases during its execution.
        If the modeling goal is to lease out a large block of space as several smaller,
        distinct units, these smaller units **must be defined as individual `VacantSuite`
        objects in the input `RentRoll`** prior to running the `AbsorptionPlan`.
        The `AbsorptionPlan` will then process these pre-defined smaller suites according
        to its configuration.
    *   **Leasing Assumptions:** The terms for the new leases generated by the
        `AbsorptionPlan` (rent, TIs, LCs, escalations, etc.) are defined by the
        `leasing_assumptions` attribute. This can be a `DirectLeaseTerms` object or
        a `RolloverProfileIdentifier` referencing a `RolloverProfile`.

    Workflow Example:
    1.  Define vacant inventory as a list of `VacantSuite` objects (e.g., in `RentRoll`).
        -   For a 50,000 SF floor to be leased as five 10,000 SF units, create five
            `VacantSuite` entries, each 10,000 SF.
        -   For a 50,000 SF floor to be leased to one tenant, create one `VacantSuite`
            entry of 50,000 SF.
    2.  Create an `AbsorptionPlan`, specifying:
        -   `space_filter` to target the desired `VacantSuite`(s).
        -   `pace` to control the timing and velocity of leasing.
        -   `leasing_assumptions` to define the terms for the new leases.
    3.  The `CashFlowAnalysis` process will use the `AbsorptionPlan` to generate
        `LeaseSpec` objects for the absorbed suites.

    #     these dynamically defined sub-areas.
    # - Considerations:
    #   - How to handle remainder areas if total area isn't perfectly divisible.
    #   - Impact on VacantSuite inventory management.
    #   - User interface for defining these parameters.
    # Refer to Argus "Space Absorption" feature for precedent.

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
        available_vacant_suites: List[VacantSuite],
        analysis_start_date: date,
        analysis_end_date: date,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> List[LeaseSpec]:
        """
        Generates a list of LeaseSpec objects based on the plan using Pace Strategies.

        Orchestrates the process:
        1. Filters vacant suites based on `space_filter`.
        2. Resolves the initial start date based on `start_date_anchor`.
        3. Resolves leasing terms (fetches profile market terms or uses direct terms).
        4. Selects and instantiates the appropriate `PaceStrategy` based on `pace`.
        5. Creates a `PaceContext` object with necessary data, including _suite_states for subdivision tracking.
        6. Calls the strategy's `generate` method to produce the `LeaseSpec` list.

        Note:
            All mutable state for dynamic subdivision (such as remaining area and units created) is tracked externally using SuiteAbsorptionState objects, keyed by suite.suite, and stored in the private _suite_states field of PaceContext. Do not mutate any attribute of VacantSuite during absorption; it is an immutable (frozen) Pydantic model.
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
        market_lease_terms: Optional[RolloverLeaseTerms] = None
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
        _suite_states = {suite.suite: SuiteAbsorptionState(remaining_area=suite.area) for suite in target_suites}
        context = PaceContext(
            plan_name=self.name,
            remaining_suites=target_suites.copy(),  # Pass a copy
            initial_start_date=initial_start_date,
            analysis_end_date=analysis_end_date,
            market_lease_terms=market_lease_terms,
            direct_terms=direct_terms,
            global_settings=global_settings,
            create_spec_fn=self._create_lease_spec,
            create_subdivided_spec_fn=self._create_subdivided_lease_spec,
            total_target_area=total_target_area,
            _suite_states=_suite_states,
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
    ) -> Optional[RolloverLeaseTerms]:
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
        suite: VacantSuite,
        start_date: date,
        profile_market_terms: Optional[RolloverLeaseTerms],
        direct_terms: Optional[DirectLeaseTerms],
        deal_number: int,
        global_settings: Optional[GlobalSettings],
    ) -> Optional[LeaseSpec]:
        """Helper method (called by Pace Strategies) to create a LeaseSpec for a whole suite.

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

    def _create_subdivided_lease_spec(
        self,
        suite: VacantSuite,
        start_date: date,
        profile_market_terms: Optional[RolloverLeaseTerms],
        direct_terms: Optional[DirectLeaseTerms],
        deal_number: int,
        global_settings: Optional[GlobalSettings],
    ) -> Optional[LeaseSpec]:
        """Helper method (called by Pace Strategies) to create a subdivided LeaseSpec.

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
