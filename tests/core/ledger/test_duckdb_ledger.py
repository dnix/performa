# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the DuckDB-based ledger implementation.

This module tests the new high-performance DuckDB ledger to ensure API compatibility
and functional parity with the original pandas-based implementation.
"""

import uuid

import pandas as pd

from performa.core.ledger import Ledger
from performa.core.ledger.records import SeriesMetadata
from performa.core.primitives.enums import (
    CashFlowCategoryEnum,
    RevenueSubcategoryEnum,
)


class TestLedger:
    """Test suite for DuckDB-based ledger implementation."""

    def test_initialization(self):
        """Test that DuckDB ledger initializes correctly."""
        ledger = Ledger()
        
        assert len(ledger) == 0
        assert ledger.record_count() == 0
        assert ledger.series_count() == 0
        
        # Test that connection works
        con, table_name = ledger.get_query_connection()
        assert con is not None
        assert table_name == "transactions"

    def test_add_series_basic(self):
        """Test adding a basic series to the ledger."""
        ledger = Ledger()
        
        # Create test series
        dates = pd.date_range("2024-01-01", periods=3, freq="M")
        series = pd.Series([1000.0, 2000.0, 3000.0], index=dates)
        
        # Create metadata
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        # Add series
        ledger.add_series(series, metadata)
        
        # Verify counts
        assert len(ledger) == 3
        assert ledger.record_count() == 3
        assert ledger.series_count() == 1

    def test_add_series_with_period_index(self):
        """Test adding series with PeriodIndex (should convert automatically)."""
        ledger = Ledger()
        
        # Create test series with PeriodIndex
        periods = pd.period_range("2024-01", periods=3, freq="M")
        series = pd.Series([1000.0, 2000.0, 3000.0], index=periods)
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        # Should not raise an error
        ledger.add_series(series, metadata)
        assert len(ledger) == 3

    def test_add_series_filters_zeros(self):
        """Test that zero values are filtered out."""
        ledger = Ledger()
        
        dates = pd.date_range("2024-01-01", periods=5, freq="M")
        series = pd.Series([1000.0, 0.0, 2000.0, 0.0, 3000.0], index=dates)
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        ledger.add_series(series, metadata)
        
        # Should only have 3 non-zero transactions
        assert len(ledger) == 3

    def test_to_dataframe_basic(self):
        """Test DataFrame materialization."""
        ledger = Ledger()
        
        dates = pd.date_range("2024-01-01", periods=3, freq="M")
        series = pd.Series([1000.0, 2000.0, 3000.0], index=dates)
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        ledger.add_series(series, metadata)
        
        # Test DataFrame materialization
        df = ledger.to_dataframe()
        
        assert len(df) == 3
        assert "transaction_id" in df.columns
        assert "date" in df.columns
        assert "amount" in df.columns
        assert "flow_purpose" in df.columns
        assert "category" in df.columns
        assert "subcategory" in df.columns
        assert "item_name" in df.columns
        
        # Verify data integrity
        assert df["amount"].sum() == 6000.0
        assert df["item_name"].iloc[0] == "Base Rent"
        assert df["flow_purpose"].iloc[0] == "Operating"

    def test_ledger_df_compatibility(self):
        """Test that ledger_df() method works for API compatibility."""
        ledger = Ledger()
        
        dates = pd.date_range("2024-01-01", periods=2, freq="M")
        series = pd.Series([1000.0, 2000.0], index=dates)
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        ledger.add_series(series, metadata)
        
        # Test API compatibility method
        df = ledger.ledger_df()
        assert len(df) == 2
        assert df["amount"].sum() == 3000.0

    def test_clear(self):
        """Test clearing the ledger."""
        ledger = Ledger()
        
        dates = pd.date_range("2024-01-01", periods=2, freq="M")
        series = pd.Series([1000.0, 2000.0], index=dates)
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        ledger.add_series(series, metadata)
        assert len(ledger) == 2
        
        ledger.clear()
        assert len(ledger) == 0
        assert ledger.record_count() == 0

    def test_empty_series_handling(self):
        """Test that empty or None series are handled gracefully."""
        ledger = Ledger()
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        # Test None series
        ledger.add_series(None, metadata)
        assert len(ledger) == 0
        
        # Test empty series
        empty_series = pd.Series([], dtype=float)
        ledger.add_series(empty_series, metadata)
        assert len(ledger) == 0
        
        # Test all-zero series
        dates = pd.date_range("2024-01-01", periods=3, freq="M")
        zero_series = pd.Series([0.0, 0.0, 0.0], index=dates)
        ledger.add_series(zero_series, metadata)
        assert len(ledger) == 0

    def test_get_query_connection(self):
        """Test that query connection interface works."""
        ledger = Ledger()
        
        con, table_name = ledger.get_query_connection()
        
        # Test that we can execute a query
        result = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        assert result == 0
        
        # Add some data and test again
        dates = pd.date_range("2024-01-01", periods=2, freq="M")
        series = pd.Series([1000.0, 2000.0], index=dates)
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        ledger.add_series(series, metadata)
        
        result = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        assert result == 2

    def test_add_series_batch(self):
        """Test adding multiple series at once."""
        ledger = Ledger()
        
        # Create multiple series
        dates = pd.date_range("2024-01-01", periods=2, freq="M")
        series1 = pd.Series([1000.0, 2000.0], index=dates)
        series2 = pd.Series([500.0, 1500.0], index=dates)
        
        metadata1 = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Base Rent",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        metadata2 = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Parking Revenue",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )
        
        pairs = [(series1, metadata1), (series2, metadata2)]
        ledger.add_series_batch(pairs)
        
        assert len(ledger) == 4
        assert ledger.series_count() == 2
