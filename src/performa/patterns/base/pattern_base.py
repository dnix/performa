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
from ...core.primitives.types import PositiveInt
from ...deal import Deal
from ...deal.api import analyze as run_analysis
from ...deal.results import DealAnalysisResult


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

    # Optional timeline parameters for explicit control
    analysis_start_date: Optional[date] = Field(
        None, description="Analysis start date (defaults to acquisition/project start)"
    )
    analysis_duration_months: Optional[PositiveInt] = Field(
        None,
        ge=1,
        le=600,
        description="Analysis duration in months (defaults to hold period + buffer)",
    )
    analysis_end_date: Optional[date] = Field(
        None, description="Analysis end date (alternative to duration_months)"
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
        Derive timeline from pattern-specific business parameters.

        This method is called when explicit timeline parameters are not provided.
        Subclasses should implement logic to derive sensible defaults based on
        their business parameters (e.g., acquisition date + hold period).

        Returns:
            Timeline object for analysis
        """
        pass

    def get_timeline(self) -> Timeline:
        """
        Get timeline for analysis, using explicit parameters or deriving from business logic.

        Priority:
        1. If both analysis_start_date and analysis_end_date provided, use them
        2. If analysis_start_date and analysis_duration_months provided, calculate end
        3. Otherwise, delegate to pattern-specific _derive_timeline()

        Returns:
            Timeline object for analysis
        """
        # Case 1: Both start and end dates provided
        if self.analysis_start_date and self.analysis_end_date:
            return Timeline.from_dates(
                start_date=self.analysis_start_date.strftime("%Y-%m-%d"),
                end_date=self.analysis_end_date.strftime("%Y-%m-%d"),
            )

        # Case 2: Start date and duration provided
        if self.analysis_start_date and self.analysis_duration_months:
            return Timeline(
                start_date=self.analysis_start_date,
                duration_months=self.analysis_duration_months,
            )

        # Case 3: Delegate to pattern-specific logic
        return self._derive_timeline()

    def analyze(self) -> DealAnalysisResult:
        """
        Create deal and run analysis with computed timeline.

        This is the primary method users will call to get analysis results
        directly from pattern parameters.

        Returns:
            DealAnalysisResult with all analysis components

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

    def create_and_analyze(self) -> Tuple[Deal, DealAnalysisResult]:
        """
        Create deal and analyze, returning both for advanced use cases.

        This method is useful when you need access to both the Deal object
        and the analysis results, for example when doing sensitivity analysis
        or debugging.

        Returns:
            Tuple of (Deal, DealAnalysisResult)

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
