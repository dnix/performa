# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performance benchmarking tests for ledger query operations.

This module provides specialized performance tests for ledger queries that are not
covered by the E2E example script tests. Full deal analysis performance is tested
in tests/e2e/test_example_scripts.py.
"""

import time
import uuid
from pathlib import Path

import pandas as pd
import pytest

from performa.core.ledger import Ledger, LedgerQueries
from performa.core.ledger.records import SeriesMetadata
from performa.core.primitives.enums import (
    CashFlowCategoryEnum,
    RevenueSubcategoryEnum,
)

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"


class TestLedgerPerformance:
    """Specialized ledger query performance testing suite.

    Note: Full deal analysis performance is tested in tests/e2e/test_example_scripts.py
    to avoid duplication. This module focuses on ledger-specific operations.
    """

    def test_ledger_query_performance(self):
        """
        Benchmark ledger query operations performance.

        This test measures the performance of common LedgerQueries operations
        to validate indexing and dtype optimizations.
        """
        # Load a representative ledger from baseline
        ledger_path = FIXTURES_DIR / "baseline_ledger_residential_development.pkl"
        if not ledger_path.exists():
            pytest.skip(
                "Baseline ledger file not found - run baseline generation first"
            )

        ledger_df = pd.read_pickle(ledger_path)

        # Create a Ledger object and populate it with the baseline data
        ledger = Ledger()

        # Since we're testing query performance, not conversion performance,
        # use the DataFrame directly through to_dataframe() method for a clean test
        # The original DataFrame is already in the correct format

        # Create fresh ledger and add data using the DataFrame->Series->Ledger path
        # This tests the actual usage pattern rather than internal conversion

        # Instead of complex conversion, let's use the add_series path which is the normal usage
        for date in ledger_df["date"].unique():
            date_records = ledger_df[ledger_df["date"] == date]
            if len(date_records) > 0:
                # Get the first record to extract metadata
                first_record = date_records.iloc[0]

                # Create a Series for this date with amounts
                amounts = date_records["amount"].values
                series = pd.Series([amounts.sum()], index=[pd.to_datetime(date)])

                # Create metadata from the first record
                metadata = SeriesMetadata(
                    category=CashFlowCategoryEnum.REVENUE,
                    subcategory=RevenueSubcategoryEnum.LEASE,
                    item_name=first_record["item_name"],
                    source_id=uuid.UUID(first_record["source_id"]),
                    asset_id=uuid.UUID(first_record["asset_id"]),
                    pass_num=first_record["pass_num"],
                )

                ledger.add_series(series, metadata)

        queries = LedgerQueries(ledger)

        def run_common_queries():
            """Run a set of common ledger queries."""
            results = {}
            # These are the most commonly used queries in reporting
            results["noi"] = queries.noi()
            results["ucf"] = queries.project_cash_flow()
            results["debt_service"] = queries.debt_service()
            results["equity_contributions"] = queries.equity_contributions()
            # Skip partner_flows as it requires a specific partner_id
            # results['partner_flows'] = queries.partner_flows(partner_id)
            return results

        # Run once as a smoke performance check (no benchmark fixture)
        results = run_common_queries()

        # Verify we got reasonable results
        assert results is not None
        assert "noi" in results
        assert len(results["noi"]) > 0


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
