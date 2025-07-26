# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Smoke tests for ValuationEngine specialist service.
"""

import pytest
from unittest.mock import Mock

from src.performa.deal.analysis.valuation import ValuationEngine
from src.performa.deal.deal import Deal
from src.performa.core.primitives import Timeline, GlobalSettings


class TestValuationEngine:
    """Test suite for ValuationEngine specialist service."""
    
    def test_valuation_engine_can_be_instantiated(self):
        """Test that ValuationEngine can be instantiated with basic parameters."""
        deal = Mock(spec=Deal)
        timeline = Mock(spec=Timeline)
        settings = Mock(spec=GlobalSettings)
        
        engine = ValuationEngine(deal=deal, timeline=timeline, settings=settings)
        
        assert engine is not None
        assert engine.deal == deal
        assert engine.timeline == timeline
        assert engine.settings == settings
    
    def test_valuation_engine_has_required_methods(self):
        """Test that ValuationEngine has the expected public methods."""
        deal = Mock(spec=Deal)
        timeline = Mock(spec=Timeline)
        settings = Mock(spec=GlobalSettings)
        
        engine = ValuationEngine(deal=deal, timeline=timeline, settings=settings)
        
        # Check for expected methods
        assert hasattr(engine, 'extract_property_value_series')
        assert callable(engine.extract_property_value_series)
        assert hasattr(engine, 'extract_noi_series')
        assert callable(engine.extract_noi_series)
        assert hasattr(engine, 'calculate_disposition_proceeds')
        assert callable(engine.calculate_disposition_proceeds)
