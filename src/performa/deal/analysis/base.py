# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""Base class for all analysis specialists."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from performa.core.ledger.queries import LedgerQueries

if TYPE_CHECKING:
    from performa.core.ledger import Ledger
    from performa.core.primitives import GlobalSettings, Timeline
    from performa.deal import Deal, DealContext


@dataclass
class AnalysisSpecialist(ABC):
    """Base class for all analysis specialists.

    Provides common properties and initialization for all specialists.
    Subclasses must implement the process() method.
    """

    context: "DealContext"
    _queries: LedgerQueries = field(init=False)

    def __post_init__(self):
        """Set up common resources."""
        self._queries = LedgerQueries(self.context.ledger.ledger_df())
        # Allow subclasses to add additional setup
        self._post_init_hook()

    def _post_init_hook(self):
        """Override in subclasses for additional setup."""
        pass

    @property
    def deal(self) -> "Deal":
        """Access to deal from context."""
        return self.context.deal

    @property
    def timeline(self) -> "Timeline":
        """Access to timeline from context."""
        return self.context.timeline

    @property
    def settings(self) -> "GlobalSettings":
        """Access to settings from context."""
        return self.context.settings

    @property
    def ledger(self) -> "Ledger":
        """Access to ledger from context."""
        return self.context.ledger

    @property
    def queries(self) -> "LedgerQueries":
        """Access to ledger queries."""
        return self._queries

    @abstractmethod
    def process(self) -> None:
        """Process the analysis.

        Must be implemented by all subclasses.
        Updates the context with results as needed.
        """
        pass
