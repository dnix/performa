# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import PrivateAttr

from performa.core.ledger import LedgerBuilder
from performa.core.primitives import CashFlowModel, GlobalSettings, Model, Timeline

from .orchestrator import AnalysisContext, CashFlowOrchestrator


class AnalysisScenarioBase(Model, ABC):
    model: Model
    settings: GlobalSettings
    timeline: Timeline
    ledger_builder: LedgerBuilder

    _orchestrator: Optional[CashFlowOrchestrator] = PrivateAttr(default=None)

    @abstractmethod
    def prepare_models(self) -> List[CashFlowModel]:
        pass

    def run(self) -> None:
        # 1. PREPARE: Call the concrete implementation
        all_models = self.prepare_models()

        # 2. CREATE CONTEXT: Create the mutable state packet with builder
        # The scenario can populate pre-calculated state here
        recovery_states = getattr(self, "_recovery_states", {})

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=self.model,
            recovery_states=recovery_states,
            ledger_builder=self.ledger_builder,
        )

        # 3. EXECUTE: Create and run the service object
        orchestrator = CashFlowOrchestrator(models=all_models, context=context)
        orchestrator.execute()

        # 4. STORE RESULT: Store the stateful orchestrator object
        self._orchestrator = orchestrator
