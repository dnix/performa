# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Core Primitives

Essential building blocks for all real estate financial modeling in Performa.
Handles timeline management, cash flow calculations, settings, and validation.
"""

# Export key primitives for convenient access
from .cash_flow import CashFlowModel
from .draw_schedule import (
    AnyDrawSchedule,
    DrawSchedule,
    FirstLastDrawSchedule,
    FirstOnlyDrawSchedule,
    LastOnlyDrawSchedule,
    ManualDrawSchedule,
    SCurveDrawSchedule,
    UniformDrawSchedule,
)
from .enums import (
    AssetTypeEnum,
    CalculationPhase,
    CapExCategoryEnum,
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    DrawScheduleKindEnum,
    ExpenseCategoryEnum,
    ExpenseSubcategoryEnum,
    FinancingSubcategoryEnum,
    FrequencyEnum,
    InterestCalculationMethod,
    LeaseStatusEnum,
    LeaseTypeEnum,
    LeveredAggregateLineKey,
    OrchestrationPass,
    ProgramUseEnum,
    PropertyAttributeKey,
    RevenueSubcategoryEnum,
    StartDateAnchorEnum,
    TransactionPurpose,
    UnleveredAggregateLineKey,
    UponExpirationEnum,
    VacancyLossMethodEnum,
    ValuationSubcategoryEnum,
)
from .growth_rates import FixedGrowthRate, GrowthRates, PercentageGrowthRate
from .model import Model
from .settings import (
    CalculationSettings,
    GlobalSettings,
    InflationSettings,
    InflationTimingEnum,
    ReportingSettings,
)
from .timeline import Timeline
from .types import FloatBetween0And1, PositiveFloat, PositiveInt
from .validation import (
    ValidationMixin,
    validate_conditional_requirement_decorator,
    validate_mutual_exclusivity,
    validate_term_specification,
)

__all__ = [
    # Core models
    "CashFlowModel",
    "Model",
    "Timeline",
    # Settings
    "GlobalSettings",
    "CalculationSettings",
    "ReportingSettings",
    "InflationSettings",
    "InflationTimingEnum",
    # Enums
    "AssetTypeEnum",
    "CalculationPhase",
    "OrchestrationPass",
    "CashFlowCategoryEnum",
    "DrawScheduleKindEnum",
    "ExpenseSubcategoryEnum",
    "FinancingSubcategoryEnum",
    "FrequencyEnum",
    "InterestCalculationMethod",
    "LeaseStatusEnum",
    "LeaseTypeEnum",
    "ProgramUseEnum",
    "PropertyAttributeKey",
    "RevenueSubcategoryEnum",
    "StartDateAnchorEnum",
    "TransactionPurpose",
    "UponExpirationEnum",
    "VacancyLossMethodEnum",
    "UnleveredAggregateLineKey",
    "LeveredAggregateLineKey",
    "CapExCategoryEnum",
    "CapitalSubcategoryEnum",
    "ExpenseCategoryEnum",
    "ValuationSubcategoryEnum",
    # Growth rates
    "GrowthRates",
    "PercentageGrowthRate",
    "FixedGrowthRate",
    # Draw schedules
    "AnyDrawSchedule",
    "DrawSchedule",
    "UniformDrawSchedule",
    "SCurveDrawSchedule",
    "ManualDrawSchedule",
    "FirstLastDrawSchedule",
    "FirstOnlyDrawSchedule",
    "LastOnlyDrawSchedule",
    # Types
    "PositiveFloat",
    "PositiveInt",
    "FloatBetween0And1",
    # Validation
    "ValidationMixin",
    "validate_conditional_requirement_decorator",
    "validate_mutual_exclusivity",
    "validate_term_specification",
]
