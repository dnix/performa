"""Base classes and interfaces for debt modeling"""

from abc import ABC, abstractmethod
from typing import Optional

from ..core._model import Model
from ..core._types import FloatBetween0And1
from ._rates import InterestRate


class DebtFacility(Model, ABC):
    """Abstract base class for all debt facilities"""

    interest_rate: Optional[InterestRate] = None
    fee_rate: Optional[FloatBetween0And1] = None

    @abstractmethod
    def calculate_interest(self) -> float:
        """Calculate interest for a period"""
        ...
