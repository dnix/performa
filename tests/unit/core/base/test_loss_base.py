# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from performa.core.base import (
    CreditLossConfig,
    Losses,
    VacancyLossConfig,
)
from performa.core.primitives import VacancyLossMethodEnum


def test_losses_base_instantiation():
    """Test successful instantiation of Losses and its nested models."""
    losses = Losses()
    assert isinstance(losses.vacancy, VacancyLossConfig)
    assert isinstance(losses.collection, CreditLossConfig)
    assert (
        losses.vacancy.method == VacancyLossMethodEnum.POTENTIAL_GROSS_REVENUE
    )
    assert losses.collection.rate == 0.01
