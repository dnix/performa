# src/performa/asset/residential/__init__.py

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

The architecture mirrors the office module's explicit vacancy pattern,
where occupancy emerges from the composition of occupied vs vacant units.
"""

# Import order matters for forward references
# Import CapitalPlan to resolve forward references
from ...common.capital import CapitalPlan
from .analysis import ResidentialAnalysisScenario
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
    # Core property model
    "ResidentialProperty",
    
    # Expenses
    "ResidentialExpenses",
    "ResidentialOpExItem", 
    "ResidentialCapExItem",
    
    # Losses
    "ResidentialLosses",
    "ResidentialGeneralVacancyLoss",
    "ResidentialCollectionLoss",
    
    # Miscellaneous Income
    "ResidentialMiscIncome",
    
    # Unit Mix & Rent Roll (Step 1.2)
    "ResidentialRentRoll",
    "ResidentialUnitSpec", 
    "ResidentialVacantUnit",  # New vacant unit model
    
    # Rollover Logic (Step 1.3)
    "ResidentialRolloverProfile",
    "ResidentialRolloverLeaseTerms",
    
    # Runtime Lease Model (Step 1.4)
    "ResidentialLease",
    
    # Analysis Scenario Plugin (Step 1.5)
    "ResidentialAnalysisScenario",
] 