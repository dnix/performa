
from ..core._model import Model


class LossItem(Model):
    """
    A loss event.
    """
    ...

class VacancyLoss(LossItem):
    """
    A vacancy loss event.
    """
    ...

class CreditLoss(LossItem):
    """
    A credit loss event.
    """
    ...


class Losses(Model):
    """
    Collection of property losses.
    """
    vacancy_loss: VacancyLoss
    credit_loss: CreditLoss
