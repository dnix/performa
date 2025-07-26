# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Smoke tests for AssetAnalyzer specialist service.

These tests validate that the AssetAnalyzer can be instantiated and perform
basic operations without errors.
"""

import pytest
from datetime import date
from unittest.mock import Mock, MagicMock

from src.performa.deal.analysis.asset import AssetAnalyzer
from src.performa.deal.deal import Deal
from src.performa.core.primitives import Timeline, GlobalSettings


class TestAssetAnalyzer:
    """Test suite for AssetAnalyzer specialist service."""
    
    def test_asset_analyzer_can_be_instantiated(self):
        """Test that AssetAnalyzer can be instantiated with basic parameters."""
        # Create minimal mock objects
        deal = Mock(spec=Deal)
        timeline = Mock(spec=Timeline)
        settings = Mock(spec=GlobalSettings)
        
        # Should not raise an exception
        analyzer = AssetAnalyzer(deal=deal, timeline=timeline, settings=settings)
        
        assert analyzer is not None
        assert analyzer.deal == deal
        assert analyzer.timeline == timeline
        assert analyzer.settings == settings
    
    def test_asset_analyzer_has_required_method(self):
        """Test that AssetAnalyzer has the expected public method."""
        deal = Mock(spec=Deal)
        timeline = Mock(spec=Timeline)
        settings = Mock(spec=GlobalSettings)
        
        analyzer = AssetAnalyzer(deal=deal, timeline=timeline, settings=settings)
        
        # Should have the main analysis method
        assert hasattr(analyzer, 'analyze_unlevered_asset')
        assert callable(analyzer.analyze_unlevered_asset)
