# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from performa.core.base import ProgramComponentSpec
from performa.core.primitives import ProgramUseEnum


def test_program_component_spec_instantiation():
    """Test successful instantiation of ProgramComponentSpec."""
    spec = ProgramComponentSpec(
        program_use=ProgramUseEnum.RETAIL,
        area=25000,
        identifier="Retail Podium"
    )
    assert spec.program_use == ProgramUseEnum.RETAIL
    assert spec.area == 25000
