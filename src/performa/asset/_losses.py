from typing import Literal

from pydantic import Field

from ..core._enums import VacancyLossMethodEnum  # Import necessary enum
from ..core._model import Model
from ..core._types import FloatBetween0And1


class GeneralVacancyLossConfig(Model):
    """Configuration for General Vacancy Loss allowance."""
    rate: FloatBetween0And1 = Field(default=0.05, description="General vacancy rate applied across the property.") 
    method: VacancyLossMethodEnum = Field(default=VacancyLossMethodEnum.POTENTIAL_GROSS_REVENUE, description="Line item used as the basis for calculating General Vacancy loss amount.")
    reduce_by_rollover_vacancy: bool = Field(default=True, description="If True, reduce calculated general vacancy loss by any vacancy already accounted for during lease rollover periods.")

class CollectionLossConfig(Model):
    """Configuration for Collection Loss allowance."""
    rate: FloatBetween0And1 = Field(default=0.01, description="Percentage of income assumed uncollectible.") 
    # FIXME: should the default be PGR? check how industry does this...
    basis: Literal["pgr", "scheduled_income", "egi"] = Field(default="egi", description="Line item used as the basis for calculating Collection Loss.") # Changed default to egi

class Losses(Model):
    """
    Container for property-level loss configurations.
    """
    # Replace old placeholders with config models
    general_vacancy: GeneralVacancyLossConfig = Field(default_factory=GeneralVacancyLossConfig)
    collection_loss: CollectionLossConfig = Field(default_factory=CollectionLossConfig)
