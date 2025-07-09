"""
Office Asset Modeling

Comprehensive modeling capabilities for commercial office properties,
from single-tenant buildings to complex multi-tenant office towers.
"""

from . import (
    analysis,
)
from .absorption import (
    DirectLeaseTerms,
    EqualSpreadPace,
    FixedQuantityPace,
    OfficeAbsorptionPlan,
    SpaceFilter,
)
from .analysis import OfficeAnalysisScenario
from .blueprint import OfficeDevelopmentBlueprint
from .expense import OfficeCapExItem, OfficeExpenses, OfficeOpExItem
from .lc import OfficeLeasingCommission
from .lease import OfficeLease
from .lease_spec import OfficeLeaseSpec
from .losses import OfficeCollectionLoss, OfficeGeneralVacancyLoss, OfficeLosses
from .misc_income import OfficeMiscIncome
from .property import OfficeProperty
from .recovery import ExpensePool, OfficeRecoveryMethod, Recovery
from .rent_abatement import OfficeRentAbatement
from .rent_escalation import OfficeRentEscalation
from .rent_roll import OfficeRentRoll, OfficeVacantSuite
from .rollover import (
    OfficeRolloverLeaseTerms,
    OfficeRolloverLeasingCommission,
    OfficeRolloverProfile,
    OfficeRolloverTenantImprovement,
)
from .tenant import OfficeTenant
from .ti import OfficeTenantImprovement

# Resolve forward references
OfficeLease.model_rebuild()
OfficeRolloverProfile.model_rebuild()
OfficeLeaseSpec.model_rebuild()
DirectLeaseTerms.model_rebuild()


__all__ = [
    "OfficeDevelopmentBlueprint",
    "OfficeLease",
    "OfficeLeaseSpec",
    "OfficeProperty",
    "OfficeAnalysisScenario",
    "OfficeRecoveryMethod",
    "Recovery",
    "ExpensePool",
    "OfficeRolloverProfile",
    "OfficeRolloverLeaseTerms",
    "OfficeRolloverLeasingCommission",
    "OfficeRolloverTenantImprovement",
    "OfficeTenantImprovement",
    "OfficeLeasingCommission",
    "OfficeTenant",
    "OfficeRentEscalation",
    "OfficeRentAbatement",
    "OfficeRentRoll",
    "OfficeLosses",
    "OfficeGeneralVacancyLoss",
    "OfficeCollectionLoss",
    "OfficeMiscIncome",
    "OfficeExpenses",
    "OfficeOpExItem",
    "OfficeCapExItem",
    "OfficeAbsorptionPlan",
    "DirectLeaseTerms",
    "EqualSpreadPace",
    "FixedQuantityPace",
    "SpaceFilter",
    "OfficeVacantSuite",
]
