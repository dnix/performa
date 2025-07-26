# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

import pandas as pd
from pydantic import PrivateAttr

from performa.core.primitives import CashFlowModel, GlobalSettings, Model, Timeline

from .orchestrator import AnalysisContext, CashFlowOrchestrator


class AnalysisScenarioBase(Model, ABC):
    model: Model
    settings: GlobalSettings
    timeline: Timeline
    
    _orchestrator: Optional[CashFlowOrchestrator] = PrivateAttr(default=None)

    @abstractmethod
    def prepare_models(self) -> List[CashFlowModel]:
        pass

    def run(self) -> None:
        # 1. PREPARE: Call the concrete implementation
        all_models = self.prepare_models()
        
        # 2. CREATE CONTEXT: Create the mutable state packet
        # The scenario can populate pre-calculated state here
        recovery_states = getattr(self, '_recovery_states', {})
        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=self.model,
            recovery_states=recovery_states
        )
        
        # 3. EXECUTE: Create and run the service object
        orchestrator = CashFlowOrchestrator(models=all_models, context=context)
        orchestrator.execute()
        
        # 4. STORE RESULT: Store the stateful orchestrator object
        self._orchestrator = orchestrator

    def get_cash_flow_summary(self) -> pd.DataFrame:
        if not self._orchestrator or self._orchestrator.summary_df is None:
            raise RuntimeError("Analysis has not been run. Call .run() first.")
        return self._orchestrator.summary_df
