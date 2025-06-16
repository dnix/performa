from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.common.primitives import Timeline


# Test Instantiation and Validation
def test_timeline_instantiation_absolute():
    """Test successful instantiation of an absolute timeline."""
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
    assert not timeline.is_relative
    assert timeline.start_date == pd.Period('2024-01', freq='M')

def test_timeline_instantiation_relative():
    """Test successful instantiation of a relative timeline."""
    timeline = Timeline(start_offset_months=6, duration_months=12)
    assert timeline.is_relative
    assert timeline.start_offset_months == 6

def test_timeline_instantiation_fails_with_both_starts():
    """Test that instantiation fails if both start_date and start_offset_months are provided."""
    with pytest.raises(ValueError, match="not both"):
        Timeline(start_date=date(2024, 1, 1), start_offset_months=6, duration_months=12)

def test_timeline_instantiation_fails_with_no_start():
    """Test that instantiation fails if neither start_date nor start_offset_months are provided."""
    with pytest.raises(ValueError, match="not both"):
        Timeline(duration_months=12)

# Test Classmethods
def test_timeline_from_dates():
    """Test the from_dates classmethod for creating an absolute timeline."""
    timeline = Timeline.from_dates(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    assert not timeline.is_relative
    assert timeline.duration_months == 12
    assert timeline.start_date == pd.Period('2024-01', 'M')

def test_timeline_from_relative():
    """Test the from_relative classmethod for creating a relative timeline."""
    timeline = Timeline.from_relative(months_until_start=3, duration_months=6)
    assert timeline.is_relative
    assert timeline.start_offset_months == 3
    assert timeline.duration_months == 6

# Test Property and Method Behavior on Relative Timelines
def test_relative_timeline_raises_error_on_absolute_properties():
    """Test that properties requiring an absolute date raise errors on relative timelines."""
    relative_timeline = Timeline.from_relative(months_until_start=0, duration_months=12)
    with pytest.raises(ValueError, match="Cannot get a start date from a relative timeline"):
        _ = relative_timeline.end_date
    with pytest.raises(ValueError, match="Cannot get a start date from a relative timeline"):
        _ = relative_timeline.period_index
    with pytest.raises(ValueError, match="Cannot get a start date from a relative timeline"):
        _ = relative_timeline.date_index
    with pytest.raises(ValueError, match="Cannot get a start date from a relative timeline"):
        relative_timeline.resample('Q')
    with pytest.raises(ValueError, match="Cannot get a start date from a relative timeline"):
        relative_timeline.align_series(pd.Series())

# Test shift_to_index
def test_timeline_shift_to_index():
    """Test the shift_to_index method converts a relative timeline to an absolute one."""
    reference_timeline = Timeline(start_date=date(2025, 6, 1), duration_months=12)
    reference_index = reference_timeline.period_index

    relative_timeline = Timeline.from_relative(months_until_start=3, duration_months=6)
    
    shifted_timeline = relative_timeline.shift_to_index(reference_index)
    
    # Check new timeline properties
    assert not shifted_timeline.is_relative
    assert shifted_timeline.start_offset_months is None
    assert shifted_timeline.start_date == pd.Period('2025-09', 'M') # June + 3 months
    assert shifted_timeline.duration_months == 6
    assert shifted_timeline.end_date == pd.Period('2026-02', 'M')

    # Ensure original timeline is unchanged
    assert relative_timeline.is_relative
    assert relative_timeline.start_offset_months == 3

def test_shift_to_index_raises_error_on_absolute_timeline():
    """Test that shift_to_index raises a ValueError if called on an absolute timeline."""
    absolute_timeline = Timeline(start_date=date(2025, 1, 1), duration_months=12)
    with pytest.raises(ValueError, match="Can only shift relative timelines"):
        absolute_timeline.shift_to_index(absolute_timeline.period_index)
