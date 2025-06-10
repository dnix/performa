from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field

# Updated imports for common.primitives
from ._enums import FrequencyEnum, UnitOfMeasureEnum
from ._model import Model
from ._settings import GlobalSettings
from ._timeline import Timeline
from ._types import PositiveFloat


class CashFlowModel(Model, ABC):
    """
    Base Abstract class for any cash flow description.
    Subclasses must implement the compute_cf method.
    """

    model_id: UUID = Field(
        default_factory=uuid4,
        description="Stable unique identifier for this model instance",
    )
    name: str
    category: str
    subcategory: str
    description: Optional[str] = None
    account: Optional[str] = None
    timeline: Timeline
    value: Union[PositiveFloat, pd.Series, Dict, List]
    unit_of_measure: UnitOfMeasureEnum
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    reference: Optional[Union[float, pd.Series, str, UUID]] = None
    settings: GlobalSettings = Field(default_factory=GlobalSettings)

    @abstractmethod
    def compute_cf(
        self,
        # The orchestrator will likely pass lookup_fn and possibly other context.
        # Subclasses will define the specific arguments they need.
        **kwargs: Any,
    ) -> Union[pd.Series, Dict[str, pd.Series]]:
        """
        Compute the cash flow for this model instance.
        The result should be a pandas Series or a dictionary of pandas Series,
        with a monthly PeriodIndex.
        """
        pass 