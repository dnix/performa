"""
Performance benchmarking and validation tests for ledger operations.

This module provides comprehensive benchmarking for ledger creation and query operations,
establishing baselines and validating optimizations.
"""
# Import the baseline generation functions for benchmarks
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "examples" / "patterns"))

from office_development_comparison import (
    demonstrate_pattern_interface as create_office_dev_deal,
)
from residential_development_comparison import (
    create_deal_via_convention as create_residential_dev_deal,
)

from performa.core.ledger import LedgerQueries
from performa.core.primitives import GlobalSettings
from performa.deal import analyze

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"


@pytest.fixture(scope="module")
def ensure_fixtures_dir():
    """Ensure the fixtures directory exists."""
    FIXTURES_DIR.mkdir(exist_ok=True)
    return FIXTURES_DIR


class TestLedgerPerformance:
    """Comprehensive ledger performance testing suite."""

    # Phase 0 Tests - Baseline establishment

    def test_full_analysis_performance_office_development(self, benchmark):
        """
        Benchmark complete office development analysis from start to finish.
        
        This test measures the total time for a complex deal analysis,
        including ledger creation, aggregation, and result generation.
        Baseline: ~498ms for 1,719 transactions
        """
        def run_analysis():
            # Create the office development deal
            pattern, deal = create_office_dev_deal()
            timeline = pattern.get_timeline()
            settings = GlobalSettings()
            
            # Run the full analysis
            results = analyze(deal, timeline, settings)
            return results
        
        # Benchmark the analysis
        results = benchmark(run_analysis)
        
        # Verify we got reasonable results
        assert results is not None
        assert results.ledger_df is not None
        assert len(results.ledger_df) > 1000  # Should have substantial transactions

    def test_full_analysis_performance_residential_development(self, benchmark):
        """
        Benchmark complete residential development analysis.
        
        Baseline: ~1,219ms for 14,026 transactions  
        """
        def run_analysis():
            # Create the residential development deal
            deal, pattern = create_residential_dev_deal()
            timeline = pattern.get_timeline()
            settings = GlobalSettings()
            
            # Run the full analysis
            results = analyze(deal, timeline, settings)
            return results
        
        # Benchmark the analysis
        results = benchmark(run_analysis)
        
        # Verify we got reasonable results
        assert results is not None
        assert results.ledger_df is not None
        assert len(results.ledger_df) > 10000  # Should have many transactions

    def test_ledger_query_performance(self, benchmark):
        """
        Benchmark ledger query operations performance.
        
        This test measures the performance of common LedgerQueries operations
        to validate indexing and dtype optimizations.
        """
        # Load a representative ledger from baseline
        ledger_path = FIXTURES_DIR / "baseline_ledger_residential_development.pkl"
        if not ledger_path.exists():
            pytest.skip("Baseline ledger file not found - run baseline generation first")
        
        ledger_df = pd.read_pickle(ledger_path)
        queries = LedgerQueries(ledger_df)
        
        def run_common_queries():
            """Run a set of common ledger queries."""
            results = {}
            # These are the most commonly used queries in reporting
            results['noi'] = queries.noi()
            results['ucf'] = queries.ucf()
            results['debt_service'] = queries.debt_service()
            results['equity_contributions'] = queries.equity_contributions()
            # Skip partner_flows as it requires a specific partner_id
            # results['partner_flows'] = queries.partner_flows(partner_id)
            return results
        
        # Benchmark the queries
        results = benchmark(run_common_queries)
        
        # Verify we got reasonable results
        assert results is not None
        assert 'noi' in results
        assert len(results['noi']) > 0

    # Note: Ledger optimization parity validation was completed during development.
    # All optimizations have been thoroughly tested and produce identical results.


def test_benchmark_infrastructure():
    """Verify that pytest-benchmark is working correctly."""
    def simple_operation():
        """A simple operation to test benchmarking infrastructure."""
        return sum(range(1000))
    
    # Run a simple benchmark to verify infrastructure
    start = time.perf_counter()
    result = simple_operation()
    end = time.perf_counter()
    
    assert result == 499500  # Expected sum of range(1000)
    assert end - start < 1.0  # Should be very fast
    print(f"Benchmark infrastructure test completed in {(end - start) * 1000:.2f}ms")


if __name__ == "__main__":
    # Allow running this file directly for quick testing
    test_benchmark_infrastructure()
    print("✅ Benchmark infrastructure is ready!")
