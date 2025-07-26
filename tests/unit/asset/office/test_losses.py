# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from performa.asset.office.losses import (
    OfficeCollectionLoss,
    OfficeGeneralVacancyLoss,
    OfficeLosses,
)


def test_office_losses_creation():
    losses = OfficeLosses(
        general_vacancy=OfficeGeneralVacancyLoss(rate=0.05),
        collection_loss=OfficeCollectionLoss(rate=0.01)
    )
    assert losses.general_vacancy.rate == 0.05
    assert losses.collection_loss.rate == 0.01
