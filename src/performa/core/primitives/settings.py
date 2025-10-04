# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .enums import FrequencyEnum
from .model import Model
from .types import FloatBetween0And1, PositiveFloat, PositiveInt


class DayCountConvention(str, Enum):
    """Day count conventions for financial calculations (Affects proration, interest)"""

    # TODO: Add implementation support for interest calculations and proration logic
    THIRTY_360 = "30/360"
    ACTUAL_360 = "Actual/360"
    ACTUAL_365 = "Actual/365"
    ACTUAL_ACTUAL = "Actual/Actual"


class InflationTimingEnum(str, Enum):
    """How inflation/growth rates are applied annually."""

    START_OF_YEAR = "Start of Year"  # Applied Jan 1st (or first month of fiscal year)
    MID_YEAR = "Mid-Year"  # Applied July 1st (or mid-point of fiscal year)
    SPECIFIC_MONTH = "Specific Month"  # Applied in the specified month
    # ANNIVERSARY = "Anniversary" # Likely applied at item level (e.g., lease anniversary)


class RecoveryMethodEnum(str, Enum):  # Placeholder, often expense-specific
    """Default method for calculating expense recoveries."""

    NET = "Net"  # Tenant pays pro-rata share of all OpEx
    BASE_YEAR_STOP = (
        "Base Year Stop"  # Tenant pays pro-rata share above a base year amount
    )
    FIXED_AMOUNT = "Fixed Amount"  # Tenant pays fixed $ psf/unit


class PercentageRentSettings(Model):
    """Percentage rent and occupancy cost settings (Planned for retail functionality)"""

    # TODO: Define actual settings based on requirements for retail asset types
    enabled: bool = False
    breakpoint_method: Literal["natural", "fixed"] = "natural"
    include_recoveries_in_breakpoint: bool = True
    # ... other potential settings ...


class ReportingSettings(Model):
    """Settings related to report generation and display."""

    reporting_frequency: FrequencyEnum = FrequencyEnum.ANNUAL
    # Use PositiveInt for fiscal month, keep validation logic
    fiscal_year_start_month: PositiveInt = Field(
        default=1, ge=1, le=12, description="Month the fiscal year begins (1=Jan)."
    )
    # Use PositiveInt for precision
    decimal_precision: PositiveInt = Field(
        default=2, description="Number of decimal places for currency values."
    )
    property_area_unit: Literal["sqft", "sqm"] = Field(
        default="sqft", description="Unit for area measurements (e.g., for PSF/PSM)."
    )
    # currency_code: str = "USD" # Future
    # currency_symbol: str = "$" # Future


class CalculationSettings(Model):
    """
    Configuration settings for the calculation engine behavior.

    These settings control how the property analysis calculation engine processes
    models, validates dependencies, and handles complex scenarios. They provide
    fine-grained control over calculation behavior without affecting the core
    business logic.

    Key Features:
    - Dependency complexity validation for defensive programming
    - Configurable limits for institutional vs. standard properties
    - Safety overrides to prevent accidental complex configurations

    Usage Examples:
        # Standard property analysis (default settings)
        calc_settings = CalculationSettings()

        # Institutional deal with complex dependencies
        calc_settings = CalculationSettings(
            max_dependency_depth=3,
            allow_complex_dependencies=True
        )

        # Conservative settings for high-volume batch processing
        calc_settings = CalculationSettings(
            max_dependency_depth=1,
            allow_complex_dependencies=False
        )
    """

    calculation_frequency: FrequencyEnum = Field(
        default=FrequencyEnum.MONTHLY,
        description="Frequency for cash flow calculations (Monthly, Quarterly, Annual).",
    )
    day_count_convention: DayCountConvention = Field(
        default=DayCountConvention.ACTUAL_ACTUAL,
        description="Day count convention for calculations (currently informational).",
    )
    fail_on_error: bool = Field(
        default=False,
        description="If True, raise calculation errors; otherwise, log and attempt to continue.",
    )
    max_dependency_depth: PositiveInt = Field(
        default=2,
        description=(
            "Maximum allowed depth of dependency chains between cash flow models. "
            "Controls complexity validation to prevent performance issues and hard-to-debug scenarios. "
            "Examples: 1=simple dependencies only, 2=standard (admin fees on totals), "
            "3+=complex institutional structures. Values >2 require allow_complex_dependencies=True."
        ),
    )
    allow_complex_dependencies: bool = Field(
        default=False,
        description=(
            "Safety flag that must be explicitly set to True for dependency depths >2. "
            "Prevents accidental complex configurations that could impact performance "
            "or create difficult debugging scenarios. Required for institutional deals "
            "with tiered fees, complex waterfalls, or nested percentage calculations."
        ),
    )


class InflationSettings(Model):
    """Global assumptions for general inflation rates."""

    # NOTE: this only applies for PercentageGrowthRate named inflation
    # NOTE: all rates are defined as PercentageGrowthRate, not percentages here in settings
    # TODO: Add inflation rate as baseline for GrowthRates and systematic application in analysis
    inflation_timing: InflationTimingEnum = Field(
        default=InflationTimingEnum.START_OF_YEAR,
        description="When annual inflation adjustments are applied.",
    )
    inflation_timing_month: Optional[PositiveInt] = Field(
        default=None,
        ge=1,
        le=12,
        description="Specific month (1-12) if inflation_timing is SPECIFIC_MONTH.",
    )

    @model_validator(mode="after")
    def check_inflation_month_logic(self) -> "InflationSettings":
        """Ensure inflation_timing_month is consistent with inflation_timing."""
        timing = self.inflation_timing
        month = self.inflation_timing_month

        if timing == InflationTimingEnum.SPECIFIC_MONTH and month is None:
            # Require month if timing is specific
            raise ValueError(
                "inflation_timing_month must be set when inflation_timing is SPECIFIC_MONTH"
            )

        if timing != InflationTimingEnum.SPECIFIC_MONTH and month is not None:
            # Month should only be set if timing is specific
            raise ValueError(
                "inflation_timing_month should only be set when inflation_timing is SPECIFIC_MONTH"
            )

        # The PositiveInt type and Field(ge=1, le=12) handle the 1-12 range check automatically now
        # No need for manual check here if Field constraints are sufficient.

        return self  # Return the validated model instance


class RecoverySettings(Model):
    """Settings for expense recovery calculations, including gross-up."""

    # Gross-up settings (existing, working)
    # Gross-up by downtime functionality implemented via occupancy-based calculations in recovery models
    gross_up_enabled: bool = Field(
        default=True,
        description="Enable grossing up of variable expenses for recovery calculations based on occupancy.",
    )
    gross_up_occupancy_threshold: FloatBetween0And1 = Field(
        default=0.95,
        description="Occupancy level (e.g., 0.95 for 95%) triggering expense gross-up.",
    )
    gross_up_uses_fixed_rate: bool = Field(
        default=False,
        description="If True, gross up to 100% occupancy always; if False, gross up to the threshold occupancy level (e.g., 95%).",
    )

    # Optional global default (recovery methods typically specified at lease level)
    default_recovery_method: Optional[RecoveryMethodEnum] = (
        None  # Usually property/lease-specific
    )

    # TODO: Centralize expense cap functionality from Recovery models to global settings

    # TODO: Future expense cap functionality integration
    # The cap functionality is currently implemented at the Recovery model level
    # Future enhancement could include:
    # - default_cap_rate: Optional[PositiveFloat] for portfolio-wide defaults
    # - cap_methodology: Literal["compound", "simple"] for calculation method
    # - portfolio_cap_policies: Dict for property-type specific defaults
    # - cap_validation_rules: For business logic enforcement


# TODO: Consider dedicated 'MarketLeasingSettings' sub-model for centralized market assumptions
# Current approach: Market terms specified per rollover profile (working, comprehensive implementation)


class ValuationSettings(Model):
    """Settings for property valuation metrics."""

    discount_rate: Optional[PositiveFloat] = Field(
        default=None, description="Annual discount rate used for DCF analysis."
    )
    exit_valuation_method: Literal["cap_rate", "dcf_only", "none"] = Field(
        default="none", description="Method for determining exit/terminal value."
    )
    exit_cap_rate: Optional[PositiveFloat] = Field(
        default=None, description="Cap rate applied to forward NOI for exit valuation."
    )
    refinancing_cap_rate: PositiveFloat = Field(
        default=0.065, description="Cap rate for refinancing property valuations."
    )
    refinancing_noi_method: Literal["ltm", "ntm", "current"] = Field(
        default="ltm",
        description="NOI calculation method for refinancing: ltm=trailing 12mo avg, ntm=forward 12mo, current=current period.",
    )
    exit_noi_method: Literal["ltm", "ntm"] = Field(
        default="ltm",
        description="NOI calculation method for exit valuation: ltm=trailing 12mo avg, ntm=forward-looking NOI.",
    )
    costs_of_sale_percentage: FloatBetween0And1 = Field(
        default=0.03, description="Transaction costs as a percentage of exit value."
    )
    
    development_valuation_method: Literal["cost", "income", "auto"] = Field(
        default="auto",
        description=(
            "Valuation method: 'cost' (land + costs), 'income' (NOI/cap rate), "
            "or 'auto' (detect phase and select method)."
        ),
    )
    development_phase_noi_threshold: FloatBetween0And1 = Field(
        default=0.70,
        description=(
            "NOI threshold for phase detection (as fraction of stabilized NOI). "
            "Higher = stay in cost mode longer. Only used when method='auto'."
        ),
    )
    development_phase_capex_threshold: FloatBetween0And1 = Field(
        default=0.01,
        description=(
            "Monthly cost growth threshold for phase detection (as fraction). "
            "Active capital deployment keeps cost method. Only used when method='auto'."
        ),
    )


# --- Main Global Settings Class ---


class GlobalSettings(Model):
    """Global model settings

    Configures global parameters affecting the entire financial model,
    grouped by functional area. Specific items (leases, expenses) can
    potentially override these defaults where applicable.
    """

    analysis_start_date: date = Field(default_factory=date.today)
    reporting: ReportingSettings = Field(default_factory=ReportingSettings)
    calculation: CalculationSettings = Field(default_factory=CalculationSettings)
    inflation: InflationSettings = Field(default_factory=InflationSettings)
    recoveries: RecoverySettings = Field(default_factory=RecoverySettings)
    valuation: ValuationSettings = Field(default_factory=ValuationSettings)
    percentage_rent: PercentageRentSettings = Field(
        default_factory=PercentageRentSettings
    )
