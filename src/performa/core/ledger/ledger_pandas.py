# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Progressive ledger construction pattern.

This module provides the Ledger class, which serves as the central
accumulator for transaction records and owns the ledger DataFrame, ensuring
consistency and preventing data mismatches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pandas as pd

from ..primitives.enums import enum_to_string
from .converter import SeriesBatchConverter
from .records import SeriesMetadata, TransactionRecord
from .settings import LedgerGenerationSettings

logger = logging.getLogger(__name__)


@dataclass
class Ledger:
    """
    Progressive ledger construction with a pass-the-builder pattern.

    The ledger "owns" the transaction records, maintaining internal state and providing
    ledger_df() for access. This prevents mismatches between the ledger's
    records and any external DataFrame references.
    """

    # Configuration
    settings: Optional[LedgerGenerationSettings] = (
        None  # TODO: should this have a default factory of LedgerGenerationSettings()?
    )

    # Internal state
    records: List[TransactionRecord] = field(default_factory=list, init=False)
    series_batch: List[Tuple[pd.Series, SeriesMetadata]] = field(
        default_factory=list, init=False
    )
    _current_ledger: Optional[pd.DataFrame] = field(
        default=None, init=False, repr=False
    )
    _ledger_dirty: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        """Initialize with default settings if none provided."""
        if self.settings is None:
            self.settings = LedgerGenerationSettings()

    def add_series(self, series: pd.Series, metadata: SeriesMetadata) -> None:
        """
        Add a single Series with metadata to the batch for processing.

        Args:
            series: Time series of cash flows
            metadata: Associated metadata for conversion
        """
        if series is not None and not series.empty:
            self.series_batch.append((series, metadata))
            self._ledger_dirty = True

    def add_series_batch(self, pairs: List[Tuple[pd.Series, SeriesMetadata]]) -> None:
        """
        Add multiple Series-metadata pairs at once.

        Args:
            pairs: List of (Series, metadata) tuples
        """
        for series, metadata in pairs:
            self.add_series(series, metadata)

    def add_records(self, records: List[TransactionRecord]) -> None:
        """
        Add pre-converted TransactionRecord instances directly.

        Args:
            records: List of transaction records to add
        """
        if records:
            # Validate if enabled
            if self.settings.validate_transactions:
                records = self._validate_batch(records)

            self.records.extend(records)
            self._ledger_dirty = True

    def ledger_df(self) -> pd.DataFrame:
        """
        Get the current ledger as a DataFrame, creating it if necessary.

        The class owns the ledger - this is the only way to access it.
        Ledger is built/cached and only rebuilt when dirty.

        Returns:
            Complete ledger DataFrame
        """
        if self._current_ledger is None or self._ledger_dirty:
            self._current_ledger = self._to_dataframe()
            self._ledger_dirty = False

        return self._current_ledger

    def _to_dataframe(self) -> pd.DataFrame:
        """
        Convert all Series and Records to optimized DataFrame.

        Performance target: <10ms per 1000 records
        Memory target: <60% of raw object dtypes
        """
        logger.debug(
            f"_to_dataframe called with {len(self.series_batch)} series and {len(self.records)} records"
        )

        # Batch convert all Series (vectorized)
        if self.series_batch:
            try:
                batch_records = SeriesBatchConverter.convert_all(
                    self.series_batch, skip_zeros=self.settings.skip_zero_values
                )
                self.records.extend(batch_records)
                # Only clear AFTER successful conversion to prevent data loss
                self.series_batch.clear()
            except Exception as e:
                # Log error but preserve batch data for retry/debugging
                logger.error(f"Batch conversion failed: {e}")
                # Re-raise to prevent silently continuing with incomplete data
                raise

        # Create DataFrame once
        if not self.records:
            return self._empty_ledger()

        # Convert records to DataFrame with optimizations
        df = self._records_to_dataframe(self.records)

        # Apply optimizations
        if self.settings.use_categorical_dtypes:
            df = self._apply_categorical_dtypes(df)

        # if (
        #     self.settings.enable_smart_indexing
        #     and len(df) > self.settings.large_ledger_threshold
        # ):
        #     df = self._apply_smart_indexing(df)

        logger.info(
            f"Built ledger with {len(df)} transactions from {len(self.records)} records"
        )

        return df

    def _empty_ledger(self) -> pd.DataFrame:
        """Create empty ledger with proper schema."""
        return pd.DataFrame(
            columns=[
                "transaction_id",
                "date",
                "amount",
                "flow_purpose",
                "category",
                "subcategory",
                "item_name",
                "source_id",
                "asset_id",
                "pass_num",
                "deal_id",
                "entity_id",
                "entity_type",
            ]
        )

    def _records_to_dataframe(self, records: List[TransactionRecord]) -> pd.DataFrame:
        """Convert TransactionRecord list to DataFrame efficiently."""
        # Use list comprehension for speed
        data = []
        for record in records:
            # Convert all enum values to strings for pandas compatibility
            row = {
                "transaction_id": record.transaction_id,
                "date": record.date,
                "amount": record.amount,
                "flow_purpose": enum_to_string(record.flow_purpose),
                "category": enum_to_string(record.category),
                "subcategory": enum_to_string(record.subcategory),
                "item_name": record.item_name,
                "source_id": record.source_id,
                "asset_id": record.asset_id,
                "pass_num": record.pass_num,
                "deal_id": record.deal_id,
                "entity_id": record.entity_id,
                "entity_type": record.entity_type,
            }
            data.append(row)

        return pd.DataFrame(data)

    def _apply_categorical_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert string columns to categorical for memory efficiency."""
        categorical_columns = [
            "flow_purpose",
            "category",
            "subcategory",
            "item_name",
            "entity_type",
        ]

        for col in categorical_columns:
            if col in df.columns and df[col].dtype == "object":
                df[col] = df[col].astype("category")

        return df

    def _apply_smart_indexing(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply date indexing for large ledgers."""
        # DISABLED: Smart indexing causes pandas groupby ambiguity issues.
        # All downstream operations expect groupby("date") which requires a column.
        # The performance benefits of date indexing are theoretical while the
        # pandas ambiguity issues are real and affect all users.
        #
        # Future enhancement: Could add date indexing only for specific query
        # patterns that benefit from it, but would need to handle groupby carefully.
        return df

    def _validate_batch(
        self, records: List[TransactionRecord]
    ) -> List[TransactionRecord]:
        """Validate a batch of records, filtering out invalid ones."""
        valid_records = []

        for record in records:
            try:
                # Basic validation (post_init handles most of this)
                if record.amount == 0.0 and self.settings.skip_zero_values:
                    continue

                valid_records.append(record)
            except Exception as e:
                logger.warning(f"Skipping invalid record: {e}")
                continue

        return valid_records

    def clear(self) -> None:
        """Clear all records and reset state."""
        self.records.clear()
        self.series_batch.clear()
        self._current_ledger = None
        self._ledger_dirty = False

    def record_count(self) -> int:
        """Get current number of transaction records."""
        return len(self.records)

    def series_count(self) -> int:
        """Get number of pending Series awaiting conversion."""
        return len(self.series_batch)

    def estimate_final_count(self) -> int:
        """Estimate total records after processing pending Series."""
        current_count = self.record_count()
        estimated_from_series = SeriesBatchConverter.estimate_record_count(
            self.series_batch, self.settings.skip_zero_values
        )
        return current_count + estimated_from_series

    def __len__(self) -> int:
        """Return count of transaction records for compatibility."""
        return len(self.records) + sum(len(batch) for batch, _ in self.series_batch)

    # === TRANSACTION COMPATIBILITY METHODS ===
    # These methods provide compatibility with DuckDB-style transaction management
    # but are no-ops for pandas since it doesn't need explicit transactions
    
    def transaction(self):
        """
        Return a context manager for transaction compatibility.
        
        For pandas backend, this is a no-op since pandas operations
        are immediately applied to the DataFrame.
        """
        return PandasTransactionContext()
    
    def flush(self):
        """
        Flush any pending operations (no-op for pandas).
        
        For pandas backend, all operations are immediately applied
        so this is included only for API compatibility.
        """
        pass  # No-op for pandas


class PandasTransactionContext:
    """
    Transaction context manager for pandas backend compatibility.
    
    This is a no-op context manager that provides the same interface
    as the DuckDB transaction context but performs no actual transaction
    management since pandas operations are immediate.
    """
    
    def __enter__(self):
        """Enter transaction context (no-op)."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit transaction context (no-op)."""
        pass

    def __len__(self) -> int:
        """Return count of transaction records for compatibility."""
        return len(self.records) + sum(len(batch) for batch, _ in self.series_batch)
