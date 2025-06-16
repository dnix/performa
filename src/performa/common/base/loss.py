from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..primitives._enums import VacancyLossMethodEnum
from ..primitives._model import Model
from ..primitives._types import FloatBetween0And1


class GeneralVacancyLossConfigBase(Model):
    """Base configuration for General Vacancy Loss allowance."""

    rate: FloatBetween0And1 = Field(
        default=0.05, description="General vacancy rate applied across the property."
    )
    method: VacancyLossMethodEnum = Field(
        default=VacancyLossMethodEnum.POTENTIAL_GROSS_REVENUE,
        description="Line item used as the basis for calculating General Vacancy loss amount.",
    )
    reduce_by_rollover_vacancy: bool = Field(
        default=True,
        description="If True, reduce calculated general vacancy loss by any vacancy already accounted for during lease rollover periods.",
    )


class CollectionLossConfigBase(Model):
    """Base configuration for Collection Loss allowance."""

    rate: FloatBetween0And1 = Field(
        default=0.01, description="Percentage of income assumed uncollectible."
    )
    basis: Literal["pgr", "scheduled_income", "egi"] = Field(
        default="egi",
        description="Line item used as the basis for calculating Collection Loss.",
    )


class LossesBase(Model):
    """
    Base container for property-level loss configurations.
    """

    general_vacancy: GeneralVacancyLossConfigBase = Field(
        default_factory=GeneralVacancyLossConfigBase
    )
    collection_loss: CollectionLossConfigBase = Field(
        default_factory=CollectionLossConfigBase
    ) 