# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for ledger transaction batching functionality.

This test module verifies that both pandas and DuckDB ledgers properly
implement transaction-based batching for performance optimization.
"""

import uuid
from unittest.mock import patch

import pandas as pd
import pytest

from performa.core.ledger import Ledger
from performa.core.ledger.records import SeriesMetadata, TransactionRecord
from performa.core.primitives.enums import CashFlowCategoryEnum, RevenueSubcategoryEnum


class TestLedgerTransactionBatching:
    """Test transaction batching for pandas Ledger."""

    @pytest.fixture
    def ledger(self):
        """Create a fresh ledger instance for each test."""
        return Ledger()

    @pytest.fixture
    def sample_metadata(self):
        """Create sample metadata for testing."""
        return SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Test Item",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )

    @pytest.fixture
    def sample_series(self):
        """Create sample series for testing."""
        dates = pd.date_range("2024-01-01", periods=12, freq="M")
        return pd.Series([1000] * 12, index=dates)

    @pytest.fixture
    def sample_records(self):
        """Create sample TransactionRecord instances."""
        return [
            TransactionRecord(
                transaction_id=str(uuid.uuid4()),
                date=pd.Timestamp("2024-01-01").date(),
                amount=1000.0,
                flow_purpose="Operating",
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.LEASE,
                item_name="Test Record",
                source_id=uuid.uuid4(),
                asset_id=uuid.uuid4(),
                pass_num=1,
                deal_id=None,
                entity_id=None,
                entity_type=None,
            ),
            TransactionRecord(
                transaction_id=str(uuid.uuid4()),
                date=pd.Timestamp("2024-02-01").date(),
                amount=1100.0,
                flow_purpose="Operating",
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.LEASE,
                item_name="Test Record 2",
                source_id=uuid.uuid4(),
                asset_id=uuid.uuid4(),
                pass_num=1,
                deal_id=None,
                entity_id=None,
                entity_type=None,
            ),
        ]

    def test_transaction_context_manager_lifecycle(self, ledger):
        """Test that transaction context manager properly manages state."""
        # Initial state
        assert not ledger._in_transaction
        assert len(ledger._transaction_buffer) == 0

        # Enter transaction context
        with ledger.transaction() as txn_ledger:
            assert ledger._in_transaction
            assert txn_ledger is ledger  # Should return the same ledger

        # Exit context - transaction should be complete
        assert not ledger._in_transaction
        assert len(ledger._transaction_buffer) == 0

    def test_buffer_accumulation(
        self, ledger, sample_series, sample_metadata, sample_records
    ):
        """Test that operations accumulate in the buffer during transactions."""
        with ledger.transaction():
            # Add series
            ledger.add_series(sample_series, sample_metadata)

            # Add records
            ledger.add_records(sample_records)

            # Verify operations are buffered, not immediately committed
            assert len(ledger._transaction_buffer) > 0
            assert len(ledger) == 0  # Not yet committed to main database
            # Buffer contains records but main ledger is empty until commit

    def test_flush_behavior(self, ledger, sample_series, sample_metadata):
        """Test flush() behavior during transactions."""
        with ledger.transaction():
            # Add some data
            ledger.add_series(sample_series, sample_metadata)

            # Verify it's buffered
            assert ledger.has_buffered_data()
            assert len(ledger) == 0

            # Flush mid-transaction
            ledger.flush()

            # Verify buffer is committed
            assert not ledger.has_buffered_data()
            assert len(ledger) > 0

            # Add more data after flush
            ledger.add_series(sample_series, sample_metadata)
            assert ledger.has_buffered_data()

        # Final commit on context exit
        assert not ledger.has_buffered_data()

    def test_auto_commit_on_context_exit(self, ledger, sample_series, sample_metadata):
        """Test that operations are automatically committed on successful context exit."""
        initial_record_count = len(ledger)

        with ledger.transaction():
            ledger.add_series(sample_series, sample_metadata)
            # Operations should be in buffer
            assert ledger.has_buffered_data()

        # After context exit, operations should be committed
        assert not ledger.has_buffered_data()
        assert len(ledger) > initial_record_count

    def test_error_handling_and_rollback(self, ledger, sample_series, sample_metadata):
        """Test that buffer is cleared on exception without committing."""
        initial_record_count = len(ledger)

        with pytest.raises(ValueError):
            with ledger.transaction():
                ledger.add_series(sample_series, sample_metadata)
                # Verify operations are buffered
                assert ledger.has_buffered_data()
                # Force an exception
                raise ValueError("Test exception")

        # After exception, buffer should be cleared and no commit should occur
        assert not ledger.has_buffered_data()
        assert len(ledger) == initial_record_count
        assert not ledger._in_transaction

    def test_nested_transaction_prevention(self, ledger):
        """Test that nested transactions are properly prevented."""
        with ledger.transaction():
            assert ledger._in_transaction

            # Attempting nested transaction should raise error
            with pytest.raises(
                RuntimeError, match="Nested transactions are not supported"
            ):
                with ledger.transaction():
                    pass

    def test_flush_outside_transaction_raises_error(self, ledger):
        """Test that flush() raises error when called outside transaction context."""
        assert not ledger._in_transaction

        with pytest.raises(
            RuntimeError,
            match="flush\\(\\) can only be called within a transaction context",
        ):
            ledger.flush()

    def test_backward_compatibility_non_transactional_use(
        self, ledger, sample_series, sample_metadata, sample_records
    ):
        """Test that ledger continues to work normally without transactions."""
        # Non-transactional operations should work as before
        ledger.add_series(sample_series, sample_metadata)
        ledger.add_records(sample_records)

        # Operations should be committed immediately (not buffered)
        assert len(ledger) > 0  # Data should be in the ledger
        assert not ledger.has_buffered_data()  # Nothing should be buffered
        assert not ledger._in_transaction

        # DataFrame generation should work
        df = ledger.ledger_df()
        assert not df.empty
        assert len(df) > 0


class TestLedgerTransactionBatchingDuckDB:
    """Test transaction batching for DuckDB Ledger."""

    @pytest.fixture
    def ledger(self):
        """Create a fresh DuckDB ledger instance for each test."""
        return Ledger()

    @pytest.fixture
    def sample_metadata(self):
        """Create sample metadata for testing."""
        return SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Test Item",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )

    @pytest.fixture
    def sample_series(self):
        """Create sample series for testing."""
        dates = pd.date_range("2024-01-01", periods=12, freq="M")
        return pd.Series([1000] * 12, index=dates)

    @pytest.fixture
    def sample_records(self):
        """Create sample TransactionRecord instances."""
        return [
            TransactionRecord(
                transaction_id=str(uuid.uuid4()),
                date=pd.Timestamp("2024-01-01").date(),
                amount=1000.0,
                flow_purpose="Operating",
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.LEASE,
                item_name="Test Record",
                source_id=uuid.uuid4(),
                asset_id=uuid.uuid4(),
                pass_num=1,
                deal_id=None,
                entity_id=None,
                entity_type=None,
            )
        ]

    def test_duckdb_transaction_context_manager_lifecycle(self, ledger):
        """Test that DuckDB transaction context manager properly manages state."""
        # Initial state
        assert not ledger._in_transaction
        assert len(ledger._transaction_buffer) == 0

        # Enter transaction context
        with ledger.transaction() as txn_ledger:
            assert ledger._in_transaction
            assert txn_ledger is ledger

        # Exit context
        assert not ledger._in_transaction
        assert len(ledger._transaction_buffer) == 0

    def test_duckdb_buffer_accumulation(
        self, ledger, sample_series, sample_metadata, sample_records
    ):
        """Test that DuckDB operations accumulate in buffer during transactions."""
        initial_count = len(ledger)

        with ledger.transaction():
            # Add series and records
            ledger.add_series(sample_series, sample_metadata)
            ledger.add_records(sample_records)

            # Operations should be buffered, not immediately inserted to DuckDB
            assert len(ledger._transaction_buffer) > 0
            assert len(ledger) == initial_count  # No immediate insert

    def test_duckdb_flush_behavior(self, ledger, sample_series, sample_metadata):
        """Test flush() behavior during DuckDB transactions."""
        initial_count = len(ledger)

        with ledger.transaction():
            # Add data
            ledger.add_series(sample_series, sample_metadata)
            assert ledger.has_buffered_data()
            assert len(ledger) == initial_count

            # Flush mid-transaction
            ledger.flush()

            # Buffer should be committed to DuckDB
            assert not ledger.has_buffered_data()
            assert len(ledger) > initial_count

    def test_duckdb_auto_commit_on_context_exit(
        self, ledger, sample_series, sample_metadata
    ):
        """Test that DuckDB operations are automatically committed on context exit."""
        initial_count = len(ledger)

        with ledger.transaction():
            ledger.add_series(sample_series, sample_metadata)
            assert ledger.has_buffered_data()

        # After context exit, operations should be in DuckDB
        assert not ledger.has_buffered_data()
        assert len(ledger) > initial_count

    def test_duckdb_error_handling_and_rollback(
        self, ledger, sample_series, sample_metadata
    ):
        """Test that DuckDB buffer is cleared on exception without committing."""
        initial_count = len(ledger)

        with pytest.raises(ValueError):
            with ledger.transaction():
                ledger.add_series(sample_series, sample_metadata)
                assert ledger.has_buffered_data()
                raise ValueError("Test exception")

        # Buffer should be cleared, no commit to DuckDB
        assert not ledger.has_buffered_data()
        assert len(ledger) == initial_count
        assert not ledger._in_transaction

    def test_duckdb_nested_transaction_prevention(self, ledger):
        """Test that nested DuckDB transactions are prevented."""
        with ledger.transaction():
            assert ledger._in_transaction

            with pytest.raises(
                RuntimeError, match="Nested transactions are not supported"
            ):
                with ledger.transaction():
                    pass

    def test_duckdb_flush_outside_transaction_raises_error(self, ledger):
        """Test that DuckDB flush() raises error when called outside transaction context."""
        with pytest.raises(
            RuntimeError,
            match="flush\\(\\) can only be called within a transaction context",
        ):
            ledger.flush()

    def test_duckdb_backward_compatibility_non_transactional_use(
        self, ledger, sample_series, sample_metadata, sample_records
    ):
        """Test that DuckDB ledger continues to work normally without transactions."""
        # Non-transactional operations should work as before
        ledger.add_series(sample_series, sample_metadata)
        ledger.add_records(sample_records)

        # Operations should be immediately inserted
        assert len(ledger._transaction_buffer) == 0
        assert not ledger._in_transaction
        assert len(ledger) > 0

        # DataFrame generation should work
        df = ledger.ledger_df()
        assert not df.empty


class TestTransactionPerformanceCharacteristics:
    """Test performance characteristics of transaction batching."""

    def test_transaction_reduces_dataframe_operations(self):
        """Test that transactions reduce the number of DataFrame concat operations."""
        ledger = Ledger()

        # Create test data
        dates = pd.date_range("2024-01-01", periods=10, freq="M")
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Test",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )

        # Mock the _commit_buffer method to count calls
        with patch.object(ledger, "_commit_buffer") as mock_commit:
            with ledger.transaction():
                # Add multiple series - should only commit once at the end
                for i in range(5):
                    series = pd.Series([1000 + i] * 10, index=dates)
                    ledger.add_series(series, metadata)

                # Verify no commits yet
                mock_commit.assert_not_called()

            # Should commit once on context exit
            mock_commit.assert_called_once()

    def test_duckdb_transaction_reduces_sql_operations(self):
        """Test that DuckDB transactions reduce the number of SQL INSERT operations."""
        ledger = Ledger()

        # Create test data
        dates = pd.date_range("2024-01-01", periods=10, freq="M")
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Test",
            source_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            pass_num=1,
        )

        # Mock the _bulk_insert_raw_data method to count calls (used by add_series optimized path)
        with patch.object(ledger, "_bulk_insert_raw_data") as mock_insert:
            with ledger.transaction():
                # Add multiple series - should buffer without inserting
                for i in range(5):
                    series = pd.Series([1000 + i] * 10, index=dates)
                    ledger.add_series(series, metadata)

                # Verify no inserts yet
                mock_insert.assert_not_called()

            # Should perform one bulk insert on context exit
            mock_insert.assert_called_once()
