# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from pydantic import ValidationError

from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    InflationSettings,
    InflationTimingEnum,
    ReportingSettings,
)


def test_global_settings_default_instantiation():
    """Test that GlobalSettings can be instantiated with default values."""
    settings = GlobalSettings()
    assert isinstance(settings, GlobalSettings)
    assert isinstance(settings.reporting, ReportingSettings)
    assert settings.reporting.reporting_frequency == FrequencyEnum.ANNUAL
    assert settings.inflation.inflation_timing == InflationTimingEnum.START_OF_YEAR


def test_global_settings_custom_instantiation():
    """Test that GlobalSettings can be instantiated with custom values."""
    reporting_settings = ReportingSettings(fiscal_year_start_month=3, decimal_precision=0)
    settings = GlobalSettings(
        reporting=reporting_settings,
        valuation={"discount_rate": 0.075}
    )
    assert settings.reporting.fiscal_year_start_month == 3
    assert settings.reporting.decimal_precision == 0
    assert settings.valuation.discount_rate == 0.075


def test_inflation_settings_validator_success():
    """Test the validator on InflationSettings for valid configurations."""
    # This should work
    InflationSettings(
        inflation_timing=InflationTimingEnum.SPECIFIC_MONTH,
        inflation_timing_month=6
    )
    # This should also work
    InflationSettings(
        inflation_timing=InflationTimingEnum.START_OF_YEAR,
        inflation_timing_month=None
    )


def test_inflation_settings_validator_failure_missing_month():
    """Test that the validator fails when a specific month is required but not provided."""
    with pytest.raises(ValueError, match="must be set when inflation_timing is SPECIFIC_MONTH"):
        InflationSettings(
            inflation_timing=InflationTimingEnum.SPECIFIC_MONTH,
            inflation_timing_month=None
        )


def test_inflation_settings_validator_failure_extra_month():
    """Test that the validator fails when a month is provided but not required."""
    with pytest.raises(ValueError, match="should only be set when inflation_timing is SPECIFIC_MONTH"):
        InflationSettings(
            inflation_timing=InflationTimingEnum.MID_YEAR,
            inflation_timing_month=6
        )


def test_reporting_settings_field_validation():
    """Test Pydantic's built-in field validation for constraints."""
    # Test fiscal_year_start_month constraints (PositiveInt, ge=1, le=12)
    with pytest.raises(ValidationError):
        ReportingSettings(fiscal_year_start_month=0)  # Fails ge=1
    with pytest.raises(ValidationError):
        ReportingSettings(fiscal_year_start_month=13)  # Fails le=12
    with pytest.raises(ValidationError):
        ReportingSettings(fiscal_year_start_month=1.5)  # Fails PositiveInt (strict=True)
    
    # Test successful case
    ReportingSettings(fiscal_year_start_month=12)
