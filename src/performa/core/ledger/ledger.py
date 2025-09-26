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

logger = logging.getLogger(__name__)


@dataclass
class Ledger:
    """
    Progressive ledger construction with a pass-the-builder pattern.

    The ledger "owns" the transaction records, maintaining internal state and providing
    ledger_df() for access. This prevents mismatches between the ledger's
    records and any external DataFrame references.
    """


    # Internal state
    records: List[TransactionRecord] = field(default_factory=list, init=False)
    series_batch: List[Tuple[pd.Series, SeriesMetadata]] = field(
        default_factory=list, init=False
    )
    _current_ledger: Optional[pd.DataFrame] = field(
        default=None, init=False, repr=False
    )
    _ledger_dirty: bool = field(default=False, init=False, repr=False)


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
            # Filter zero values if configured
            records = self._filter_zero_records(records)
            
            self.records.extend(records)
            self._ledger_dirty = True

    def ledger_df(self) -> pd.DataFrame:
        """
        Get the current ledger as a DataFrame, using incremental updates for performance.

        The class owns the ledger - this is the only way to access it.
        Uses incremental updates to avoid O(n²) rebuilds during analysis.

        Returns:
            Complete ledger DataFrame
        """
        if self._current_ledger is None:
            # First time: full build
            self._current_ledger = self._to_dataframe()
            self._ledger_dirty = False
        elif self._ledger_dirty and self.series_batch:
            # Incremental: add only new data
            self._current_ledger = self._append_new_data()
            self._ledger_dirty = False

        return self._current_ledger


    def _to_dataframe(self) -> pd.DataFrame:
        """
        Convert all pending Series and existing Records to an optimized DataFrame.
        
        Uses the proven SeriesBatchConverter logic with vectorized DataFrame creation.
        This is called only for the initial build - subsequent updates use _append_new_data().
        """
        logger.debug(
            f"_to_dataframe called with {len(self.series_batch)} series and {len(self.records)} records"
        )

        # Convert series to records first (proven logic from original implementation)
        if self.series_batch:
            try:
                batch_records = SeriesBatchConverter.convert_all(
                    self.series_batch, skip_zeros=True
                )
                self.records.extend(batch_records)
                self.series_batch.clear()
            except Exception as e:
                logger.error(f"Batch conversion failed: {e}")
                raise

        # Create DataFrame once
        if not self.records:
            return self._empty_ledger()

        # Vectorized DataFrame creation from records
        df = self._records_to_dataframe_vectorized(self.records)

        # Apply DataFrame optimizations for memory and performance
        df = self._optimize_dataframe(df)

        logger.info(f"Built ledger with {len(df)} transactions from {len(self.records)} records")
        return df



    def _records_to_dataframe_vectorized(self, records) -> pd.DataFrame:
        """Vectorized version of _records_to_dataframe for better performance."""
        if not records:
            return self._empty_ledger()
        
        # Pre-allocate lists for all columns
        data = {
            "transaction_id": [],
            "date": [],
            "amount": [],
            "flow_purpose": [],
            "category": [],
            "subcategory": [],
            "item_name": [],
            "source_id": [],
            "asset_id": [],
            "pass_num": [],
            "deal_id": [],
            "entity_id": [],
            "entity_type": [],
        }
        
        # Vectorized data extraction
        for record in records:
            data["transaction_id"].append(record.transaction_id)
            data["date"].append(record.date)
            data["amount"].append(record.amount)
            data["flow_purpose"].append(enum_to_string(record.flow_purpose))
            data["category"].append(enum_to_string(record.category))
            data["subcategory"].append(enum_to_string(record.subcategory))
            data["item_name"].append(record.item_name)
            data["source_id"].append(record.source_id)
            data["asset_id"].append(record.asset_id)
            data["pass_num"].append(record.pass_num)
            data["deal_id"].append(record.deal_id)
            data["entity_id"].append(record.entity_id)
            data["entity_type"].append(record.entity_type)
        
        return pd.DataFrame(data)

    def _append_new_data(self) -> pd.DataFrame:
        """
        Incremental update: add only new series data to existing DataFrame.
        
        This is the key performance optimization that avoids O(n²) rebuilds.
        """
        
        if not self.series_batch:
            # No new data, return existing
            return self._current_ledger
            
        # Convert only the new series to records 
        new_records = SeriesBatchConverter.convert_all(
            self.series_batch, skip_zeros=True
        )
        
        # Convert new records to DataFrame rows
        new_df = self._records_to_dataframe_vectorized(new_records)
        
        # Concatenate with existing DataFrame (handle empty DataFrames to avoid FutureWarning)
        if new_df.empty:
            result_df = self._current_ledger.copy()
        elif self._current_ledger.empty:
            result_df = new_df.copy()
        else:
            # Simply concatenate - avoid dropna which might remove important columns
            result_df = pd.concat([self._current_ledger, new_df], ignore_index=True)
        
        # Apply DataFrame optimizations to the complete DataFrame
        result_df = self._optimize_dataframe(result_df)
            
        # Clear the processed batch and update records list
        self.records.extend(new_records)
        self.series_batch.clear()
        
        
        return result_df

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

    def _apply_categorical_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply comprehensive dtype optimizations for memory efficiency and query speed.
        
        Optimizations applied:
        - String columns → categorical (major memory savings)
        - Integer columns → downcast to smallest suitable type  
        - UUID columns → string (consistent, memory-efficient)
        """
        # 1. Convert high-cardinality string columns to categorical
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
        
        # 2. Downcast integer columns to smallest suitable type
        if "pass_num" in df.columns:
            # pass_num is typically 1-6, so int8 is sufficient
            df["pass_num"] = pd.to_numeric(df["pass_num"], downcast="integer")
        
        # 3. Convert UUID columns to string for consistency and memory efficiency  
        uuid_columns = ["source_id", "asset_id", "deal_id", "entity_id", "transaction_id"]
        for col in uuid_columns:
            if col in df.columns and df[col].dtype == "object":
                df[col] = df[col].astype(str)
        
        # 4. Ensure amount column is optimal float type
        if "amount" in df.columns:
            # Most financial amounts fit in float32, but keep float64 for precision
            # This is a safety vs. memory tradeoff - keeping float64 for financial accuracy
            pass  # Keep default float64 for financial precision
            
        return df

    def _optimize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply DataFrame optimizations for memory efficiency and query performance.
        
        Applies smart optimizations based on DataFrame size to balance performance
        gains against optimization overhead. Includes dtype optimizations and
        date sorting for improved query speed.
        
        Args:
            df: DataFrame to optimize
            
        Returns:
            Optimized DataFrame with categorical dtypes and improved layout
        """
        if df.empty or len(df) < 1000:
            # Skip optimization for small DataFrames to avoid overhead
            return df
            
        # Apply categorical dtypes and integer downcasting
        df = self._apply_categorical_dtypes(df)
        
        # Apply date optimization for large ledgers where sorting provides benefit
        if len(df) >= 5000:
            df = self._optimize_date_column(df)
            
        return df

    def _optimize_date_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Optimize the date column for better query performance.
        
        Converts to datetime dtype and sorts by date while preserving the column
        structure required for downstream operations and LedgerQueries compatibility.
        
        Args:
            df: DataFrame with date column to optimize
            
        Returns:
            DataFrame with optimized date column and improved sort order
        """
        if "date" not in df.columns:
            return df
            
        # Convert to datetime dtype for faster pandas operations
        if not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"])
        
        # Sort by date for improved query performance on time-series operations
        if not df["date"].is_monotonic_increasing:
            df = df.sort_values("date").reset_index(drop=True)
            
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

    def _filter_zero_records(
        self, records: List[TransactionRecord]
    ) -> List[TransactionRecord]:
        """Filter out zero-value records to keep ledger clean and performant."""
        return [record for record in records if record.amount != 0.0]

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

    def estimate_final_count(self) -> int:
        """Estimate total records after processing pending Series."""
        current_count = self.record_count()
        estimated_from_series = SeriesBatchConverter.estimate_record_count(
            self.series_batch, skip_zeros=True
        )
        return current_count + estimated_from_series
