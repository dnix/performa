# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Base Classes

Foundational base classes that enable all real estate modeling in Performa.
These abstract and concrete base classes define contracts and common behaviors.
"""

from .absorption import (
    AbsorptionPlanBase,
    BasePace,
    CustomSchedulePace,
    DirectLeaseTerms,
    EqualSpreadPace,
    FixedQuantityPace,
    PaceContext,
    PaceStrategy,
    SpaceFilter,
    SuiteAbsorptionState,
)
from .blueprint import DevelopmentBlueprintBase
from .cost import (
    CommissionTier,
    LeasingCommissionBase,
    TenantImprovementAllowanceBase,
)
from .expense import CapExItemBase, ExpenseItemBase, OpExItemBase
from .lease import LeaseBase, LeaseSpecBase
from .lease_components import RentAbatementBase, RentEscalationBase, TenantBase
from .loss import (
    CollectionLossConfigBase,
    GeneralVacancyLossConfigBase,
    LossesBase,
)
from .program import ProgramComponentSpec
from .property import Address, PropertyBaseModel
from .recovery import (
    ExpensePoolBase,
    RecoveryBase,
    RecoveryCalculationState,
    RecoveryMethodBase,
)
from .rent_roll import VacantSuiteBase
from .revenue import MiscIncomeBase
from .rollover import RolloverLeaseTermsBase, RolloverProfileBase

__all__ = [
    "AbsorptionPlanBase",
    "BasePace",
    "CustomSchedulePace",
    "DevelopmentBlueprintBase",
    "DirectLeaseTerms",
    "EqualSpreadPace",
    "FixedQuantityPace",
    "PaceContext",
    "PaceStrategy",
    "SpaceFilter",
    "SuiteAbsorptionState",
    "CommissionTier",
    "LeasingCommissionBase",
    "TenantImprovementAllowanceBase",
    "CapExItemBase",
    "ExpenseItemBase",
    "OpExItemBase",
    "LeaseBase",
    "LeaseSpecBase",
    "RentAbatementBase",
    "RentEscalationBase",
    "TenantBase",
    "CollectionLossConfigBase",
    "GeneralVacancyLossConfigBase",
    "LossesBase",
    "ProgramComponentSpec",
    "Address",
    "PropertyBaseModel",
    "ExpensePoolBase",
    "RecoveryBase",
    "RecoveryCalculationState",
    "RecoveryMethodBase",
    "VacantSuiteBase",
    "MiscIncomeBase",
    "RolloverLeaseTermsBase",
    "RolloverProfileBase",
] 