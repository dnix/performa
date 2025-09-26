# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Transactional Ledger System

This module provides the unified transactional ledger infrastructure for Performa,
replacing wide-format DataFrames with an immutable, auditable record-based system
that serves as the single source of truth for all financial calculations.

Key Components:
    - TransactionRecord: Immutable transaction representation
    - SeriesMetadata: Type-safe metadata for Series conversion
    - Ledger: Progressive ledger construction with ownership pattern
    - LedgerQueries: Clean query interface for financial metrics
    - FlowPurposeMapper: Business logic for transaction classification

Architecture:
    The ledger follows a "series preservation" approach where CashFlowModel
    instances continue to return pd.Series internally, with batch conversion to
    TransactionRecord instances occurring at the final assembly stage. This
    maintains performance while providing transparency and auditability.

Usage:
    ```python
    from performa.core.ledger import Ledger, SeriesMetadata

    # Create ledger
    ledger = Ledger()

    # Add series with metadata
    metadata = SeriesMetadata(
        category="Revenue",
        subcategory="Rent",
        item_name="Base Rent",
        source_id=model.uid,
        asset_id=property.uid,
        pass_num=1
    )
    ledger.add_series(cash_flow_series, metadata)

    # Get current state of ledger
    ledger_df = ledger.ledger_df()
    ```
"""

# Core data models
# Ledger and query interface
from .ledger import Ledger

# Utilities
from .mapper import FlowPurposeMapper
from .queries import LedgerQueries
from .records import SeriesMetadata, TransactionRecord

__all__ = [
    # Core data models
    "TransactionRecord",
    "SeriesMetadata",
    # Ledger and query interface
    "Ledger",
    "LedgerQueries",
    # Utilities
    "FlowPurposeMapper",
]
