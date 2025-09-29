# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Dual-backend ledger system with environment-based switching.

This module provides seamless switching between pandas (main branch compatible)
and DuckDB (performance optimized) backends via the USE_DUCKDB_LEDGER environment variable.

Usage:
    # Use pandas backend (default, main branch compatible)
    export USE_DUCKDB_LEDGER=false
    
    # Use DuckDB backend (performance optimized)  
    export USE_DUCKDB_LEDGER=true
"""

import os
from typing import TYPE_CHECKING

# Environment variable for backend selection
_USE_DUCKDB = os.environ.get("USE_DUCKDB_LEDGER", "false").lower() in ("true", "1", "yes")

if _USE_DUCKDB:
    # DuckDB backend (performance optimized)
    from .ledger_duckdb import Ledger as DuckDBLedger
    from .queries_duckdb import LedgerQueries as DuckDBQueries
    
    # Use DuckDB implementations
    Ledger = DuckDBLedger
    LedgerQueries = DuckDBQueries
    
    # Export backend info for diagnostics
    BACKEND_NAME = "DuckDB"
    BACKEND_TYPE = "duckdb"
else:
    # Pandas backend (main branch compatible)
    from .ledger_pandas import Ledger as PandasLedger
    from .queries_pandas import LedgerQueries as PandasQueries
    
    # Use pandas implementations  
    Ledger = PandasLedger
    LedgerQueries = PandasQueries
    
    # Export backend info for diagnostics
    BACKEND_NAME = "Pandas"
    BACKEND_TYPE = "pandas"

# Always export common components
from .records import SeriesMetadata, TransactionRecord
from .settings import LedgerGenerationSettings

# Export the active backend classes and metadata
__all__ = [
    "Ledger",
    "LedgerQueries", 
    "SeriesMetadata",
    "TransactionRecord",
    "LedgerGenerationSettings",
    "BACKEND_NAME",
    "BACKEND_TYPE"
]


def get_backend_info() -> dict:
    """
    Get information about the currently active backend.
    
    Returns:
        Dictionary with backend name, type, and capabilities
    """
    return {
        "name": BACKEND_NAME,
        "type": BACKEND_TYPE,
        "environment_variable": "USE_DUCKDB_LEDGER",
        "current_value": os.environ.get("USE_DUCKDB_LEDGER", "false"),
        "description": "Pandas backend (main branch compatible)" if BACKEND_TYPE == "pandas" 
                      else "DuckDB backend (performance optimized)"
    }


if TYPE_CHECKING:
    # For type checking, always import both backend types
    from .ledger_duckdb import Ledger as DuckDBLedger
    from .ledger_pandas import Ledger as PandasLedger
    from .queries_duckdb import LedgerQueries as DuckDBQueries
    from .queries_pandas import LedgerQueries as PandasQueries
