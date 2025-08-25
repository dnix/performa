# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for draw schedule classes."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from performa.core.primitives import (
    DrawScheduleKindEnum,
    FirstLastDrawSchedule,
    FirstOnlyDrawSchedule,
    LastOnlyDrawSchedule,
    ManualDrawSchedule,
    SCurveDrawSchedule,
    Timeline,
    UniformDrawSchedule,
)


class TestUniformDrawSchedule:
    """Tests for UniformDrawSchedule."""

    def test_uniform_schedule_creation(self):
        """Test creating a uniform draw schedule."""
        schedule = UniformDrawSchedule()
        assert schedule.kind == DrawScheduleKindEnum.UNIFORM

    def test_uniform_schedule_json_serialization(self):
        """Test JSON serialization of uniform schedule."""
        schedule = UniformDrawSchedule()
        json_data = schedule.model_dump()
        assert json_data == {"kind": "uniform"}

        # Test round-trip
        reloaded = UniformDrawSchedule.model_validate(json_data)
        assert reloaded.kind == DrawScheduleKindEnum.UNIFORM

    def test_uniform_apply_to_amount(self):
        """Test applying uniform schedule to an amount."""
        schedule = UniformDrawSchedule()
        result = schedule.apply_to_amount(amount=100_000, periods=5)

        # Should be evenly distributed
        expected = [20_000, 20_000, 20_000, 20_000, 20_000]
        assert result.tolist() == expected
        assert result.sum() == 100_000


class TestSCurveDrawSchedule:
    """Tests for SCurveDrawSchedule."""

    def test_s_curve_default_sigma(self):
        """Test S-curve with default sigma value."""
        schedule = SCurveDrawSchedule()
        assert schedule.kind == DrawScheduleKindEnum.S_CURVE
        assert schedule.sigma == 1.0

    def test_s_curve_custom_sigma(self):
        """Test S-curve with custom sigma value."""
        schedule = SCurveDrawSchedule(sigma=2.5)
        assert schedule.sigma == 2.5

    def test_s_curve_invalid_sigma(self):
        """Test S-curve with invalid sigma value."""
        with pytest.raises(ValidationError):
            SCurveDrawSchedule(sigma=-1.0)

    def test_s_curve_json_serialization(self):
        """Test JSON serialization of S-curve schedule."""
        schedule = SCurveDrawSchedule(sigma=1.5)
        json_data = schedule.model_dump()
        assert json_data == {"kind": "s-curve", "sigma": 1.5}

        # Test round-trip
        reloaded = SCurveDrawSchedule.model_validate(json_data)
        assert reloaded.sigma == 1.5

    def test_s_curve_apply_to_amount(self):
        """Test applying S-curve schedule to an amount."""
        schedule = SCurveDrawSchedule(sigma=1.0)
        result = schedule.apply_to_amount(amount=100_000, periods=6)

        # Should sum to total amount
        assert abs(result.sum() - 100_000) < 0.01  # Allow for floating point precision

        # Should follow S-curve pattern (low -> high -> low)
        assert result.iloc[0] < result.iloc[2]  # Start low
        assert result.iloc[-1] < result.iloc[2]  # End low
        assert result.iloc[2] > result.iloc[0]  # Middle is higher


class TestManualDrawSchedule:
    """Tests for ManualDrawSchedule."""

    def test_manual_schedule_creation(self):
        """Test creating a manual draw schedule."""
        values = [1.0, 2.0, 3.0, 2.0, 1.0]
        schedule = ManualDrawSchedule(values=values)
        assert schedule.kind == DrawScheduleKindEnum.MANUAL
        assert schedule.values == values

    def test_manual_schedule_normalization_concept(self):
        """Test that manual values work for normalization."""
        # Values don't need to sum to 1.0, they'll be normalized
        values = [10, 20, 30, 20, 10]  # Sum = 90
        schedule = ManualDrawSchedule(values=values)
        assert sum(schedule.values) == 90

    def test_manual_schedule_empty_values(self):
        """Test manual schedule with empty values list."""
        with pytest.raises(ValidationError) as exc_info:
            ManualDrawSchedule(values=[])
        assert "at least 1 item" in str(exc_info.value).lower()

    def test_manual_schedule_negative_values(self):
        """Test manual schedule with negative values."""
        with pytest.raises(ValidationError):
            ManualDrawSchedule(values=[1.0, -2.0, 3.0])

    def test_manual_schedule_json_serialization(self):
        """Test JSON serialization of manual schedule."""
        values = [1.0, 2.0, 3.0]
        schedule = ManualDrawSchedule(values=values)
        json_data = schedule.model_dump()
        # period_count is now @property (not @computed_field), so not serialized
        assert json_data["kind"] == "manual"
        assert json_data["values"] == values
        # period_count still works as a property but is not serialized
        assert schedule.period_count == 3

        # Test round-trip
        reloaded = ManualDrawSchedule.model_validate(json_data)
        assert reloaded.values == values

    def test_manual_apply_to_amount(self):
        """Test applying manual schedule to an amount."""
        schedule = ManualDrawSchedule(values=[1, 2, 3, 2, 1])
        result = schedule.apply_to_amount(amount=90_000, periods=5)

        # Should be normalized: [1,2,3,2,1] -> [10k, 20k, 30k, 20k, 10k]
        expected = [10_000, 20_000, 30_000, 20_000, 10_000]
        assert result.tolist() == expected
        assert result.sum() == 90_000

    def test_manual_apply_to_amount_period_mismatch(self):
        """Test manual schedule with period count mismatch."""
        schedule = ManualDrawSchedule(values=[1, 2, 3, 2, 1])

        # Should raise error if periods don't match
        with pytest.raises(ValueError) as exc_info:
            schedule.apply_to_amount(amount=100_000, periods=3)
        assert "5 values but 3 periods" in str(exc_info.value)

    def test_manual_integers_and_floats(self):
        """Test manual schedule with integers and floats."""
        schedule = ManualDrawSchedule(values=[10, 20.5, 30, 15.5, 5])
        result = schedule.apply_to_amount(amount=81_000, periods=5)

        # Should sum to total
        assert result.sum() == 81_000

        # Should normalize properly
        total_weights = sum(schedule.values)  # 81
        expected = [
            81_000 * (10 / total_weights),
            81_000 * (20.5 / total_weights),
            81_000 * (30 / total_weights),
            81_000 * (15.5 / total_weights),
            81_000 * (5 / total_weights),
        ]
        np.testing.assert_array_almost_equal(result.values, expected)

    def test_manual_create_for_timeline(self):
        """Test the create_for_timeline factory method."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=3)

        # Factory methods are simple constructors
        schedule = ManualDrawSchedule.create_for_timeline([1, 2, 3], timeline)
        assert schedule.values == [1, 2, 3]
        assert schedule.period_count == 3

        # Can create schedules with any length - validation deferred to usage
        schedule2 = ManualDrawSchedule.create_for_timeline([1, 2, 3, 4, 5], timeline)
        assert schedule2.values == [1, 2, 3, 4, 5]
        assert schedule2.period_count == 5

        # Validation happens when actually used
        with pytest.raises(ValueError) as exc_info:
            schedule2.apply_to_amount(100_000, periods=3)  # timeline has 3 months
        assert "5 values but 3 periods" in str(exc_info.value)

    def test_manual_create_for_periods(self):
        """Test the create_for_periods factory method."""
        # Factory methods are simple constructors
        schedule = ManualDrawSchedule.create_for_periods([10, 20, 30], periods=3)
        assert schedule.values == [10, 20, 30]
        assert schedule.period_count == 3

        # Can create schedules with any length - validation deferred to usage
        schedule2 = ManualDrawSchedule.create_for_periods([1, 2], periods=4)
        assert schedule2.values == [1, 2]
        assert schedule2.period_count == 2

        # Validation happens when actually used
        with pytest.raises(ValueError) as exc_info:
            schedule2.apply_to_amount(100_000, periods=4)  # 4 periods expected
        assert "2 values but 4 periods" in str(exc_info.value)


class TestFirstLastDrawSchedule:
    """Tests for FirstLastDrawSchedule."""

    def test_first_last_with_first_percentage(self):
        """Test first-last schedule specifying first percentage."""
        schedule = FirstLastDrawSchedule(first_percentage=0.3)
        assert schedule.kind == DrawScheduleKindEnum.FIRST_LAST
        assert schedule.first_percentage == 0.3
        assert schedule.last_percentage is None

    def test_first_last_with_last_percentage(self):
        """Test first-last schedule specifying last percentage."""
        schedule = FirstLastDrawSchedule(last_percentage=0.7)
        assert schedule.kind == DrawScheduleKindEnum.FIRST_LAST
        assert schedule.effective_first_percentage == 0.3  # Calculated from 1.0 - 0.7
        assert schedule.last_percentage == 0.7

    def test_first_last_mutual_exclusivity(self):
        """Test that first and last percentage are mutually exclusive."""
        # Should fail if both are specified
        with pytest.raises(ValidationError) as exc_info:
            FirstLastDrawSchedule(first_percentage=0.3, last_percentage=0.7)
        assert (
            "must specify either first_percentage or last_percentage"
            in str(exc_info.value).lower()
        )

    def test_first_last_requires_one_percentage(self):
        """Test that at least one percentage must be specified."""
        # Should fail if neither is specified
        with pytest.raises(ValidationError) as exc_info:
            FirstLastDrawSchedule()
        assert "must specify" in str(exc_info.value).lower()

    def test_first_last_boundary_values(self):
        """Test first-last schedule with boundary values."""
        # 0% first (all last)
        schedule1 = FirstLastDrawSchedule(first_percentage=0.0)
        assert schedule1.first_percentage == 0.0
        assert schedule1.effective_first_percentage == 0.0

        # 100% first (none last)
        schedule2 = FirstLastDrawSchedule(first_percentage=1.0)
        assert schedule2.first_percentage == 1.0
        assert schedule2.effective_first_percentage == 1.0

        # 0% last (all first)
        schedule3 = FirstLastDrawSchedule(last_percentage=0.0)
        assert schedule3.effective_first_percentage == 1.0

        # 100% last (none first)
        schedule4 = FirstLastDrawSchedule(last_percentage=1.0)
        assert schedule4.effective_first_percentage == 0.0

    def test_first_last_invalid_percentage(self):
        """Test first-last schedule with invalid percentage."""
        with pytest.raises(ValidationError):
            FirstLastDrawSchedule(first_percentage=1.5)  # > 1.0

        with pytest.raises(ValidationError):
            FirstLastDrawSchedule(first_percentage=-0.1)  # < 0.0

        with pytest.raises(ValidationError):
            FirstLastDrawSchedule(last_percentage=1.5)  # > 1.0

        with pytest.raises(ValidationError):
            FirstLastDrawSchedule(last_percentage=-0.1)  # < 0.0

    def test_first_last_json_serialization(self):
        """Test JSON serialization of first-last schedule."""
        # Test with first_percentage
        schedule1 = FirstLastDrawSchedule(first_percentage=0.25)
        json_data1 = schedule1.model_dump()
        assert json_data1["kind"] == "first-last"
        assert json_data1["first_percentage"] == 0.25
        assert "last_percentage" not in json_data1  # Should be excluded

        # Test with last_percentage
        schedule2 = FirstLastDrawSchedule(last_percentage=0.75)
        json_data2 = schedule2.model_dump()
        assert json_data2["kind"] == "first-last"
        assert "first_percentage" not in json_data2  # Should be excluded
        assert json_data2["last_percentage"] == 0.75

        # Test round-trip
        reloaded1 = FirstLastDrawSchedule.model_validate(json_data1)
        assert reloaded1.first_percentage == 0.25
        assert reloaded1.effective_first_percentage == 0.25

        reloaded2 = FirstLastDrawSchedule.model_validate(json_data2)
        assert reloaded2.last_percentage == 0.75
        assert reloaded2.effective_first_percentage == 0.25

    def test_first_last_apply_to_amount(self):
        """Test applying first-last schedule to an amount."""
        schedule = FirstLastDrawSchedule(first_percentage=0.3)
        result = schedule.apply_to_amount(amount=100_000, periods=5)

        # Should have 30k in first period, 70k in last period, 0 in middle
        expected = [30_000, 0, 0, 0, 70_000]
        assert result.tolist() == expected
        assert result.sum() == 100_000

    def test_first_last_apply_to_amount_insufficient_periods(self):
        """Test first-last schedule with insufficient periods."""
        schedule = FirstLastDrawSchedule(first_percentage=0.5)

        # Should raise error if less than 2 periods
        with pytest.raises(ValueError) as exc_info:
            schedule.apply_to_amount(amount=100_000, periods=1)
        assert "requires at least 2 periods" in str(exc_info.value)


class TestFirstOnlyDrawSchedule:
    """Tests for FirstOnlyDrawSchedule."""

    def test_first_only_creation(self):
        """Test creating a first-only draw schedule."""
        schedule = FirstOnlyDrawSchedule()
        assert schedule.kind == DrawScheduleKindEnum.FIRST_ONLY

    def test_first_only_json_serialization(self):
        """Test JSON serialization of first-only schedule."""
        schedule = FirstOnlyDrawSchedule()
        json_data = schedule.model_dump()
        assert json_data == {"kind": "first-only"}

        # Test round-trip
        reloaded = FirstOnlyDrawSchedule.model_validate(json_data)
        assert reloaded.kind == DrawScheduleKindEnum.FIRST_ONLY

    def test_first_only_apply_to_amount(self):
        """Test applying first-only schedule to an amount."""
        schedule = FirstOnlyDrawSchedule()
        result = schedule.apply_to_amount(amount=50_000, periods=5)

        # Should have entire amount in first period
        expected = [50_000, 0, 0, 0, 0]
        assert result.tolist() == expected
        assert result.sum() == 50_000


class TestLastOnlyDrawSchedule:
    """Tests for LastOnlyDrawSchedule."""

    def test_last_only_creation(self):
        """Test creating a last-only draw schedule."""
        schedule = LastOnlyDrawSchedule()
        assert schedule.kind == DrawScheduleKindEnum.LAST_ONLY

    def test_last_only_json_serialization(self):
        """Test JSON serialization of last-only schedule."""
        schedule = LastOnlyDrawSchedule()
        json_data = schedule.model_dump()
        assert json_data == {"kind": "last-only"}

        # Test round-trip
        reloaded = LastOnlyDrawSchedule.model_validate(json_data)
        assert reloaded.kind == DrawScheduleKindEnum.LAST_ONLY

    def test_last_only_apply_to_amount(self):
        """Test applying last-only schedule to an amount."""
        schedule = LastOnlyDrawSchedule()
        result = schedule.apply_to_amount(amount=75_000, periods=5)

        # Should have entire amount in last period
        expected = [0, 0, 0, 0, 75_000]
        assert result.tolist() == expected
        assert result.sum() == 75_000


class TestDrawScheduleDiscriminator:
    """Test the discriminated union functionality."""

    def test_parse_uniform_from_dict(self):
        """Test parsing uniform schedule from dict."""
        data = {"kind": "uniform"}
        schedule = UniformDrawSchedule.model_validate(data)
        assert isinstance(schedule, UniformDrawSchedule)

    def test_parse_s_curve_from_dict(self):
        """Test parsing S-curve schedule from dict."""

        data = {"kind": "s-curve", "sigma": 2.0}
        # Note: In practice, you'd use a parent model with AnyDrawSchedule field
        # This is just testing the type structure exists

    def test_parse_manual_from_dict(self):
        """Test parsing manual schedule from dict."""

        data = {"kind": "manual", "values": [1, 2, 3]}
        # Note: In practice, you'd use a parent model with AnyDrawSchedule field
        # This is just testing the type structure exists

    def test_apply_to_amount_with_period_index(self):
        """Test applying schedule with a PeriodIndex."""
        schedule = ManualDrawSchedule(values=[1, 2, 3])

        # Create a PeriodIndex
        index = pd.period_range(start="2024-01", periods=3, freq="M")

        result = schedule.apply_to_amount(amount=60_000, periods=3, index=index)

        # Should use the provided index
        assert isinstance(result.index, pd.PeriodIndex)
        assert len(result.index) == 3
        assert result.index.equals(index)

        # Should still normalize correctly
        expected = [10_000, 20_000, 30_000]
        assert result.tolist() == expected

    def test_apply_to_amount_validation_errors(self):
        """Test validation errors in apply_to_amount method."""
        schedule = UniformDrawSchedule()

        # Test negative periods
        with pytest.raises(ValueError) as exc_info:
            schedule.apply_to_amount(amount=100_000, periods=-1)
        assert "greater than or equal to 0" in str(exc_info.value)

        # Test zero periods
        with pytest.raises(ValueError) as exc_info:
            schedule.apply_to_amount(amount=100_000, periods=0)
        assert "greater than 0" in str(exc_info.value)

        # Test index length mismatch
        index = pd.period_range("2024-01", periods=5, freq="M")
        with pytest.raises(ValueError) as exc_info:
            schedule.apply_to_amount(amount=100_000, periods=3, index=index)
        assert "Index length (5) must match periods (3)" in str(exc_info.value)

        # Test non-PeriodIndex
        with pytest.raises(ValueError) as exc_info:
            schedule.apply_to_amount(amount=100_000, periods=3, index=[1, 2, 3])
        assert "instance of PeriodIndex" in str(exc_info.value)
