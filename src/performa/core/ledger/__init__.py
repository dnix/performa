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
    - LedgerBuilder: Progressive ledger construction with ownership pattern
    - LedgerQuery: Query utilities with Pydantic validation
    - SeriesBatchConverter: Efficient batch Series conversion
    - FlowPurposeMapper: Business logic for transaction classification
    - LedgerGenerationSettings: Pydantic configuration model

Architecture:
    The ledger follows a "series preservation" approach where CashFlowModel
    instances continue to return pd.Series internally, with batch conversion to
    TransactionRecord instances occurring at the final assembly stage. This
    maintains performance while providing transparency and auditability.

Usage:
    ```python
    from performa.core.ledger import LedgerBuilder, SeriesMetadata
    
    # Create builder
    builder = LedgerBuilder()
    
    # Add series with metadata
    metadata = SeriesMetadata(
        category="Revenue",
        subcategory="Rent", 
        item_name="Base Rent",
        source_id=model.uid,
        asset_id=property.uid,
        pass_num=1
    )
    builder.add_series(cash_flow_series, metadata)
    
    # Get ledger (builder owns it)
    ledger = builder.get_current_ledger()
    ```
"""

# Core data models
# Builder and conversion
from .builder import LedgerBuilder
from .converter import SeriesBatchConverter

# Utilities
from .mapper import FlowPurposeMapper
from .query import LedgerQuery
from .records import SeriesMetadata, TransactionRecord
from .settings import LedgerGenerationSettings

__all__ = [
    # Core data models
    "TransactionRecord",
    "SeriesMetadata", 
    
    # Builder and conversion
    "LedgerBuilder",
    "SeriesBatchConverter",
    
    # Utilities
    "FlowPurposeMapper",
    "LedgerQuery", 
    "LedgerGenerationSettings",
]
