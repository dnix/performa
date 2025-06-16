from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, model_validator

from ..primitives.growth_rates import GrowthRate
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1, PositiveFloat
from .expense import ExpenseItemBase

logger = logging.getLogger(__name__)


@dataclass
class RecoveryCalculationState:
    """
    Holds pre-calculated, mutable state for a Recovery object during analysis.
    """
    recovery_uid: UUID
    calculated_annual_base_year_stop: Optional[float] = None
    frozen_base_year_pro_rata: Optional[float] = None


class ExpensePoolBase(Model):
    """
    Base class for a group of related expenses for recovery.
    """

    name: str
    expenses: Union[ExpenseItemBase, List[ExpenseItemBase]]
    pool_size_override: Optional[PositiveFloat] = None


class RecoveryBase(Model):
    """
    Base model for cost recovery rules.
    """

    uid: UUID = Field(default_factory=uuid4)
    expenses: Union[ExpensePoolBase, ExpenseItemBase]
    structure: Literal[
        "net",
        "base_stop",
        "fixed",
        "base_year",
        "base_year_plus1",
        "base_year_minus1",
    ]
    base_amount: Optional[PositiveFloat] = None
    base_amount_unit: Optional[Literal["total", "psf"]] = "psf"
    base_year: Optional[int] = None
    growth_rate: Optional[GrowthRate] = None
    contribution_deduction: Optional[PositiveFloat] = None
    admin_fee_percent: Optional[FloatBetween0And1] = None
    prorata_share: Optional[PositiveFloat] = None
    denominator: Optional[PositiveFloat] = None
    yoy_min_growth: Optional[FloatBetween0And1] = None
    yoy_max_growth: Optional[FloatBetween0And1] = None
    recovery_floor: Optional[PositiveFloat] = None
    recovery_ceiling: Optional[PositiveFloat] = None

    @property
    def expense_pool(self) -> ExpensePoolBase:
        if isinstance(self.expenses, ExpenseItemBase):
            pool_name = self.expenses.name
            return ExpensePoolBase(name=f"{pool_name} Pool", expenses=self.expenses)
        return self.expenses

    @model_validator(mode="after")
    def validate_structure_requirements(self) -> "RecoveryBase":
        if self.structure == "base_stop" and self.base_amount is None:
            raise ValueError("base_amount is required for base_stop recovery structure")
        if self.structure == "fixed" and self.base_amount is None:
            raise ValueError("base_amount is required for fixed recovery structure")
        if self.structure in ["base_year", "base_year_plus1", "base_year_minus1"] and self.base_year is None:
            raise ValueError(f"base_year is required for {self.structure} recovery structure")
        return self


class RecoveryMethodBase(Model):
    """
    Base class for how expenses are recovered from tenants.
    """

    name: str
    gross_up: bool = True
    gross_up_percent: Optional[FloatBetween0And1] = None
    recoveries: List[RecoveryBase]
