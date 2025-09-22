# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Base class for deal pattern implementations.

This module provides the abstract base class for all deal patterns,
integrating deal creation with analysis in a type-safe, validated approach.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional, Tuple

from pydantic import ConfigDict, Field

from ...core.primitives import GlobalSettings, Model, Timeline
from ...deal import Deal
from ...deal.api import analyze as run_analysis
from ...deal.results import DealResults


class PatternBase(Model, ABC):
    """
    Abstract base class for all deal patterns with integrated analysis.

    This class provides a minimal framework for creating type-safe deal patterns
    that can be directly analyzed without requiring separate timeline creation.

    Design Philosophy:
    - Minimal validation at pattern level (delegate to underlying models)
    - Smart timeline defaults derived from business logic
    - Immutable pattern objects (frozen=True from Model)
    - Direct integration with existing analyze() function

    Subclasses must implement:
    - create(): Build the Deal object from pattern parameters
    - _derive_timeline(): Calculate timeline from business parameters
    """

    # Override base Model config to add strict parameter validation for user-facing patterns
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,
        extra="forbid",  # Prevent silent parameter failures in Patterns abstractions
    )

    # Optional timeline overrides for advanced use cases
    # Most users should rely on pattern's hold_period_years for timeline
    analysis_start_date: Optional[date] = Field(
        None,
        description="Override analysis start date (defaults to acquisition/project start)",
    )
    analysis_end_date: Optional[date] = Field(
        None,
        description="Override analysis end date (defaults to hold period + construction/lease-up)",
    )

    # Optional global settings for analysis
    settings: Optional[GlobalSettings] = Field(
        None,
        description="Optional global settings for analysis (uses defaults if not provided)",
    )

    @abstractmethod
    def create(self) -> Deal:
        """
        Create the Deal object from validated pattern parameters.

        This method should assemble all deal components (asset, financing,
        partnership, etc.) using the pattern's parameters.

        Returns:
            Complete Deal object ready for analysis
        """
        pass

    @abstractmethod
    def _derive_timeline(self) -> Timeline:
        """
        Derive timeline from hold_period_years business parameter.

        Unified Timeline Approach:
        - Stabilized patterns: Timeline = acquisition_date to (acquisition_date + hold_period_years)
        - Development patterns: Timeline = acquisition_date to (construction_end + lease_up + hold_period_years)

        This eliminates timeline mismatches by making hold_period_years the single source of truth.
        All exit valuations, analysis periods, and business calculations derive from this.

        Returns:
            Timeline object for analysis based on hold_period_years
        """
        pass

    def get_timeline(self) -> Timeline:
        """
        Get timeline for analysis, using explicit overrides or deriving from hold period.

        Timeline Philosophy:
        - Hold period drives everything (industry standard like Argus/Rockport)
        - Development patterns: hold_period_years = stabilized hold AFTER construction/lease-up
        - Stabilized patterns: hold_period_years = total operating period

        Priority:
        1. If both analysis_start_date and analysis_end_date provided, use them (override)
        2. Otherwise, delegate to pattern-specific _derive_timeline() based on hold_period_years

        Returns:
            Timeline object for analysis
        """
        # Case 1: Both start and end dates provided (advanced override)
        if self.analysis_start_date and self.analysis_end_date:
            return Timeline.from_dates(
                start_date=self.analysis_start_date.strftime("%Y-%m-%d"),
                end_date=self.analysis_end_date.strftime("%Y-%m-%d"),
            )

        # Case 2: Delegate to pattern-specific logic based on hold_period_years
        return self._derive_timeline()

    def analyze(self) -> DealResults:
        """
        Create deal and run analysis with computed timeline.

        This is the primary method users will call to get analysis results
        directly from pattern parameters.

        Returns:
            DealResults with all analysis components

        Example:
            ```python
            pattern = ValueAddAcquisitionPattern(
                property_name="Test Property",
                acquisition_price=10_000_000,
                # ... other parameters
            )
            results = pattern.analyze()
            print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
            ```
        """
        deal = self.create()
        timeline = self.get_timeline()
        settings = self.settings or GlobalSettings()
        return run_analysis(deal, timeline, settings)

    def create_and_analyze(self) -> Tuple[Deal, DealResults]:
        """
        Create deal and analyze, returning both for advanced use cases.

        This method is useful when you need access to both the Deal object
        and the analysis results, for example when doing sensitivity analysis
        or debugging.

        Returns:
            Tuple of (Deal, DealResults)

        Example:
            ```python
            pattern = ValueAddAcquisitionPattern(...)
            deal, results = pattern.create_and_analyze()

            # Can now inspect the deal structure
            print(f"Asset: {deal.asset.name}")
            print(f"Financing: {deal.financing.name}")

            # And use the results
            print(f"IRR: {results.deal_metrics.irr:.2%}")
            ```
        """
        deal = self.create()
        timeline = self.get_timeline()
        settings = self.settings or GlobalSettings()
        results = run_analysis(deal, timeline, settings)
        return deal, results
