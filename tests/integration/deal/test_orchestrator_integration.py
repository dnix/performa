# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for DealCalculator orchestrator delegation patterns.

These tests validate that the orchestrator correctly delegates to specialist services
and that the data flow between services works as expected.
"""

from unittest.mock import Mock

from src.performa.core.primitives import GlobalSettings, Timeline
from src.performa.deal.deal import Deal
from src.performa.deal.orchestrator import DealCalculator


class TestOrchestratorIntegration:
    """Test suite for orchestrator integration patterns."""
    
    def test_orchestrator_can_be_instantiated(self):
        """Test that DealCalculator can be instantiated with basic parameters."""
        deal = Mock(spec=Deal)
        timeline = Mock(spec=Timeline)
        settings = Mock(spec=GlobalSettings)
        
        calculator = DealCalculator(deal=deal, timeline=timeline, settings=settings)
        
        assert calculator is not None
        assert calculator.deal == deal
        assert calculator.timeline == timeline
        assert calculator.settings == settings
    
