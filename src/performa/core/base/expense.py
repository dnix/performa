# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from pydantic import computed_field

from ..primitives.cash_flow import CashFlowModel
from ..primitives.enums import ExpenseSubcategoryEnum
from ..primitives.types import FloatBetween0And1


logger = logging.getLogger(__name__)


class ExpenseItemBase(CashFlowModel):
    """
    Base abstract class for all expense items (both OpEx and CapEx).
    
    Recovery Design Pattern:
    ========================
    Both operating and capital expenses can be recoverable from tenants:
    
    - Set `recoverable_ratio` field (0.0 to 1.0) to control what percentage is recoverable
    - Use `is_recoverable` property (computed from recoverable_ratio > 0) for boolean checks
    - DO NOT set `is_recoverable` directly - it's computed automatically
    
    Examples:
        # Fully recoverable OpEx
        opex = OfficeOpExItem(name="CAM", value=5.0, recoverable_ratio=1.0)
        assert opex.is_recoverable == True
        
        # Partially recoverable CapEx (tenant improvement pass-through)
        capex = ResidentialCapExItem(name="Roof Replacement", value=50000, recoverable_ratio=0.3)
        assert capex.is_recoverable == True
        
        # Non-recoverable expense
        expense = OfficeOpExItem(name="Management", value=2.0, recoverable_ratio=0.0)
        assert expense.is_recoverable == False
    """

    category: str = "Expense"
    subcategory: ExpenseSubcategoryEnum
    group: Optional[str] = None
    recoverable_ratio: Optional[FloatBetween0And1] = 0.0  # Default: not recoverable

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


class OpExItemBase(ExpenseItemBase):
    """
    Base class for operating expenses.

    This class inherits the powerful `compute_cf` method from `CashFlowModel`,
    which automatically handles value calculation based on `unit_of_measure`,
    dependency resolution via `reference`, and growth rate application.
    Subclasses like `OfficeOpExItem` can then call `super().compute_cf()` and
    apply their own specific adjustments (e.g., for occupancy).
    
    Inherits recovery logic from `ExpenseItemBase` for tenant cost recovery.
    
    Variable Expense Pattern (OpEx-specific):
    ========================================
    Operating expenses can vary with building occupancy:
    
    - Set `variable_ratio` field (0.0 to 1.0) for expenses that scale with occupancy
    - Use `is_variable` property (computed from variable_ratio existence) for boolean checks
    
    Examples:
        # Fixed expense (doesn't vary with occupancy)
        expense = OfficeOpExItem(name="Property Tax", value=10000)
        assert expense.is_variable == False
        
        # Variable expense (scales with occupancy)  
        expense = OfficeOpExItem(name="Utilities", value=5000, variable_ratio=0.8)
        assert expense.is_variable == True
    """

    subcategory: ExpenseSubcategoryEnum = ExpenseSubcategoryEnum.OPEX
    variable_ratio: Optional[FloatBetween0And1] = None

    @computed_field
    @property
    def is_variable(self) -> bool:
        """True if this expense varies with occupancy (has variable_ratio)."""
        return self.variable_ratio is not None


class CapExItemBase(ExpenseItemBase):
    """
    Base class for capital expenditures.
    
    Inherits the standard `compute_cf` method from `CashFlowModel` via `ExpenseItemBase`,
    which automatically handles:
    - PER_UNIT calculations with smart property type detection
    - BY_PERCENT calculations with dependency resolution  
    - Growth rate application (industry standard for CapEx like capital reserves)
    
    Inherits recovery logic from `ExpenseItemBase` for tenant cost recovery.
    Capital expenses can be recoverable through various mechanisms:
    - Tenant improvements passed through to tenants
    - Major building upgrades recovered via CAM charges
    - Infrastructure improvements with tenant cost allocation
    
    This follows the same inheritance pattern as `OpExItemBase`.

    NOTE: CapEx are assumed to NOT be variable with occupancy.
    
    Examples:
        # Non-recoverable capital reserve
        capex = ResidentialCapExItem(name="Capital Reserves", value=450, recoverable_ratio=0.0)
        assert capex.is_recoverable == False
        
        # Partially recoverable tenant improvement
        capex = OfficeCapExItem(name="HVAC Upgrade", value=100000, recoverable_ratio=0.6)
        assert capex.is_recoverable == True
    """

    subcategory: ExpenseSubcategoryEnum = ExpenseSubcategoryEnum.CAPEX 
