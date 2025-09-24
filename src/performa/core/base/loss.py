# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Loss models for real estate financial analysis.

This module contains both configuration classes (for property definition) and
execution classes (for runtime analysis). This separation is necessary because
losses need runtime information (timeline, property name) not available at
property creation time.

CLEAN ARCHITECTURE:
- Configuration classes: Store loss parameters on properties
- Execution classes: Runtime CashFlowModel instances for analysis
- Single file: All loss logic consolidated here
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import pandas as pd
from pydantic import Field, field_validator

from ..primitives import CashFlowCategoryEnum, CashFlowModel, Model
from ..primitives.enums import (
    RevenueSubcategoryEnum,
    UnleveredAggregateLineKey,
    VacancyLossMethodEnum,
)
from ..primitives.types import FloatBetween0And1

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext


# ============================================================================
# CONFIGURATION CLASSES (stored on properties)
# ============================================================================


class VacancyLossConfig(Model):
    """
    Configuration for vacancy loss allowance.

    Stored on property models to define vacancy assumptions.
    Converted to VacancyLossModel at analysis runtime.
    """

    rate: FloatBetween0And1 = Field(
        default=0.05, description="Vacancy rate as decimal (e.g., 0.05 for 5%)"
    )
    method: VacancyLossMethodEnum = Field(
        default=VacancyLossMethodEnum.POTENTIAL_GROSS_REVENUE,
        description="Which line item to apply vacancy rate to",
    )
    reduce_by_rollover_vacancy: bool = Field(
        default=True, description="Reduce by vacancy already accounted for in rollovers"
    )


class CreditLossConfig(Model):
    """
    Configuration for credit loss allowance.

    Stored on property models to define credit risk assumptions.
    Converted to CreditLossModel at analysis runtime.
    """

    rate: FloatBetween0And1 = Field(
        default=0.01, description="Credit loss rate as decimal (e.g., 0.01 for 1%)"
    )
    basis: UnleveredAggregateLineKey = Field(
        default=UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE,
        description="Revenue basis for credit loss calculation. PGR includes all revenue, GPR is rent only, TENANT_REVENUE is rent plus recoveries.",
    )

    @field_validator("basis")
    @classmethod
    def validate_basis(cls, v):
        """Validate that basis is one of the allowed revenue-based aggregate keys."""
        allowed_bases = {
            UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE,
            UnleveredAggregateLineKey.GROSS_POTENTIAL_RENT,
            UnleveredAggregateLineKey.TENANT_REVENUE,
        }
        if v not in allowed_bases:
            allowed_names = [basis.value for basis in allowed_bases]
            raise ValueError(
                f"Credit loss basis must be a revenue-based aggregate key. "
                f"Allowed: {allowed_names}. Got: {v.value if hasattr(v, 'value') else v}"
            )
        return v


class Losses(Model):
    """
    Container for property-level loss configurations.

    Used by property models to store loss assumptions.
    Analysis scenarios convert these to CashFlowModel instances.

    Example:
        losses = Losses(
            vacancy=VacancyLossConfig(rate=0.05),
            collection=CreditLossConfig(rate=0.01, basis="egi")
        )
    """

    vacancy: Optional[VacancyLossConfig] = Field(
        default_factory=VacancyLossConfig, description="Vacancy loss configuration"
    )
    collection: Optional[CreditLossConfig] = Field(
        default_factory=CreditLossConfig, description="Credit loss configuration"
    )


# ============================================================================
# EXECUTION CLASSES (runtime CashFlowModel instances)
# ============================================================================


class VacancyLossModel(CashFlowModel):
    """
    Runtime model for vacancy loss calculations.

    Created by analysis scenarios from VacancyLossConfig with runtime info.
    Calculates vacancy loss amounts based on PGR (returns positive values).
    """

    # All losses are negative revenue
    category: CashFlowCategoryEnum = CashFlowCategoryEnum.REVENUE
    subcategory: RevenueSubcategoryEnum = RevenueSubcategoryEnum.VACANCY_LOSS

    # Runtime configuration
    rate: float = Field(description="Vacancy rate as decimal")
    reference_line: str = Field(
        default="Potential Gross Revenue",
        description="Which aggregate line to reference",
    )
    value: float = Field(default=0.0, description="Will be calculated in compute_cf")

    # Set reference to trigger DEPENDENT_MODELS phase
    reference: UnleveredAggregateLineKey = (
        UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE
    )

    def compute_cf(self, context: "AnalysisContext") -> pd.Series:
        """
        Calculate vacancy loss as percentage of reference line.

        Args:
            context: Analysis context containing resolved aggregates

        Returns:
            Series with positive values representing vacancy loss amounts
        """
        # Get reference amount from context
        if not hasattr(context, "resolved_lookups"):
            return pd.Series(0.0, index=self.timeline.period_index)

        reference_series = context.resolved_lookups.get(self.reference)
        if reference_series is None or reference_series.empty:
            return pd.Series(0.0, index=self.timeline.period_index)

        # Calculate loss amount as positive value (orchestrator will handle sign)
        loss_amount = abs(reference_series * self.rate)

        # Ensure proper index alignment
        result = pd.Series(0.0, index=self.timeline.period_index)
        for period in result.index:
            if period in loss_amount.index:
                result[period] = loss_amount[period]

        return result


class CreditLossModel(CashFlowModel):
    """
    Runtime model for credit loss calculations.

    Created by analysis scenarios from CreditLossConfig with runtime info.
    Calculates credit loss amounts as a percentage of the specified revenue basis.
    Default basis is PGR (all potential revenue at 100% occupancy).
    """

    # All losses are negative revenue
    category: CashFlowCategoryEnum = CashFlowCategoryEnum.REVENUE
    subcategory: RevenueSubcategoryEnum = RevenueSubcategoryEnum.CREDIT_LOSS

    # Runtime configuration
    rate: float = Field(description="Credit loss rate as decimal")
    reference_line: str = Field(
        default="Potential Gross Revenue",
        description="Which aggregate line to reference",
    )
    value: float = Field(default=0.0, description="Will be calculated in compute_cf")

    # Set reference to trigger DEPENDENT_MODELS phase (configurable)
    reference: UnleveredAggregateLineKey = Field(
        default=UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE,
        description="Revenue aggregate line used as basis for credit loss calculation",
    )

    def compute_cf(self, context: "AnalysisContext") -> pd.Series:
        """
        Calculate credit loss as percentage of reference line.

        Args:
            context: Analysis context containing resolved aggregates

        Returns:
            Series with positive values representing credit loss amounts
        """
        # Get reference amount from context
        if not hasattr(context, "resolved_lookups"):
            return pd.Series(0.0, index=self.timeline.period_index)

        reference_series = context.resolved_lookups.get(self.reference)
        if reference_series is None or reference_series.empty:
            return pd.Series(0.0, index=self.timeline.period_index)

        # Calculate loss amount as positive value (orchestrator will handle sign)
        loss_amount = abs(reference_series * self.rate)

        # Ensure proper index alignment
        result = pd.Series(0.0, index=self.timeline.period_index)
        for period in result.index:
            if period in loss_amount.index:
                result[period] = loss_amount[period]

        return result
