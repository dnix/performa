# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Capital planning system for Performa.

This module provides a hybrid approach to capital expenditure modeling:
- CapitalItem(CashFlowModel): Individual items with flexible timing
- CapitalPlan(Model): Container with factory methods for common patterns
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, computed_field, field_validator

from ..primitives import (
    AnyDrawSchedule,
    CashFlowModel,
    Model,
    PropertyAttributeKey,
    Timeline,
    UniformDrawSchedule,
    UnleveredAggregateLineKey,
)


class CapitalItem(CashFlowModel):
    """
    Individual capital expenditure item.

    Inherits all CashFlowModel functionality:
    - timeline: When and for how long the work occurs
    - value: Cost amount (supports scalar, series, dict for complex timing)
    - unit_of_measure: Currency, per-unit, or percentage
    - compute_cf(): Handles all cash flow logic with growth rates

    Key Difference from OpEx: Capital items typically don't grow, but
    CashFlowModel can handle growth if needed for inflation adjustments.
    """

    category: str = "Capital"
    subcategory: str = "RENOVATION"  # Can be overridden for specific types

    # Optional renovation-specific fields
    work_type: Optional[str] = None  # "Demo", "Construction", "Finishes", etc.
    contractor: Optional[str] = None
    permit_required: bool = False

    # Draw schedule for distributing costs over time
    draw_schedule: Optional[AnyDrawSchedule] = Field(
        default=None,
        description="Draw schedule for the capital item. Defaults to UniformDrawSchedule if not specified.",
    )

    @field_validator("draw_schedule")
    @classmethod
    def validate_draw_schedule(
        cls, v: Optional[AnyDrawSchedule], info
    ) -> AnyDrawSchedule:
        """Validate the draw schedule, ensuring it's set."""
        if v is None:
            return UniformDrawSchedule()

        # Note: Period count validation is now handled by the DrawSchedule
        # classes themselves when apply_to_amount() is called
        return v

    def compute_cf(self, context) -> pd.Series:
        """
        Compute capital expenditure cash flow using the draw schedule.

        This overrides the base CashFlowModel implementation to apply
        draw schedule distributions instead of uniform spreading.
        """
        # Handle reference resolution directly without calling super().compute_cf()
        # to avoid the monthly repetition issue in _cast_value_to_flow
        base_value = self.value

        # New unified reference-based calculation system (copied from CashFlowModel)
        if self.reference is None:
            # Direct currency amount - no multiplication needed
            pass

        elif isinstance(self.reference, PropertyAttributeKey):
            # Property attribute calculation (replaces PER_UNIT)
            if hasattr(context.property_data, self.reference.value):
                multiplier = getattr(context.property_data, self.reference.value)
                base_value = self.value * float(multiplier) if multiplier else 0.0
            else:
                raise AttributeError(
                    f"Property '{getattr(context.property_data, 'name', 'Unknown')}' "
                    f"missing attribute '{self.reference.value}' for calculation '{self.name}'. "
                    f"Available attributes: {[attr for attr in dir(context.property_data) if not attr.startswith('_')]}"
                )

        elif isinstance(self.reference, UnleveredAggregateLineKey):
            # Aggregate reference calculation (% of NOI, Total OpEx, etc.)
            if self.reference.value in context.resolved_lookups:
                aggregate_series = context.resolved_lookups[self.reference.value]
                # For capital items, use the mean of the aggregate as the base
                aggregate_value = (
                    aggregate_series.mean()
                    if isinstance(aggregate_series, pd.Series)
                    else aggregate_series
                )
                base_value = (
                    self.value * float(aggregate_value) if aggregate_value else 0.0
                )
            else:
                raise KeyError(
                    f"Aggregate reference '{self.reference.value}' not found in resolved lookups for calculation '{self.name}'"
                )
        else:
            raise TypeError(
                f"Unsupported reference type: {type(self.reference)} for calculation '{self.name}'"
            )

        # Apply frequency conversion
        base_value = self._convert_frequency(base_value)

        # Use the raw base_value as total cost (not summed from inflated series)
        total_cost = float(base_value)

        # Apply draw schedule - now much simpler with template method pattern!
        # Defensive check: ensure draw_schedule is not None
        draw_schedule = self.draw_schedule or UniformDrawSchedule()

        cf = draw_schedule.apply_to_amount(
            amount=total_cost,
            periods=self.timeline.duration_months,
            index=self.timeline.period_index,
        )

        # Apply growth if specified (e.g., for inflation)
        if self.growth_rate:
            cf = self._apply_compounding_growth(cf, self.growth_rate)

        return cf


class CapitalPlan(Model):
    """
    Container for coordinated capital projects with factory methods.

    Provides both flexibility (individual item timing) and convenience
    (factory methods for common patterns). Each capital item can have
    its own timeline, allowing complex sequencing when needed.
    """

    name: str
    description: Optional[str] = None
    capital_items: List[CapitalItem] = Field(default_factory=list)
    uid: UUID = Field(default_factory=uuid4)

    @computed_field
    @property
    def total_cost(self) -> float:
        """Total cost across all capital items."""
        return sum(
            item.value if isinstance(item.value, (int, float)) else 0.0
            for item in self.capital_items
        )

    @computed_field
    @property
    def duration_months(self) -> int:
        """Total duration from earliest start to latest end."""
        if not self.capital_items:
            return 0

        earliest_start = min(item.timeline.start_date for item in self.capital_items)
        latest_end = max(item.timeline.end_date for item in self.capital_items)

        # Calculate months between dates
        months = (
            (latest_end.year - earliest_start.year) * 12
            + (latest_end.month - earliest_start.month)
            + 1
        )
        return max(months, 1)

    # === FACTORY METHODS FOR COMMON PATTERNS ===

    @classmethod
    def create_concurrent_renovation(
        cls,
        name: str,
        start_date: Union[date, datetime],
        # FIXME: should we have default values here at all?
        duration_months: int = 2,
        costs: Optional[Dict[str, float]] = None,
        description: Optional[str] = None,
        draw_schedule: Optional[AnyDrawSchedule] = None,
    ) -> "CapitalPlan":
        """
        Create a renovation where all work happens simultaneously.

        Perfect for: Unit turnovers, small projects, budget simplicity.

        Args:
            name: Plan name (e.g., "Unit 201 Renovation")
            start_date: When renovation begins
            duration_months: How long renovation takes (default: 2 months)
            costs: Dict of work types to costs (e.g., {"Flooring": 3000, "Paint": 1200})
            description: Optional description
            draw_schedule: Optional draw schedule (defaults to UniformDrawSchedule)

        Returns:
            CapitalPlan with all items running concurrently

        Example:
            plan = CapitalPlan.create_concurrent_renovation(
                name="Unit 201 Renovation",
                start_date=date(2024, 3, 1),
                costs={"Flooring": 3000, "Paint": 1200, "Appliances": 2500},
                draw_schedule=SCurveDrawSchedule(sigma=1.0)
            )
        """
        if costs is None:
            costs = {"Renovation": 5000.0}  # Default single item

        # Ensure start_date is a date object
        if isinstance(start_date, datetime):
            start_date = start_date.date()

        timeline = Timeline(start_date=start_date, duration_months=duration_months)

        capital_items = []
        for work_type, cost in costs.items():
            item = CapitalItem(
                name=f"{name} - {work_type}",
                work_type=work_type,
                timeline=timeline,  # Same timeline for all items
                value=cost,
                description=f"{work_type} work for {name}",
                draw_schedule=draw_schedule,  # Apply same draw schedule to all items
            )
            capital_items.append(item)

        return cls(
            name=name,
            description=description
            or f"Concurrent renovation with {len(costs)} work types",
            capital_items=capital_items,
        )

    @classmethod
    def create_sequential_renovation(
        cls,
        name: str,
        start_date: Union[date, datetime],
        work_phases: Optional[
            List[Dict[str, Union[str, float, int, AnyDrawSchedule]]]
        ] = None,
        description: Optional[str] = None,
    ) -> "CapitalPlan":
        """
        Create a renovation with sequential work phases.

        Perfect for: Complex renovations, compliance requirements, large projects.

        Args:
            name: Plan name (e.g., "Building Lobby Renovation")
            start_date: When first phase begins
            work_phases: List of dicts with 'work_type', 'cost', 'duration_months',
                        and optional 'draw_schedule'
            description: Optional description

        Returns:
            CapitalPlan with sequential phases

        Example:
            phases = [
                {"work_type": "Demo", "cost": 5000, "duration_months": 1},
                {"work_type": "Construction", "cost": 15000, "duration_months": 3,
                 "draw_schedule": SCurveDrawSchedule(sigma=1.5)},
                {"work_type": "Finishes", "cost": 8000, "duration_months": 2}
            ]
            plan = CapitalPlan.create_sequential_renovation(
                name="Building Lobby Renovation",
                start_date=date(2024, 6, 1),
                work_phases=phases
            )
        """
        if work_phases is None:
            work_phases = [
                {"work_type": "Demo", "cost": 2000.0, "duration_months": 1},
                {"work_type": "Construction", "cost": 8000.0, "duration_months": 2},
                {"work_type": "Finishes", "cost": 3000.0, "duration_months": 1},
            ]

        # Ensure start_date is a date object
        if isinstance(start_date, datetime):
            start_date = start_date.date()

        capital_items = []
        current_start = start_date

        for phase in work_phases:
            work_type = phase["work_type"]
            cost = phase["cost"]
            duration = phase.get("duration_months", 1)
            phase_draw_schedule = phase.get("draw_schedule", None)

            timeline = Timeline(start_date=current_start, duration_months=duration)

            item = CapitalItem(
                name=f"{name} - {work_type}",
                work_type=work_type,
                timeline=timeline,
                value=cost,
                description=f"{work_type} phase for {name}",
                draw_schedule=phase_draw_schedule,  # Phase-specific draw schedule
            )
            capital_items.append(item)

            # Move start date forward for next phase
            # Add duration months to current start
            year = current_start.year
            month = current_start.month + duration
            while month > 12:
                year += 1
                month -= 12
            current_start = date(year, month, 1)

        return cls(
            name=name,
            description=description
            or f"Sequential renovation with {len(work_phases)} phases",
            capital_items=capital_items,
        )

    @classmethod
    def create_staggered_renovation(
        cls,
        name: str,
        start_date: Union[date, datetime],
        unit_count: int,
        cost_per_unit: float,
        # FIXME: should we have default values here at all?
        units_per_wave: int = 5,
        wave_spacing_months: int = 3,
        unit_duration_months: int = 2,
        description: Optional[str] = None,
        draw_schedule: Optional[AnyDrawSchedule] = None,
    ) -> "CapitalPlan":
        """
        Create a renovation program with staggered unit waves.

        Perfect for: Portfolio renovations, maintaining occupancy, managing cash flow.

        Args:
            name: Plan name (e.g., "Portfolio Unit Renovation Program")
            start_date: When first wave begins
            unit_count: Total units to renovate
            cost_per_unit: Renovation cost per unit
            units_per_wave: How many units per wave (default: 5)
            wave_spacing_months: Months between wave starts (default: 3)
            unit_duration_months: How long each unit takes (default: 2)
            description: Optional description
            draw_schedule: Optional draw schedule for each wave

        Returns:
            CapitalPlan with staggered renovation waves

        Example:
            plan = CapitalPlan.create_staggered_renovation(
                name="Portfolio Unit Renovation Program",
                start_date=date(2024, 9, 1),
                unit_count=20,
                cost_per_unit=4500,
                units_per_wave=4,
                wave_spacing_months=2,
                draw_schedule=ManualDrawSchedule(values=[0.3, 0.7])
            )
        """
        # Ensure start_date is a date object
        if isinstance(start_date, datetime):
            start_date = start_date.date()

        capital_items = []
        current_start = start_date
        units_renovated = 0
        wave_number = 1

        while units_renovated < unit_count:
            # Determine units in this wave
            units_in_wave = min(units_per_wave, unit_count - units_renovated)
            wave_cost = units_in_wave * cost_per_unit

            timeline = Timeline(
                start_date=current_start, duration_months=unit_duration_months
            )

            item = CapitalItem(
                name=f"{name} - Wave {wave_number}",
                work_type=f"Unit Renovation Wave {wave_number}",
                timeline=timeline,
                value=wave_cost,
                description=f"Wave {wave_number}: {units_in_wave} units @ ${cost_per_unit:,.0f}/unit",
                draw_schedule=draw_schedule,  # Apply draw schedule to each wave
            )
            capital_items.append(item)

            units_renovated += units_in_wave
            wave_number += 1

            # Move start date forward for next wave
            year = current_start.year
            month = current_start.month + wave_spacing_months
            while month > 12:
                year += 1
                month -= 12
            current_start = date(year, month, 1)

        total_cost = unit_count * cost_per_unit

        return cls(
            name=name,
            description=description
            or f"Staggered renovation: {unit_count} units in {len(capital_items)} waves (${total_cost:,.0f} total)",
            capital_items=capital_items,
        )
