# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Dict, Optional

import pandas as pd
from pydantic import computed_field, field_validator, model_validator

from ..primitives.cash_flow import CashFlowModel, ReferenceKey
from ..primitives.enums import (
    CalculationPass,
    FrequencyEnum,
    LeaseStatusEnum,
    UponExpirationEnum,
)
from ..primitives.model import Model
from ..primitives.settings import GlobalSettings
from ..primitives.validation import validate_term_specification
from .lease_components import RentAbatementBase

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext

# Now we can import these directly since there's no circular dependency
from .rollover import RolloverProfileBase

# --- Main Base Models ---


class LeaseSpecBase(Model, ABC):
    """
    Abstract base class for lease specifications - defining the terms
    and parameters of a lease before it becomes an active LeaseBase instance.
    """
    tenant_name: str
    start_date: date
    end_date: Optional[date] = None
    term_months: Optional[int] = None
    signing_date: Optional[date] = None
    suite: str
    floor: str
    area: float

    # Base rent terms
    base_rent_value: float
    base_rent_reference: Optional[ReferenceKey] = None
    base_rent_frequency: FrequencyEnum = FrequencyEnum.MONTHLY

    @field_validator("signing_date")
    @classmethod
    def validate_signing_date(cls, v, info):
        if v is not None:
            start_date = info.data.get("start_date")
            if start_date and v > start_date:
                raise ValueError("signing_date must be on or before start_date")
        return v

    @model_validator(mode="after")
    @classmethod
    def check_term(cls, data) -> "LeaseSpecBase":
        """Validate term specification using reusable validator."""
        return validate_term_specification(cls, data)

    @computed_field
    @property
    def computed_end_date(self) -> date:
        if self.end_date:
            return self.end_date
        if self.term_months:
            return (
                pd.Period(self.start_date, freq="M") + self.term_months - 1
            ).end_time.date()
        raise ValueError("Cannot compute end_date without end_date or term_months")


class LeaseBase(CashFlowModel, ABC):
    """
    Abstract base class for all lease types.
    
    Provides core lease functionality including:
    - Basic lease terms and timing
    - Timeline management
    - Abstract compute_cf method for cash flow calculations
    - Common properties for rent calculations
    """
    category: str = "Revenue"
    subcategory: str = "Lease"  # Simplified from enum for base class
    status: LeaseStatusEnum
    area: float
    suite: str
    floor: str
    upon_expiration: UponExpirationEnum
    signing_date: Optional[date] = None
    settings: GlobalSettings = GlobalSettings()
    
    # Rent-related fields
    rent_abatement: Optional[RentAbatementBase] = None
    
    @computed_field
    @property
    def calculation_pass(self) -> CalculationPass:
        """
        Determines the calculation phase for this lease based on its dependencies.
        
        FIXED: Previously all leases were hardcoded as DEPENDENT_VALUES, which caused
        a critical bug where basic leases were processed in Phase 2 instead of Phase 1.
        This prevented proper EGI calculation for dependent expenses like Property Management.
        
        Now uses smart dependency detection:
        - INDEPENDENT_VALUES: Basic leases with no dependencies (simple base rent)
        - DEPENDENT_VALUES: Complex leases with dependencies:
          * Leases with aggregate references (% rent, etc.)
          * Leases with recovery methods (need expense calculations first)
        
        This ensures proper sequencing:
        1. Phase 1: Basic leases + expenses generate base cash flows
        2. Intermediate: EGI calculated from Phase 1 revenue
        3. Phase 2: Complex leases (with recoveries) + dependent expenses (Property Management)
        """
        # Check for direct aggregate references (% rent, etc.)
        if self.reference is not None:
            return CalculationPass.DEPENDENT_VALUES
            
        # Check for recovery method dependencies (office leases)
        if hasattr(self, 'recovery_method') and self.recovery_method is not None:
            return CalculationPass.DEPENDENT_VALUES
            
        # Simple base rent leases can be calculated independently
        return CalculationPass.INDEPENDENT_VALUES

    @abstractmethod
    def compute_cf(self, context: "AnalysisContext") -> Dict[str, pd.Series]:
        """
        Compute cash flows for this lease.
        
        All concrete lease implementations must define how they calculate
        their cash flows given an analysis context.
        """
        raise NotImplementedError

    @abstractmethod
    def project_future_cash_flows(self, context: "AnalysisContext") -> pd.DataFrame:
        """
        Projects cash flows for this lease and all subsequent rollover events
        throughout the analysis period.

        This method must be implemented by subclasses to handle the logic of
        lease expiration and the creation of new speculative or renewal leases
        based on the `upon_expiration` setting and rollover profiles.
        """
        pass 


class RolloverLeaseTermsBase(Model, ABC):
    """
    Abstract base class for lease terms used in rollover scenarios.
    
    These define the parameters for speculative future leases when
    current leases expire and need to be renewed or replaced.
    """
    term_months: Optional[int] = None
    reference: Optional[ReferenceKey] = None
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY


class RolloverProfileBase(Model, ABC):
    """
    Abstract base class for rollover profiles that define how leases
    transition when they expire.
    
    Contains probability-based logic for renewals vs. new leases,
    downtime periods, and associated costs.
    """
    renewal_probability: float = 0.0
    downtime_months: int = 0
    term_months: int = 60
    upon_expiration: UponExpirationEnum = UponExpirationEnum.MARKET

    # Options for flexibility
    allow_renewals: bool = True
    allow_options: bool = False 