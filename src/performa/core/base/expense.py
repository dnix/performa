# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import pandas as pd
from pydantic import computed_field

from ..primitives.cash_flow import CashFlowModel
from ..primitives.enums import ExpenseSubcategoryEnum, UnitOfMeasureEnum
from ..primitives.model import Model
from ..primitives.types import FloatBetween0And1

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext


logger = logging.getLogger(__name__)


class ExpenseItemBase(CashFlowModel):
    """
    Base abstract class for all expense items.
    """

    category: str = "Expense"
    subcategory: ExpenseSubcategoryEnum
    group: Optional[str] = None


class OpExItemBase(ExpenseItemBase):
    """
    Base class for operating expenses.

    This class inherits the powerful `compute_cf` method from `CashFlowModel`,
    which automatically handles value calculation based on `unit_of_measure`,
    dependency resolution via `reference`, and growth rate application.
    Subclasses like `OfficeOpExItem` can then call `super().compute_cf()` and
    apply their own specific adjustments (e.g., for occupancy).
    
    Recovery Design Pattern:
    ========================
    The recoverability of expenses follows a clear computed property pattern:
    
    - Set `recoverable_ratio` field (0.0 to 1.0) to control what percentage is recoverable
    - Use `is_recoverable` property (computed from recoverable_ratio > 0) for boolean checks
    - DO NOT set `is_recoverable` directly - it's computed automatically
    
    Examples:
        # Fully recoverable expense
        expense = OfficeOpExItem(name="CAM", value=5.0, recoverable_ratio=1.0)
        assert expense.is_recoverable == True
        
        # Partially recoverable expense  
        expense = OfficeOpExItem(name="Utilities", value=3.0, recoverable_ratio=0.8)
        assert expense.is_recoverable == True
        
        # Non-recoverable expense
        expense = OfficeOpExItem(name="Management", value=2.0, recoverable_ratio=0.0)
        assert expense.is_recoverable == False
    """

    subcategory: ExpenseSubcategoryEnum = ExpenseSubcategoryEnum.OPEX
    variable_ratio: Optional[FloatBetween0And1] = None
    recoverable_ratio: Optional[FloatBetween0And1] = 0.0  # Default: not recoverable

    @computed_field
    @property
    def is_variable(self) -> bool:
        """True if this expense varies with occupancy (has variable_ratio)."""
        return self.variable_ratio is not None

    @computed_field
    @property
    def is_recoverable(self) -> bool:
        """
        True if any portion of this expense is recoverable from tenants.
        
        This is a computed property based on recoverable_ratio.
        DO NOT set this directly - set recoverable_ratio instead.
        
        Returns:
            True if recoverable_ratio is set and > 0, False otherwise
        """
        return self.recoverable_ratio is not None and self.recoverable_ratio > 0


class CapExItemBase(ExpenseItemBase):
    """Base class for capital expenditures."""

    subcategory: ExpenseSubcategoryEnum = ExpenseSubcategoryEnum.CAPEX

    def compute_cf(self, context: AnalysisContext) -> pd.Series:
        """
        Computes the cash flow for a capital expenditure item.

        This method overrides the base `CashFlowModel.compute_cf` to explicitly
        **exclude** the application of growth rates. Capital expenditures are
        typically budgeted as discrete amounts and are not expected to grow
        in the same compounding manner as operational expenses.
        """
        base_value = self.value
        if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
            nra = context.property_data.net_rentable_area
            if nra > 0:
                base_value = self.value * nra
            else:
                base_value = 0.0
        elif self.unit_of_measure == UnitOfMeasureEnum.BY_PERCENT and self.reference:
            dependency_cf = context.resolved_lookups.get(self.reference)
            if dependency_cf is None:
                raise ValueError(f"Unresolved dependency for '{self.name}': {self.reference}")
            base_value = dependency_cf * self.value
        
        monthly_value = self._convert_frequency(base_value)
        base_series = self._cast_to_flow(monthly_value)
        return base_series 