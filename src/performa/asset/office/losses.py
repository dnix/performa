from __future__ import annotations

from ...common.base import (
    CollectionLossConfigBase,
    GeneralVacancyLossConfigBase,
    LossesBase,
)


class OfficeGeneralVacancyLoss(GeneralVacancyLossConfigBase):
    """
    Office-specific configuration for General Vacancy Loss.
    """
    pass

class OfficeCollectionLoss(CollectionLossConfigBase):
    """
    Office-specific configuration for Collection Loss.
    """
    pass

class OfficeLosses(LossesBase):
    """
    Office-specific container for property-level loss configurations.
    """
    general_vacancy: OfficeGeneralVacancyLoss
    collection_loss: OfficeCollectionLoss 