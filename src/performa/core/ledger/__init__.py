# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
DuckDB-only ledger backend.

This module exposes the DuckDB ledger and queries classes as the single,
canonical backend implementation.
"""

from .ledger import Ledger
from .queries import LedgerQueries
from .records import SeriesMetadata, TransactionRecord
from .settings import LedgerGenerationSettings

__all__ = [
    "Ledger",
    "LedgerQueries",
    "SeriesMetadata",
    "TransactionRecord",
    "LedgerGenerationSettings",
]
