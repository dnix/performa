# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import pytest
from pydantic import ValidationError

from performa.core.primitives import Model


class _TestModel(Model):
    a: int
    b: str = "hello"


def test_model_is_frozen():
    """Test that the base Model is frozen and attributes cannot be changed after instantiation."""
    m = _TestModel(a=1)
    with pytest.raises(ValidationError):
        m.a = 2


def test_model_copy_no_updates():
    """Test the copy() method without any updates."""
    m1 = _TestModel(a=1, b="original")
    m2 = m1.copy()

    assert m1 == m2
    assert m1 is not m2
    assert m1.a == m2.a
    assert m1.b == m2.b


def test_model_copy_with_updates():
    """Test the copy() method with updates."""
    m1 = _TestModel(a=1, b="original")
    m2 = m1.model_copy(update={"a": 100, "b": "updated"})

    assert m1 != m2
    assert m2.a == 100
    assert m2.b == "updated"


def test_model_copy_with_partial_updates():
    """Test the copy() method with partial updates."""
    m1 = _TestModel(a=1, b="original")
    m2 = m1.model_copy(update={"a": 100})

    assert m1 != m2
    assert m2.a == 100
    assert m2.b == "original"
