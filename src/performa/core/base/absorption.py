# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
)
from uuid import UUID, uuid4

from pydantic import Field

from ..primitives.cash_flow import ReferenceKey
from ..primitives.enums import (
    FrequencyEnum,
    ProgramUseEnum,
    StartDateAnchorEnum,
    UponExpirationEnum,
)
from ..primitives.growth_rates import PercentageGrowthRate
from ..primitives.model import Model
from ..primitives.settings import GlobalSettings
from ..primitives.types import PositiveFloat, PositiveInt
from .cost import LeasingCommissionBase, TenantImprovementAllowanceBase
from .lease import LeaseSpecBase
from .lease_components import RentAbatementBase, RentEscalationBase
from .recovery import RecoveryMethodBase
from .rent_roll import VacantSuiteBase
from .rollover import RolloverLeaseTermsBase

logger = logging.getLogger(__name__)

# Generic TypeVar parameters for stabilized operating assumptions
#
# These create type constraints ensuring office absorption plans accept only office expense types,
# residential plans accept only residential types, etc.
#
# Example:
#   class OfficeAbsorptionPlan(AbsorptionPlanBase[OfficeExpenses, OfficeLosses, OfficeMiscIncome]):
#       pass  # Can only accept OfficeExpenses, not ResidentialExpenses
#
ExpenseType = TypeVar("ExpenseType", bound=Model)  # Asset-specific expense assumptions
LossesType = TypeVar("LossesType", bound=Model)  # Asset-specific loss assumptions
MiscIncomeType = TypeVar(
    "MiscIncomeType", bound=Model
)  # Asset-specific misc income assumptions


@dataclass
class SuiteAbsorptionState:
    remaining_area: float
    units_created: int = 0

    def absorb_area(self, area: float) -> None:
        self.remaining_area = max(0, self.remaining_area - area)

    def create_unit(self) -> None:
        self.units_created += 1

    @property
    def fully_absorbed(self) -> bool:
        return (
            self.remaining_area <= 0.01
        )  # Small tolerance for floating point comparison

    @property
    def has_available_area(self) -> bool:
        return self.remaining_area > 0.01


class SpaceFilter(Model):
    suite_ids: Optional[List[str]] = None
    floors: Optional[List[Union[str, int]]] = None
    use_types: Optional[List[ProgramUseEnum]] = None
    min_area: Optional[PositiveFloat] = None
    max_area: Optional[PositiveFloat] = None

    def matches(self, suite: "VacantSuiteBase") -> bool:
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
        return True


class BasePace(Model, ABC):
    # FIXME: add a discriminator field to the model on `type`?
    pass


class FixedQuantityPace(BasePace):
    type: Literal["FixedQuantity"] = "FixedQuantity"
    quantity: PositiveFloat
    unit: Literal["SF", "Units"]
    frequency_months: PositiveInt = 1


class EqualSpreadPace(BasePace):
    type: Literal["EqualSpread"] = "EqualSpread"
    total_deals: PositiveInt
    frequency_months: PositiveInt = 1


class CustomSchedulePace(BasePace):
    type: Literal["CustomSchedule"] = "CustomSchedule"
    schedule: Dict[date, PositiveFloat]


RolloverProfileIdentifier = str


class DirectLeaseTerms(Model):
    base_rent_value: Optional[PositiveFloat] = None
    base_rent_reference: Optional[ReferenceKey] = None
    base_rent_frequency: FrequencyEnum = FrequencyEnum.MONTHLY  # Keep existing default behavior
    term_months: Optional[PositiveInt] = None
    upon_expiration: Optional[UponExpirationEnum] = None
    rent_escalation: Optional["RentEscalationBase"] = None
    rent_abatement: Optional["RentAbatementBase"] = None
    recovery_method: Optional["RecoveryMethodBase"] = None
    ti_allowance: Optional["TenantImprovementAllowanceBase"] = None
    leasing_commission: Optional["LeasingCommissionBase"] = None
    market_rent_growth: Optional[PercentageGrowthRate] = (
        None  # Allows rents to escalate during multi-year lease-up
    )
    # FIXME: review this for internal consistency


AnchorLogic = Any  # FIXME: address Any typing


@dataclass
class PaceContext:
    plan_name: str
    remaining_suites: List["VacantSuiteBase"]
    initial_start_date: date
    analysis_end_date: date
    market_lease_terms: Optional["RolloverLeaseTermsBase"]
    direct_terms: Optional[DirectLeaseTerms]
    global_settings: Optional[GlobalSettings]
    create_spec_fn: Callable[..., Optional["LeaseSpecBase"]]
    create_subdivided_spec_fn: Callable[..., Optional["LeaseSpecBase"]]
    total_target_area: float
    _suite_states: dict


class PaceStrategy(ABC):
    @abstractmethod
    def generate(
        self, pace_model: BasePace, context: PaceContext
    ) -> List["LeaseSpecBase"]:
        pass


class FixedQuantityPaceStrategy(PaceStrategy):
    def generate(
        self, pace_model: FixedQuantityPace, context: PaceContext
    ) -> List["LeaseSpecBase"]:
        # Logic from original FixedQuantityPaceStrategy.generate
        # This is extensive and will be simplified for the base class
        return []


class EqualSpreadPaceStrategy(PaceStrategy):
    def generate(
        self, pace_model: EqualSpreadPace, context: PaceContext
    ) -> List["LeaseSpecBase"]:
        # Logic from original EqualSpreadPaceStrategy.generate
        return []


class CustomSchedulePaceStrategy(PaceStrategy):
    def generate(
        self, pace_model: CustomSchedulePace, context: PaceContext
    ) -> List["LeaseSpecBase"]:
        # Logic from original CustomSchedulePaceStrategy.generate
        return []


class AbsorptionPlanBase(Model, Generic[ExpenseType, LossesType, MiscIncomeType]):
    """
    Generic base class for absorption plans with stabilized operating assumptions.

    Absorption plans define both the leasing strategy (pace, timing, tenant assumptions)
    and the stabilized operating characteristics of the resulting asset. This enables
    development analysis where assets are created via absorption plans to transition
    to deal analysis where stabilized assets are analyzed.

    Generic Type Parameters:
        ExpenseType: Asset-specific expense model (OfficeExpenses, ResidentialExpenses)
        LossesType: Asset-specific losses model (OfficeLosses, ResidentialLosses)
        MiscIncomeType: Asset-specific misc income model (OfficeMiscIncome, ResidentialMiscIncome)

    The generic constraints ensure office absorption plans accept only office expense types,
    residential plans accept only residential types, etc.

    Example:
        class OfficeAbsorptionPlan(AbsorptionPlanBase[OfficeExpenses, OfficeLosses, OfficeMiscIncome]):
            pass

    Required Fields:
        All stabilized operating assumption fields (stabilized_expenses, stabilized_losses,
        stabilized_misc_income) are required and have no default values.

    Usage:
        # With factory method for standard assumptions
        plan = OfficeAbsorptionPlan.with_typical_assumptions(...)

        # With custom assumptions
        plan = OfficeAbsorptionPlan(
            stabilized_expenses=custom_expenses,
            stabilized_losses=custom_losses,
            stabilized_misc_income=custom_income,
            ...
        )

        # Extract assumptions for asset creation
        expenses = plan.stabilized_expenses
        losses = plan.stabilized_losses
    """

    # Core absorption plan fields (unchanged)
    uid: UUID = Field(
        default_factory=uuid4, description="Unique identifier for the absorption plan"
    )
    name: str
    space_filter: SpaceFilter
    start_date_anchor: Union[date, StartDateAnchorEnum, AnchorLogic]
    pace: Annotated[
        Union[FixedQuantityPace, EqualSpreadPace, CustomSchedulePace],
        Field(discriminator="type"),
    ]
    leasing_assumptions: Union[RolloverProfileIdentifier, DirectLeaseTerms]

    # REQUIRED: Stabilized operating assumptions (type-safe with generics)
    # These define the operating characteristics of the stabilized asset
    stabilized_expenses: ExpenseType = Field(
        ...,
        description="REQUIRED: Operating expense assumptions for the stabilized asset. "
        "Use factory methods for realistic defaults if needed.",
    )
    stabilized_losses: LossesType = Field(
        ...,
        description="REQUIRED: Loss assumptions (vacancy, collection) for the stabilized asset. "
        "Use factory methods for realistic defaults if needed.",
    )
    stabilized_misc_income: List[MiscIncomeType] = Field(
        ...,
        description="REQUIRED: Miscellaneous income assumptions for the stabilized asset. "
        "Use empty list if no misc income. Use factory methods for typical income streams.",
    )

    def generate_lease_specs(
        self,
        available_vacant_suites: List["VacantSuiteBase"],
        analysis_start_date: date,
        analysis_end_date: date,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> List["LeaseSpecBase"]:
        # Simplified logic for base class - concrete implementations override this
        return []
