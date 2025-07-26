# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import List

from pydantic import Field, computed_field, model_validator

from ...core.base import PropertyBaseModel
from ...core.capital import CapitalPlan
from ...core.primitives import AssetTypeEnum
from .expense import ResidentialExpenses
from .losses import ResidentialLosses
from .misc_income import ResidentialMiscIncome

# Now we can import ResidentialRentRoll directly
from .rent_roll import ResidentialRentRoll


class ResidentialProperty(PropertyBaseModel):
    """
    Represents a multifamily residential property for analysis.
    
    This model embodies the "unit-centric" paradigm of residential
    real estate analysis, where the central concept is the "unit mix"
    rather than individual lease specifications.
    
    Key Architectural Differences from Commercial/Office:
    - unit_mix: Container for unit specifications and vacant units
    - capital_plans: Renovation projects that can be triggered during analysis
    - No TI/LC structures (simpler residential lease costs)
    - No complex recovery methods (residents don't pay building expenses)
    """
    
    # === CORE FIELDS ===
    # Real estate classification - this IS a property type (unlike DevelopmentProject)
    property_type: AssetTypeEnum = AssetTypeEnum.MULTIFAMILY
    unit_mix: ResidentialRentRoll
    
    # === FINANCIAL MODELS ===
    expenses: ResidentialExpenses = Field(default_factory=ResidentialExpenses)
    losses: ResidentialLosses = Field(default_factory=ResidentialLosses)
    miscellaneous_income: List[ResidentialMiscIncome] = Field(default_factory=list)
    
    # === VALUE-ADD CAPABILITIES ===
    capital_plans: List[CapitalPlan] = Field(
        default_factory=list,
        description="Renovation projects that can be triggered during lease turnover or other events"
    )
    
    # === REQUIRED BASE FIELDS ===
    # These are required by PropertyBaseModel - must be provided explicitly
    # gross_area and net_rentable_area are inherited from PropertyBaseModel

    @computed_field
    @property
    def unit_count(self) -> int:
        """Total number of units (occupied + vacant)."""
        return self.unit_mix.total_unit_count

    @computed_field
    @property
    def weighted_avg_rent(self) -> float:
        """Weighted average rent across all unit types (including vacant units)."""
        return self.unit_mix.average_rent_per_unit

    @computed_field
    @property
    def occupancy_rate(self) -> float:
        """Current occupancy rate as decimal (0.0 to 1.0)."""
        return self.unit_mix.occupancy_rate

    @computed_field
    @property
    def monthly_income_potential(self) -> float:
        """Total monthly income if 100% occupied."""
        return self.unit_mix.total_monthly_income_potential

    @computed_field
    @property
    def current_monthly_income(self) -> float:
        """Current monthly income based on occupancy."""
        return self.unit_mix.current_monthly_income

    @model_validator(mode='after')
    def _validate_area_consistency(self) -> "ResidentialProperty":
        """Validate that provided areas are consistent with unit mix."""
        if self.unit_mix and self.net_rentable_area > 0:
            unit_mix_area = self.unit_mix.total_rentable_area
            nra = self.net_rentable_area
            
            # Allow reasonable tolerance (5% for residential properties)
            tolerance = 0.05
            if abs(unit_mix_area - nra) / nra > tolerance:
                percentage_diff = abs(unit_mix_area - nra) / nra * 100
                raise ValueError(
                    f"Area inconsistency in property '{self.name}': "
                    f"Unit mix total area ({unit_mix_area:,.0f} SF) differs from "
                    f"Net Rentable Area ({nra:,.0f} SF) by {percentage_diff:.1f}%. "
                    f"Please ensure consistency between unit specifications and property areas."
                )
        return self 