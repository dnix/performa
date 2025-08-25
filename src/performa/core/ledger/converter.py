# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Batch conversion utilities for Series to TransactionRecord transformation.

This module provides efficient batch processing capabilities for converting
pandas Series (with associated metadata) into TransactionRecord instances.
"""

from __future__ import annotations

from typing import List, Tuple

import pandas as pd

from .mapper import FlowPurposeMapper
from .records import SeriesMetadata, TransactionRecord


class SeriesBatchConverter:
    """
    Efficient batch converter for Series to TransactionRecord transformation.

    Clean, strict-typing approach with architectural boundary enforcement.
    """

    @staticmethod
    def convert_series(
        series: pd.Series, metadata: SeriesMetadata, skip_zeros: bool = True
    ) -> List[TransactionRecord]:
        """
        Convert a single Series to TransactionRecord instances.

        Args:
            series: Time series with PeriodIndex (from models)
            metadata: Associated metadata for the series
            skip_zeros: Whether to skip zero-value transactions

        Returns:
            List of TransactionRecord instances

        Raises:
            TypeError: If series doesn't have PeriodIndex (architectural violation)
        """
        if series is None or series.empty:
            return []

        # ARCHITECTURAL BOUNDARY: Models → PeriodIndex, Ledger → DatetimeIndex
        if isinstance(series.index, pd.PeriodIndex):
            series.index = series.index.to_timestamp()
        elif isinstance(series.index, pd.DatetimeIndex):
            pass  # Already correct
        else:
            raise TypeError(
                f"Expected PeriodIndex from models, got {type(series.index).__name__}. "
                f"Series: {metadata.item_name}"
            )

        records = []
        for dt, amount in series.items():
            if skip_zeros and abs(amount) < 1e-10:
                continue

            flow_purpose = FlowPurposeMapper.determine_purpose_with_subcategory(
                metadata.category, metadata.subcategory, amount
            )

            # Convert to date for TransactionRecord
            transaction_date = dt.date() if hasattr(dt, "date") else dt

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
                entity_type=metadata.entity_type,
            )
            records.append(record)

        return records

    @staticmethod
    def convert_all(
        series_batch: List[Tuple[pd.Series, SeriesMetadata]], skip_zeros: bool = True
    ) -> List[TransactionRecord]:
        """
        Convert multiple Series to TransactionRecord instances.

        Simple, clean batch processing using convert_series (DRY principle).
        """
        if not series_batch:
            return []

        all_records = []
        for series, metadata in series_batch:
            records = SeriesBatchConverter.convert_series(series, metadata, skip_zeros)
            all_records.extend(records)

        return all_records
