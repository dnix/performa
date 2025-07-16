"""
Smoke tests for DebtAnalyzer specialist service.
"""

import pytest
from unittest.mock import Mock

from src.performa.deal.analysis.debt import DebtAnalyzer
from src.performa.deal.deal import Deal
from src.performa.core.primitives import Timeline, GlobalSettings


class TestDebtAnalyzer:
    """Test suite for DebtAnalyzer specialist service."""
    
    def test_debt_analyzer_can_be_instantiated(self):
        """Test that DebtAnalyzer can be instantiated with basic parameters."""
        deal = Mock(spec=Deal)
        timeline = Mock(spec=Timeline)
        settings = Mock(spec=GlobalSettings)
        
        analyzer = DebtAnalyzer(deal=deal, timeline=timeline, settings=settings)
        
        assert analyzer is not None
        assert analyzer.deal == deal
        assert analyzer.timeline == timeline
        assert analyzer.settings == settings
    
    def test_debt_analyzer_has_required_methods(self):
        """Test that DebtAnalyzer has the expected public methods."""
        deal = Mock(spec=Deal)
        timeline = Mock(spec=Timeline)
        settings = Mock(spec=GlobalSettings)
        
        analyzer = DebtAnalyzer(deal=deal, timeline=timeline, settings=settings)
        
        # Check for expected methods
        assert hasattr(analyzer, 'analyze_financing_structure')
        assert callable(analyzer.analyze_financing_structure)
        assert hasattr(analyzer, 'calculate_dscr_metrics')
        assert callable(analyzer.calculate_dscr_metrics)
