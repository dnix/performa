# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Batch conversion utilities for Series to TransactionRecord transformation.

This module provides efficient batch processing capabilities for converting
pandas Series (with associated metadata) into TransactionRecord instances,
optimized for performance and memory usage.
"""

from __future__ import annotations

import datetime
import logging
from typing import List, Tuple

import pandas as pd

from .mapper import FlowPurposeMapper
from .records import SeriesMetadata, TransactionRecord

logger = logging.getLogger(__name__)


class SeriesBatchConverter:
    """
    Efficient batch converter for Series to TransactionRecord transformation.
    
    Pure utility class with static methods - no state.
    Optimized for vectorized operations where possible.
    """
    
    @staticmethod
    def convert_series(series: pd.Series, metadata: SeriesMetadata, skip_zeros: bool = True) -> List[TransactionRecord]:
        """
        Convert a single Series to TransactionRecord instances.
        
        Args:
            series: Time series of cash flows with date index
            metadata: Associated metadata for the series
            skip_zeros: Whether to skip zero-value transactions
            
        Returns:
            List of TransactionRecord instances
            
        Raises:
            ValueError: If series index is not datetime-like
        """
        if series is None or series.empty:
            return []
        
        # Convert index to DatetimeIndex if needed
        if isinstance(series.index, pd.PeriodIndex):
            # Convert PeriodIndex to DatetimeIndex
            series.index = series.index.to_timestamp()
        elif not isinstance(series.index, pd.DatetimeIndex):
            # Check if index contains Period objects
            
            # Handle mixed datetime-like objects
            datetime_like_types = (pd.Period, pd.Timestamp, datetime.date, datetime.datetime)
            if all(isinstance(x, datetime_like_types) for x in series.index):
                # Convert Period objects to timestamps, leave others as-is
                converted_index = []
                for x in series.index:
                    if isinstance(x, pd.Period):
                        converted_index.append(x.to_timestamp())
                    elif isinstance(x, (datetime.date, datetime.datetime)):
                        converted_index.append(pd.Timestamp(x))
                    else:  # Already Timestamp
                        converted_index.append(x)
                series.index = pd.DatetimeIndex(converted_index)
            else:
                # Try standard conversion for other types
                try:
                    series.index = pd.to_datetime(series.index)
                except Exception as e:
                    raise ValueError(f"Series index must be datetime-like: {e}")
        
        records = []
        
        for dt, amount in series.items():
            # Skip zero values if requested
            if skip_zeros and amount == 0.0:
                continue
            
            # Determine flow purpose using mapper
            flow_purpose = FlowPurposeMapper.determine_purpose_with_subcategory(
                metadata.category, 
                metadata.subcategory, 
                amount
            )
            
            # Convert to datetime.date for TransactionRecord
            if isinstance(dt, pd.Period):
                transaction_date = dt.to_timestamp().date()
            elif isinstance(dt, pd.Timestamp):
                transaction_date = dt.date()
            elif isinstance(dt, (datetime.date, datetime.datetime)):
                transaction_date = dt.date() if hasattr(dt, 'date') else dt
            else:
                # Fallback - try to convert to date
                transaction_date = pd.Timestamp(dt).date()
            
            record = TransactionRecord(
                date=transaction_date,
                amount=float(amount),
                flow_purpose=flow_purpose,
                category=metadata.category,
                subcategory=metadata.subcategory,
                item_name=metadata.item_name,
                source_id=metadata.source_id,
                asset_id=metadata.asset_id,
                pass_num=metadata.pass_num,
                deal_id=metadata.deal_id,
                entity_id=metadata.entity_id,
                entity_type=metadata.entity_type
            )
            
            records.append(record)
        
        return records
    
    @staticmethod
    def convert_all(
        series_batch: List[Tuple[pd.Series, SeriesMetadata]], 
        skip_zeros: bool = True
    ) -> List[TransactionRecord]:
        """
        Convert multiple Series to TransactionRecord instances in batch.
        
        Args:
            series_batch: List of (Series, metadata) tuples
            skip_zeros: Whether to skip zero-value transactions
            
        Returns:
            Flattened list of all TransactionRecord instances
            
        Performance target: <10ms per 1000 records
        """
        if not series_batch:
            return []
        
        start_time = pd.Timestamp.now()
        all_records = []
        
        for series, metadata in series_batch:
            try:
                records = SeriesBatchConverter.convert_series(series, metadata, skip_zeros)
                all_records.extend(records)
            except Exception as e:
                logger.error(f"Failed to convert series '{metadata.item_name}': {e}")
                # Re-raise to prevent silent failures
                raise ValueError(f"Batch conversion failed for '{metadata.item_name}': {e}") from e
        
        # Performance logging
        elapsed = (pd.Timestamp.now() - start_time).total_seconds() * 1000
        record_count = len(all_records)
        
        if record_count > 0:
            ms_per_record = elapsed / record_count
            logger.debug(f"Converted {record_count} records in {elapsed:.1f}ms ({ms_per_record:.3f}ms/record)")
        
        return all_records
    
    @staticmethod
    def validate_series_metadata(series: pd.Series, metadata: SeriesMetadata) -> None:
        """
        Validate that Series and metadata are compatible.
        
        Args:
            series: Time series to validate
            metadata: Associated metadata
            
        Raises:
            ValueError: If validation fails
        """
        if series is None:
            raise ValueError("Series cannot be None")
        
        if metadata is None:
            raise ValueError("Metadata cannot be None")
        
        # Check for datetime-like index (DatetimeIndex or PeriodIndex)
        if not series.empty:
            if not isinstance(series.index, (pd.DatetimeIndex, pd.PeriodIndex)):
                # Check if index contains datetime-like objects (Period, Timestamp, etc.)
                try:
                    # Try converting to datetime - this works for most datetime-like objects
                    pd.to_datetime(series.index)
                except Exception:
                    # If conversion fails, check if all elements are datetime-like objects
                   
                    datetime_like_types = (pd.Period, pd.Timestamp, datetime.date, datetime.datetime)
                    if all(isinstance(x, datetime_like_types) for x in series.index):
                        # Index of datetime-like objects is acceptable
                        pass
                    else:
                        raise ValueError(f"Series index must be datetime-like, got {type(series.index)} with elements: {[type(x).__name__ for x in series.index[:3]]}")
        
        # Check for numeric values
        if not series.empty and not pd.api.types.is_numeric_dtype(series):
            raise ValueError("Series must contain numeric values")
    
    @staticmethod 
    def estimate_record_count(series_batch: List[Tuple[pd.Series, SeriesMetadata]], skip_zeros: bool = True) -> int:
        """
        Estimate the number of records that will be generated from a batch.
        
        Args:
            series_batch: List of (Series, metadata) tuples
            skip_zeros: Whether zero values will be skipped
            
        Returns:
            Estimated record count
        """
        total_estimate = 0
        
        for series, _ in series_batch:
            if series is None or series.empty:
                continue
            
            if skip_zeros:
                # Count non-zero values
                non_zero_count = (series != 0.0).sum()
                total_estimate += non_zero_count
            else:
                total_estimate += len(series)
        
        return total_estimate
