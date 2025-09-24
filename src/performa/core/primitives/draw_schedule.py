# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Draw schedule system for distributing costs over time.

This module provides flexible draw scheduling for capital expenditures,
supporting uniform, S-curve, and manual distribution patterns commonly
used in real estate development and construction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Literal, Optional, Union

import numpy as np
import pandas as pd
from pydantic import Field, field_validator, model_validator
from scipy.stats import norm
from typing_extensions import Annotated

from .enums import DrawScheduleKindEnum
from .model import Model
from .types import PositiveFloat, PositiveInt
from .validation import ValidationMixin


class DrawScheduleParameters(Model):
    """
    Validation model for apply_to_amount method parameters.

    Ensures type safety and validation for method parameters
    using Pydantic's validation framework.
    """

    amount: float = Field(ge=0, description="Total amount to distribute")
    periods: PositiveInt = Field(
        gt=0, description="Number of periods to distribute over"
    )
    index: Optional[pd.PeriodIndex] = Field(
        default=None, description="Optional PeriodIndex for the resulting Series"
    )

    @field_validator("index")
    @classmethod
    def validate_index(cls, v: Optional[pd.PeriodIndex]) -> Optional[pd.PeriodIndex]:
        """Validate that index is a PeriodIndex if provided."""
        if v is not None and not isinstance(v, pd.PeriodIndex):
            raise ValueError("Index must be a pandas PeriodIndex")
        return v

    @model_validator(mode="after")
    def validate_index_length(self) -> "DrawScheduleParameters":
        """Validate that index length matches periods if both are provided."""
        if self.index is not None and len(self.index) != self.periods:
            raise ValueError(
                f"Index length ({len(self.index)}) must match periods ({self.periods})"
            )
        return self


class DrawSchedule(Model, ValidationMixin, ABC):
    """
    Base class for all draw schedules.

    Uses template method pattern - each subclass implements its own
    distribution pattern via _get_distribution_pattern(), while the
    base class handles the common logic of applying it to amounts.
    """

    kind: DrawScheduleKindEnum

    def apply_to_amount(
        self, amount: float, periods: int, index: Optional[pd.PeriodIndex] = None
    ) -> pd.Series:
        """
        Apply this draw schedule to distribute an amount over periods.

        This is the template method that provides consistent behavior
        across all draw schedule types.

        Args:
            amount: Total amount to distribute
            periods: Number of periods to distribute over
            index: Optional PeriodIndex for the resulting Series

        Returns:
            Series with distributed amounts that sum to the total amount

        Raises:
            ValueError: If periods/index validation fails

        Example:
            >>> schedule = ManualDrawSchedule(values=[1, 2, 3, 2, 1])
            >>> result = schedule.apply_to_amount(90_000, periods=5)
            >>> result.sum()  # Returns 90_000.0
        """
        # Validate parameters using Pydantic
        params = DrawScheduleParameters(amount=amount, periods=periods, index=index)

        # Get the distribution pattern from the subclass
        distribution = self._get_distribution_pattern(params.periods)

        # Validate distribution pattern length
        if len(distribution) != params.periods:
            raise ValueError(
                f"Distribution pattern length ({len(distribution)}) does not match periods ({params.periods})"
            )

        # Apply distribution to the amount
        values = params.amount * distribution

        # Create series with proper index
        if params.index is not None:
            return pd.Series(values, index=params.index)
        else:
            return pd.Series(values)

    @abstractmethod
    def _get_distribution_pattern(self, periods: int) -> np.ndarray:
        """
        Get the distribution pattern for this schedule type.

        Each subclass must implement this method to define how it
        distributes amounts across periods.

        Args:
            periods: Number of periods to distribute over

        Returns:
            Array of values that sum to 1.0, representing the
            fraction of total amount for each period

        Raises:
            ValueError: If periods is invalid for this schedule type
        """
        pass


class UniformDrawSchedule(DrawSchedule):
    """
    Uniform draw schedule (evenly distributed).

    The simplest draw schedule where costs are spread evenly
    across all periods. This is the default behavior.

    Example:
        >>> schedule = UniformDrawSchedule()
        >>> result = schedule.apply_to_amount(100_000, periods=10)
        >>> # Returns: [10000, 10000, 10000, ...] (10 periods)
    """

    kind: Literal[DrawScheduleKindEnum.UNIFORM] = DrawScheduleKindEnum.UNIFORM

    def _get_distribution_pattern(self, periods: int) -> np.ndarray:
        """Evenly distribute across all periods."""
        return np.ones(periods) / periods


class SCurveDrawSchedule(DrawSchedule):
    """
    S-curve draw schedule with a sigma parameter.

    Models the typical construction spending pattern where costs
    start slow, accelerate through the middle phase, and taper
    off near completion. Uses a normal cumulative distribution.

    Args:
        sigma: Standard deviation parameter controlling curve steepness.
               Lower values (0.5-1.0) create steeper curves.
               Higher values (2.0-3.0) create more gradual curves.

    Example:
        >>> schedule = SCurveDrawSchedule(sigma=1.0)
        >>> result = schedule.apply_to_amount(100_000, periods=6)
        >>> # Returns S-curve pattern: low->high->low spending
    """

    kind: Literal[DrawScheduleKindEnum.S_CURVE] = DrawScheduleKindEnum.S_CURVE
    sigma: PositiveFloat = Field(
        default=1.0,
        gt=0,
        description="Standard deviation for S-curve distribution. Lower = steeper curve.",
    )

    def _get_distribution_pattern(self, periods: int) -> np.ndarray:
        """Calculate S-curve distribution using normal cumulative distribution."""
        timeline_int = np.arange(0, periods)

        # Calculate cumulative distribution
        cdf_values = norm.cdf(timeline_int + 1, periods / 2, self.sigma) - norm.cdf(
            timeline_int, periods / 2, self.sigma
        )

        # Normalize to ensure sum equals 1
        normalization_factor = 1 - 2 * norm.cdf(0, periods / 2, self.sigma)
        return cdf_values / normalization_factor


class ManualDrawSchedule(DrawSchedule):
    """
    Manual draw schedule with user-defined values.

    Allows complete control over draw patterns by specifying
    the relative weight for each period. Values are automatically
    normalized to sum to the total cost.

    Accepts any positive numbers (integers or floats) and normalizes them.
    For example, [1, 2, 3, 2, 1] becomes [11.1%, 22.2%, 33.3%, 22.2%, 11.1%].

    Args:
        values: List of positive values representing relative draw amounts.
                Can be integers, floats, or percentages - will be normalized.
                Length must match the periods when applied to an amount.

    Example:
        >>> schedule = ManualDrawSchedule(values=[1, 2, 3, 2, 1])
        >>> result = schedule.apply_to_amount(90_000, periods=5)
        >>> # Returns: [10000, 20000, 30000, 20000, 10000]
    """

    kind: Literal[DrawScheduleKindEnum.MANUAL] = DrawScheduleKindEnum.MANUAL
    values: List[Union[int, float]] = Field(
        min_length=1,
        description="Relative draw amounts for each period. Any positive numbers - will be normalized.",
    )

    @field_validator("values")
    @classmethod
    def validate_values(cls, v: List[Union[int, float]]) -> List[Union[int, float]]:
        """Validate that values are positive and non-empty."""
        # Check all values are positive
        for i, val in enumerate(v):
            if val <= 0:
                raise ValueError(
                    f"All values must be positive, but value at index {i} is {val}"
                )

        return v

    @property
    def period_count(self) -> int:
        """Number of periods in this schedule."""
        return len(self.values)

    @classmethod
    def create_for_timeline(
        cls, values: List[Union[int, float]], timeline
    ) -> "ManualDrawSchedule":
        """
        Create a ManualDrawSchedule for use with a timeline.

        This is a convenience constructor that documents the intended timeline
        usage. Compatibility validation occurs when the schedule is actually
        applied to an amount.

        Args:
            values: List of relative draw amounts
            timeline: Timeline object (for documentation/context)

        Returns:
            ManualDrawSchedule instance

        Example:
            >>> from performa.core.primitives import Timeline
            >>> from datetime import date
            >>> timeline = Timeline(start_date=date(2024, 1, 1), duration_months=3)
            >>> schedule = ManualDrawSchedule.create_for_timeline([1, 2, 3], timeline)
        """
        return cls(values=values)

    @classmethod
    def create_for_periods(
        cls, values: List[Union[int, float]], periods: int
    ) -> "ManualDrawSchedule":
        """
        Create a ManualDrawSchedule for use with a specific period count.

        This is a convenience constructor that documents the intended period
        usage. Compatibility validation occurs when the schedule is actually
        applied to an amount.

        Args:
            values: List of relative draw amounts
            periods: Expected number of periods (for documentation/context)

        Returns:
            ManualDrawSchedule instance

        Example:
            >>> schedule = ManualDrawSchedule.create_for_periods([1, 2, 3, 4], periods=4)
        """
        return cls(values=values)

    def _get_distribution_pattern(self, periods: int) -> np.ndarray:
        """
        Get normalized distribution pattern for manual schedule.

        Validates that the period count matches schedule length and
        returns normalized values.
        """
        # Validate period count matches schedule length
        if self.period_count != periods:
            raise ValueError(
                f"Manual draw schedule has {self.period_count} values "
                f"but {periods} periods are required. "
                f"Expected values list of length {periods}, got length {self.period_count}."
            )

        # Normalize values to sum to 1.0
        total = sum(self.values)
        return np.array([float(v) / total for v in self.values])


class FirstLastDrawSchedule(DrawSchedule):
    """
    Draw schedule with payments split between first and last periods.

    Useful for milestone-based payments, deal fees, or any situation
    where payments occur at project start and completion.

    Args:
        first_percentage: Percentage of total to draw in first period (0.0 to 1.0).
                         Mutually exclusive with last_percentage.
        last_percentage: Percentage of total to draw in last period (0.0 to 1.0).
                        Mutually exclusive with first_percentage.

    Example:
        >>> # Specify using first percentage
        >>> schedule = FirstLastDrawSchedule(first_percentage=0.3)
        >>> # For $100,000 total: $30k in month 1, $70k in final month

        >>> # Or specify using last percentage
        >>> schedule = FirstLastDrawSchedule(last_percentage=0.7)
        >>> # Same result: $30k in month 1, $70k in final month
    """

    kind: Literal[DrawScheduleKindEnum.FIRST_LAST] = DrawScheduleKindEnum.FIRST_LAST
    first_percentage: Optional[PositiveFloat] = Field(
        default=None,
        le=1.0,
        description="Percentage to draw in first period (0.0 to 1.0)",
    )
    last_percentage: Optional[PositiveFloat] = Field(
        default=None,
        le=1.0,
        description="Percentage to draw in last period (0.0 to 1.0)",
    )

    @model_validator(mode="after")
    def validate_mutual_exclusivity(self) -> "FirstLastDrawSchedule":
        """
        Validate that exactly one of first_percentage or last_percentage is specified.
        """
        # Use ValidationMixin helper for mutual exclusivity validation
        data = {
            "first_percentage": self.first_percentage,
            "last_percentage": self.last_percentage,
        }
        ValidationMixin.validate_either_or_required(
            data,
            "first_percentage",
            "last_percentage",
            "Must specify either first_percentage or last_percentage",
        )
        return self

    @property
    def effective_first_percentage(self) -> float:
        """Get the effective first percentage, calculating from last_percentage if needed."""
        if self.first_percentage is not None:
            return float(self.first_percentage)
        elif self.last_percentage is not None:
            return round(
                1.0 - float(self.last_percentage), 10
            )  # Round to avoid float precision issues
        else:
            # This shouldn't happen due to validation, but provide a default
            return 0.5

    def model_dump(self, **kwargs):
        """Override to exclude calculated fields from serialization."""
        data = super().model_dump(**kwargs)
        # Only include the percentage that was explicitly set
        if self._was_last_percentage_set():
            data.pop("first_percentage", None)
        else:
            data.pop("last_percentage", None)
        return data

    def _was_last_percentage_set(self) -> bool:
        """Check if last_percentage was the originally set value."""
        # If first_percentage is None, then last_percentage was set
        return self.first_percentage is None

    def _get_distribution_pattern(self, periods: int) -> np.ndarray:
        """Create distribution with first/last split."""
        if periods < 2:
            raise ValueError("FirstLast schedule requires at least 2 periods")

        values = np.zeros(periods)
        values[0] = self.effective_first_percentage
        values[-1] = 1.0 - self.effective_first_percentage
        return values


class FirstOnlyDrawSchedule(DrawSchedule):
    """
    Draw schedule with entire amount in the first period.

    Common for upfront payments like:
    - Land acquisition
    - Upfront fees
    - Security deposits
    - Initial mobilization costs

    Example:
        >>> schedule = FirstOnlyDrawSchedule()
        >>> result = schedule.apply_to_amount(50_000, periods=5)
        >>> # Returns: [50000, 0, 0, 0, 0]
    """

    kind: Literal[DrawScheduleKindEnum.FIRST_ONLY] = DrawScheduleKindEnum.FIRST_ONLY

    def _get_distribution_pattern(self, periods: int) -> np.ndarray:
        """Put entire amount in first period."""
        values = np.zeros(periods)
        values[0] = 1.0
        return values


class LastOnlyDrawSchedule(DrawSchedule):
    """
    Draw schedule with entire amount in the last period.

    Common for completion-based payments like:
    - Success fees
    - Final contractor payments
    - Performance bonuses
    - Retention releases

    Example:
        >>> schedule = LastOnlyDrawSchedule()
        >>> result = schedule.apply_to_amount(75_000, periods=5)
        >>> # Returns: [0, 0, 0, 0, 75000]
    """

    kind: Literal[DrawScheduleKindEnum.LAST_ONLY] = DrawScheduleKindEnum.LAST_ONLY

    def _get_distribution_pattern(self, periods: int) -> np.ndarray:
        """Put entire amount in last period."""
        values = np.zeros(periods)
        values[-1] = 1.0
        return values


# Union type for all draw schedules, using discriminator for type differentiation
AnyDrawSchedule = Annotated[
    Union[
        SCurveDrawSchedule,
        UniformDrawSchedule,
        ManualDrawSchedule,
        FirstLastDrawSchedule,
        FirstOnlyDrawSchedule,
        LastOnlyDrawSchedule,
    ],
    Field(discriminator="kind"),
]
