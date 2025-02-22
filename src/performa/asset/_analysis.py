from ..core._model import Model
from ._property import Property
from ._settings import GlobalSettings


class CashFlowAnalysis(Model):
    """
    Orchestration layer for a property's cash flow analysis.
    """

    property: Property
    settings: GlobalSettings

    # TODO: add methods for calculating cash flow from revenues and expenses definitions
    # NOTE: be mindful of the order of operations for calculating cash flow and dependency graphs
