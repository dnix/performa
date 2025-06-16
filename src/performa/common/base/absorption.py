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

from ..primitives.enums import (
    ProgramUseEnum,
    StartDateAnchorEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from ..primitives.model import Model
from ..primitives.settings import GlobalSettings
from ..primitives.timeline import Timeline
from ..primitives.types import PositiveFloat, PositiveInt
from .cost import LeasingCommissionBase, TenantImprovementAllowanceBase
from .lease import LeaseSpecBase, RentAbatementBase, RentEscalationBase
from .recovery import RecoveryMethodBase
from .rent_roll import VacantSuiteBase
from .rollover import RolloverLeaseTermsBase

logger = logging.getLogger(__name__)


@dataclass
class SuiteAbsorptionState:
    remaining_area: float
    units_created: int = 0


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
    base_rent_unit_of_measure: Optional[UnitOfMeasureEnum] = None
    term_months: Optional[PositiveInt] = None
    upon_expiration: Optional[UponExpirationEnum] = None
    rent_escalation: Optional["RentEscalationBase"] = None
    rent_abatement: Optional["RentAbatementBase"] = None
    recovery_method: Optional["RecoveryMethodBase"] = None
    ti_allowance: Optional["TenantImprovementAllowanceBase"] = None
    leasing_commission: Optional["LeasingCommissionBase"] = None


AnchorLogic = Any


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


class AbsorptionPlanBase(Model):
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
        available_vacant_suites: List["VacantSuiteBase"],
        analysis_start_date: date,
        analysis_end_date: date,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> List["LeaseSpecBase"]:
        # Simplified logic for base class
        return [] 