from __future__ import annotations

from typing import TYPE_CHECKING

from ..common.primitives._model import Model

if TYPE_CHECKING:
    from ..common.base._property_base import PropertyBaseModel


class AssetAnalysisWrapper(Model):
    """
    User-facing wrapper to orchestrate asset-level cash flow analysis.
    """

    property: "PropertyBaseModel"

    def run(self):
        # This will orchestrate the analysis using CashFlowOrchestrator
        pass

    def create_cash_flow_dataframe(self):
        # This will return the aggregated cash flow dataframe
        pass 