# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Core Framework

Foundational building blocks for all real estate financial modeling in Performa.
Contains essential primitives, base classes, and capital planning tools.
"""

from . import base, capital, primitives

# Explicit imports from base module
from .base import (
    # Absorption
    AbsorptionPlanBase,
    # Property
    Address,
    BasePace,
    # Expenses
    CapExItemBase,
    # Losses
    CollectionLossConfigBase,
    # Cost components
    CommissionTier,
    CustomSchedulePace,
    DirectLeaseTerms,
    EqualSpreadPace,
    ExpenseItemBase,
    # Recovery
    ExpensePoolBase,
    FixedQuantityPace,
    GeneralVacancyLossConfigBase,
    # Leases
    LeaseBase,
    LeaseSpecBase,
    LeasingCommissionBase,
    LossesBase,
    # Revenue
    MiscIncomeBase,
    OpExItemBase,
    PaceContext,
    PaceStrategy,
    ProgramComponentSpec,
    PropertyBaseModel,
    RecoveryBase,
    RecoveryCalculationState,
    RecoveryMethodBase,
    # Lease components
    RentAbatementBase,
    RentEscalationBase,
    # Rollover
    RolloverLeaseTermsBase,
    RolloverProfileBase,
    SpaceFilter,
    SuiteAbsorptionState,
    TenantBase,
    TenantImprovementAllowanceBase,
    # Rent roll
    VacantSuiteBase,
)

# Explicit imports from capital module
from .capital import (
    CapitalItem,
    CapitalPlan,
)

# Explicit imports from primitives module  
from .primitives import (
    # Enums
    AssetTypeEnum,
    CalculationPass,
    CashFlowCategoryEnum,
    # Core models
    CashFlowModel,
    ExpenseSubcategoryEnum,
    # Types
    FloatBetween0And1,
    FrequencyEnum,
    # Settings
    GlobalSettings,
    # Growth rates
    GrowthRate,
    GrowthRates,
    InflationSettings,
    InflationTimingEnum,
    LeaseStatusEnum,
    LeaseTypeEnum,
    Model,
    PositiveFloat,
    PositiveInt,
    ProgramUseEnum,
    ReportingSettings,
    RevenueSubcategoryEnum,
    StartDateAnchorEnum,
    Timeline,

    UponExpirationEnum,
    VacancyLossMethodEnum,
    # Validation
    ValidationMixin,
    validate_conditional_requirement_decorator,
    validate_mutual_exclusivity,
    validate_term_specification,
)

__all__ = [
    # Absorption
    "AbsorptionPlanBase",
    "BasePace",
    "CustomSchedulePace",
    "DirectLeaseTerms",
    "EqualSpreadPace",
    "FixedQuantityPace",
    "PaceContext",
    "PaceStrategy",
    "SpaceFilter",
    "SuiteAbsorptionState",
    
    # Cost components
    "CommissionTier",
    "LeasingCommissionBase",
    "TenantImprovementAllowanceBase",
    
    # Expenses
    "CapExItemBase",
    "ExpenseItemBase",
    "OpExItemBase",
    
    # Leases
    "LeaseBase",
    "LeaseSpecBase",
    
    # Lease components
    "RentAbatementBase",
    "RentEscalationBase",
    "TenantBase",
    
    # Losses
    "CollectionLossConfigBase",
    "GeneralVacancyLossConfigBase",
    "LossesBase",
    
    # Property
    "Address",
    "PropertyBaseModel",
    "ProgramComponentSpec",
    
    # Recovery
    "ExpensePoolBase",
    "RecoveryBase",
    "RecoveryCalculationState",
    "RecoveryMethodBase",
    
    # Rent roll
    "VacantSuiteBase",
    
    # Revenue
    "MiscIncomeBase",
    
    # Rollover
    "RolloverLeaseTermsBase",
    "RolloverProfileBase",
    
    # Core models
    "CashFlowModel",
    "Model",
    "Timeline",
    
    # Settings
    "GlobalSettings",
    "InflationSettings",
    "InflationTimingEnum", 
    "ReportingSettings",
    
    # Enums

    "AssetTypeEnum",
    "CalculationPass",
    "CashFlowCategoryEnum",
    "ExpenseSubcategoryEnum",
    "FrequencyEnum",
    "LeaseStatusEnum",
    "LeaseTypeEnum",
    "ProgramUseEnum",
    "RevenueSubcategoryEnum",
    "StartDateAnchorEnum",

    "UponExpirationEnum",
    "VacancyLossMethodEnum",
    
    # Growth rates
    "GrowthRate",
    "GrowthRates",
    
    # Types
    "FloatBetween0And1",
    "PositiveFloat",
    "PositiveInt",
    
    # Validation
    "ValidationMixin",
    "validate_conditional_requirement_decorator",
    "validate_mutual_exclusivity",
    "validate_term_specification",
    
    # Capital planning
    "CapitalItem",
    "CapitalPlan",
] 
