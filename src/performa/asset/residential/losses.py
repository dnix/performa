# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import Field

from ...core.base import (
    CollectionLossConfigBase,
    GeneralVacancyLossConfigBase,
    LossesBase,
)


class ResidentialGeneralVacancyLoss(GeneralVacancyLossConfigBase):
    """
    Residential-specific configuration for general vacancy loss.

    Typically applied as a percentage of potential gross income in
    multifamily properties to account for turnover and downtime.
    """

    pass


class ResidentialCollectionLoss(CollectionLossConfigBase):
    """
    Residential-specific configuration for collection loss.

    Accounts for uncollectable rent and bad debt in residential properties.
    Often lower than commercial properties due to shorter lease terms and
    more liquid tenant markets.
    """

    pass


class ResidentialLosses(LossesBase):
    """
    Container for residential property-level loss configurations.
    """

    uid: UUID = Field(
        default_factory=uuid4, description="Unique identifier for this losses container"
    )
    general_vacancy: ResidentialGeneralVacancyLoss
    collection_loss: ResidentialCollectionLoss
