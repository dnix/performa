"""
Residential asset analysis module for multifamily properties.

This module implements the "unit-centric" paradigm of residential real estate
analysis, where properties are modeled by unit mix rather than individual leases.

Key Components:
- ResidentialProperty: Main property container 
- ResidentialRentRoll: Unit mix container (occupied + vacant units)
- ResidentialUnitSpec: Specification for groups of identical units
- ResidentialVacantUnit: Specification for groups of vacant units
- ResidentialLease: Runtime lease model for individual units
- ResidentialAnalysisScenario: Analysis orchestration
- ResidentialAbsorptionPlan: Unit-based absorption modeling for developments

The architecture mirrors the office module's explicit vacancy pattern,
where occupancy emerges from the composition of occupied vs vacant units.
"""

# Import order matters for forward references
# Import CapitalPlan to resolve forward references
from ...common.capital import CapitalPlan
from .absorption import ResidentialAbsorptionPlan
from .analysis import ResidentialAnalysisScenario
from .blueprint import ResidentialDevelopmentBlueprint
from .expense import ResidentialCapExItem, ResidentialExpenses, ResidentialOpExItem
from .lease import ResidentialLease
from .losses import (
    ResidentialCollectionLoss,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
)
from .misc_income import ResidentialMiscIncome
from .property import ResidentialProperty
from .rent_roll import ResidentialRentRoll, ResidentialUnitSpec, ResidentialVacantUnit
from .rollover import ResidentialRolloverLeaseTerms, ResidentialRolloverProfile

# Resolve forward references for CapitalPlan
# This ensures CapitalPlan is properly recognized in ResidentialLease
ResidentialLease.model_rebuild()

__all__ = [
    # Property and container models
    "ResidentialProperty",
    "ResidentialRentRoll",
    "ResidentialUnitSpec", 
    "ResidentialVacantUnit",
    
    # Analysis and cash flow models
    "ResidentialAnalysisScenario",
    "ResidentialLease",
    "ResidentialExpenses",
    "ResidentialOpExItem",
    "ResidentialCapExItem",
    "ResidentialLosses",
    "ResidentialGeneralVacancyLoss",
    "ResidentialCollectionLoss",
    "ResidentialMiscIncome",
    
    # Rollover and absorption models
    "ResidentialRolloverProfile",
    "ResidentialRolloverLeaseTerms",
    "ResidentialAbsorptionPlan",
    
    # Development models
    "ResidentialDevelopmentBlueprint",
] 