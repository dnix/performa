# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Configuration settings for ledger generation.

This module provides Pydantic models for configuring ledger behavior,
following existing Performa patterns for settings management.
"""

from pydantic import BaseModel, ConfigDict, Field


class LedgerGenerationSettings(BaseModel):
    # FIXME: should we be using a global settings object?
    """
    Configuration for transactional ledger generation behavior.
    
    Uses Pydantic for validation following existing GlobalSettings patterns.
    Controls performance optimizations, validation strictness, and output format.
    """
    
    # Data filtering
    skip_zero_values: bool = Field(
        default=True,
        description="Skip transactions with zero amounts to reduce ledger size"
    )
    
    # Validation controls
    validate_transactions: bool = Field(
        default=True,
        description="Perform validation on transaction records during batch processing"
    )
    
    validate_metadata: bool = Field(
        default=True, 
        description="Validate SeriesMetadata before conversion to records"
    )
    
    # Performance optimizations
    use_categorical_dtypes: bool = Field(
        default=True,
        description="Use pandas Categorical dtypes for string columns to save memory"
    )
    
    enable_smart_indexing: bool = Field(
        default=True,
        description="Automatically set date index for large ledgers (>10k records)"
    )
    
    large_ledger_threshold: int = Field(
        default=10000,
        ge=1000,
        description="Threshold for applying large ledger optimizations"
    )
    
    # Batch processing
    batch_size: int = Field(
        default=1000,
        ge=100,
        le=10000, 
        description="Batch size for Series to Record conversion"
    )
    
    # Output format
    preserve_precision: bool = Field(
        default=True,
        description="Preserve full floating point precision in amounts"
    )
    
    include_transaction_ids: bool = Field(
        default=True,
        description="Include unique transaction IDs for auditability"
    )
    
    # Memory management
    clear_intermediate_data: bool = Field(
        default=True,
        description="Clear intermediate Series data after successful conversion"
    )
    
    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",  # Prevent typos in field names
    )
        
    @property
    def memory_optimized(self) -> bool:
        """Check if settings are optimized for memory usage."""
        return (
            self.skip_zero_values and 
            self.use_categorical_dtypes and 
            self.clear_intermediate_data
        )
    
    @property  
    def performance_optimized(self) -> bool:
        """Check if settings are optimized for performance."""
        return (
            self.enable_smart_indexing and
            self.batch_size >= 1000 and
            not self.validate_transactions  # Validation has performance cost
        )
