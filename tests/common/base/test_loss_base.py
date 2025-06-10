from __future__ import annotations

import pytest

from performa.common.base._loss_base import (
    CollectionLossConfigBase,
    GeneralVacancyLossConfigBase,
    LossesBase,
)
from performa.common.primitives import VacancyLossMethodEnum


def test_losses_base_instantiation():
    """Test successful instantiation of LossesBase and its nested models."""
    losses = LossesBase()
    assert isinstance(losses.general_vacancy, GeneralVacancyLossConfigBase)
    assert isinstance(losses.collection_loss, CollectionLossConfigBase)
    assert losses.general_vacancy.method == VacancyLossMethodEnum.POTENTIAL_GROSS_REVENUE
    assert losses.collection_loss.rate == 0.01
