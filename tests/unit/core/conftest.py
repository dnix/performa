# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from performa.analysis import AnalysisContext
from performa.asset.office import OfficeProperty
from performa.core.primitives import GlobalSettings, Timeline


@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline(start_date=date(2024, 1, 1), duration_months=120)


@pytest.fixture
def sample_context(sample_timeline: Timeline) -> AnalysisContext:
    # A basic factory fixture that can be customized in tests if needed
    def _create_context(
        timeline_duration: int = 120, property_data: OfficeProperty = None
    ):
        timeline = Timeline(
            start_date=date(2024, 1, 1), duration_months=timeline_duration
        )
        return AnalysisContext(
            timeline=timeline,
            settings=GlobalSettings(),
            property_data=property_data,  # Can be None for base tests
            resolved_lookups={},
        )

    return _create_context 