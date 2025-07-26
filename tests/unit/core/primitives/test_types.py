# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from performa.core.primitives import FloatBetween0And1, PositiveFloat, PositiveInt

# Use TypeAdapter for testing Pydantic constrained types
positive_int_adapter = TypeAdapter(PositiveInt)
positive_float_adapter = TypeAdapter(PositiveFloat)
float_01_adapter = TypeAdapter(FloatBetween0And1)

# PositiveInt
def test_positive_int_valid():
    assert positive_int_adapter.validate_python(0) == 0
    assert positive_int_adapter.validate_python(100) == 100

def test_positive_int_invalid():
    with pytest.raises(ValidationError):
        positive_int_adapter.validate_python(-1)
    with pytest.raises(ValidationError):
        positive_int_adapter.validate_python(1.5) # strict=True fails on float
    with pytest.raises(ValidationError):
        positive_int_adapter.validate_python("1") # strict=True fails on string

# PositiveFloat
def test_positive_float_valid():
    assert positive_float_adapter.validate_python(0.0) == 0.0
    assert positive_float_adapter.validate_python(123.45) == 123.45

def test_positive_float_invalid():
    with pytest.raises(ValidationError):
        positive_float_adapter.validate_python(-0.001)
    with pytest.raises(ValidationError):
        positive_float_adapter.validate_python("1.5") # strict=True fails on string

# FloatBetween0And1
def test_float_01_valid():
    assert float_01_adapter.validate_python(0.0) == 0.0
    assert float_01_adapter.validate_python(1.0) == 1.0
    assert float_01_adapter.validate_python(0.5) == 0.5

def test_float_01_invalid():
    with pytest.raises(ValidationError):
        float_01_adapter.validate_python(-0.01)
    with pytest.raises(ValidationError):
        float_01_adapter.validate_python(1.01)
    with pytest.raises(ValidationError):
        float_01_adapter.validate_python("0.5") # strict=True fails on string
