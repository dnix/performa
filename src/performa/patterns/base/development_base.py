# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Base class for development deal patterns.

This module provides the abstract base class for asset-specific development patterns,
containing common parameters that apply to all development deals regardless of asset type.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import date
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from ...core.primitives import (
    FloatBetween0And1,
    PositiveFloat,
    PositiveInt,
    Timeline,
)
from ...deal import Deal
from .pattern_base import PatternBase


class DevelopmentPatternBase(PatternBase):
    """
    Abstract base class for development deal patterns.

    This class contains all common parameters for development deals regardless
    of asset type (office, residential, industrial, etc.). Asset-specific patterns
    inherit from this base and add their own specialized parameters.

    Common Development Components:
    - Land acquisition and closing costs
    - Construction timeline and financing
    - Partnership structure and distributions
    - Exit strategy and disposition

    Subclasses must implement:
    - Asset-specific building parameters (SF vs units vs other metrics)
    - Asset-specific leasing and absorption assumptions
    - Asset-specific construction cost models
    - create(): Assembly of asset-appropriate Deal components
    """

    # === CORE PROJECT PARAMETERS ===
    project_name: str = Field(..., description="Development project name")
    acquisition_date: date = Field(..., description="Land acquisition closing date")
    land_cost: PositiveFloat = Field(..., description="Land acquisition cost")
    land_closing_costs_rate: FloatBetween0And1 = Field(
        default=0.025, description="Land closing costs as percentage of land cost"
    )

    # === CONSTRUCTION TIMELINE ===
    construction_start_months: PositiveInt = Field(
        default=3,
        ge=1,
        le=24,
        description="Months after land acquisition to start construction",
    )
    construction_duration_months: PositiveInt = Field(
        default=18, ge=6, le=60, description="Construction duration in months"
    )

    # === CONSTRUCTION FINANCING ===
    construction_ltc_ratio: FloatBetween0And1 = Field(
        default=0.70,
        le=0.85,
        description="Loan-to-cost ratio for construction financing",
    )
    construction_ltc_max: FloatBetween0And1 = Field(
        default=0.80,
        le=0.85,
        description="Maximum LTC threshold - lender's covenant that cannot be exceeded",
    )
    construction_interest_rate: FloatBetween0And1 = Field(
        default=0.065, description="Interest rate for construction loan"
    )
    construction_fee_rate: FloatBetween0And1 = Field(
        default=0.01, description="Origination fee rate for construction loan"
    )
    interest_calculation_method: Literal["NONE", "SIMPLE", "SCHEDULED", "ITERATIVE"] = (
        Field(
            default="SCHEDULED",
            description="Construction loan interest calculation method",
        )
    )
    interest_reserve_rate: Optional[FloatBetween0And1] = Field(
        default=None,
        description="Interest reserve as percentage of loan amount (only used with SIMPLE method)",
    )

    # === PERMANENT FINANCING ===
    permanent_ltv_ratio: FloatBetween0And1 = Field(
        default=0.70, le=0.80, description="Loan-to-value ratio for permanent financing"
    )
    permanent_interest_rate: FloatBetween0And1 = Field(
        default=0.055, description="Interest rate for permanent loan"
    )
    permanent_loan_term_years: PositiveInt = Field(
        default=10, ge=5, le=30, description="Permanent loan term in years"
    )
    permanent_amortization_years: PositiveInt = Field(
        default=25,
        ge=20,
        le=40,
        description="Permanent loan amortization period in years",
    )

    # === PARTNERSHIP STRUCTURE ===
    distribution_method: Literal["pari_passu", "waterfall"] = Field(
        default="waterfall", description="Partnership distribution methodology"
    )
    gp_share: FloatBetween0And1 = Field(
        default=0.10, description="General Partner ownership percentage"
    )
    lp_share: FloatBetween0And1 = Field(
        default=0.90, description="Limited Partner ownership percentage"
    )
    preferred_return: FloatBetween0And1 = Field(
        default=0.08, description="LP preferred return rate (for waterfall structures)"
    )
    promote_tier_1: FloatBetween0And1 = Field(
        default=0.20, description="GP promote rate above preferred return"
    )

    # === EXIT STRATEGY ===
    hold_period_years: PositiveInt = Field(
        default=7,
        ge=3,
        le=15,
        description="Investment hold period in years (from land acquisition)",
    )
    exit_cap_rate: FloatBetween0And1 = Field(
        default=0.065,
        description="Exit capitalization rate for sale valuation (typical market: 6-7%)",
    )
    exit_costs_rate: FloatBetween0And1 = Field(
        default=0.025, description="Exit transaction costs as percentage of sale price"
    )

    # === VALIDATION RULES ===

    @field_validator("permanent_amortization_years")
    @classmethod
    def validate_amortization_vs_term(cls, v, info):
        """Ensure amortization period is longer than loan term."""
        if "permanent_loan_term_years" in info.data:
            loan_term = info.data["permanent_loan_term_years"]
            if v < loan_term:
                raise ValueError(
                    f"Amortization period ({v} years) must be >= loan term ({loan_term} years)"
                )
        return v

    @model_validator(mode="after")
    def validate_partnership_shares(self) -> "DevelopmentPatternBase":
        """Ensure GP and LP shares sum to 100%."""
        total_share = self.gp_share + self.lp_share
        if abs(total_share - 1.0) > 0.001:  # Allow for floating point precision
            raise ValueError(
                f"GP share ({self.gp_share:.1%}) + LP share ({self.lp_share:.1%}) must equal 100%"
            )
        return self

    def _derive_timeline(self) -> Timeline:
        """Derive timeline from hold period."""
        return Timeline(
            start_date=self.acquisition_date,
            duration_months=self.hold_period_years * 12,
        )

    @abstractmethod
    def create(self) -> Deal:
        """
        Create the complete development deal.

        Subclasses must implement this method to create asset-specific
        development deals with appropriate components for their asset type.

        Returns:
            Complete Deal object ready for analysis
        """
        pass
