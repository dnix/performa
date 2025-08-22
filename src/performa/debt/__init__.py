# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

# Import all debt classes
from .amortization import LoanAmortization
from .construction import ConstructionFacility
from .constructs import create_construction_to_permanent_plan
from .debt_facility import DebtFacility
from .permanent import PermanentFacility
from .plan import FinancingPlan
from .rates import (
    FixedRate,
    FloatingRate,
    InterestRate,
    InterestRateType,
    RateIndexEnum,
)
from .tranche import DebtTranche
from .types import AnyDebtFacility

# Rebuild models that have forward references to DebtTranche
FinancingPlan.model_rebuild()
ConstructionFacility.model_rebuild()

# Define __all__ to specify what gets imported with "from performa.debt import *"
__all__ = [
    # Core facility types
    "DebtFacility",
    "ConstructionFacility",
    "PermanentFacility",
    "DebtTranche",
    # Financial planning
    "FinancingPlan",
    # Rate mechanics
    "InterestRate",
    "InterestRateType",  # Backward compatibility
    "RateIndexEnum",
    "FixedRate",
    "FloatingRate",
    # Payment calculations
    "LoanAmortization",
    # Type unions
    "AnyDebtFacility",
    # Construct constructs
    "create_construction_to_permanent_plan",
]
