# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Core data models for the transactional ledger.

This module defines the fundamental record structures used throughout
the ledger system, following Performa's dataclass patterns for
performance and type safety.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional, Union
from uuid import UUID, uuid4

from performa.core.primitives import (
    CapExCategoryEnum,
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
    FinancingSubcategoryEnum,
    RevenueSubcategoryEnum,
    TransactionPurpose,
    ValuationSubcategoryEnum,
)


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    """
    Immutable record representing a single financial transaction.

    **Architecture Note**: This dataclass is used for type-hinting and representing
    individual transactions read from a ledger. For performance, the vectorized ledger
    implementation bypasses TransactionRecord creation during DataFrame construction,
    building DataFrames directly from Series data via columnar operations.

    Attributes:
        transaction_id: Unique identifier for auditability
        date: Transaction date
        amount: Transaction amount (+ = inflow, - = outflow)
        flow_purpose: High-level classification (Operating, Capital Use, etc.)
        category: Primary categorization (Revenue, Expense, Capital, etc.)
        subcategory: Secondary categorization (Rent, Utilities, etc.)
        item_name: Descriptive name of the transaction
        source_id: UID of the originating model/component
        asset_id: Asset this transaction belongs to
        pass_num: Calculation pass (1=independent, 2=dependent)
        deal_id: Deal this transaction belongs to (optional)
        entity_id: Counterparty entity (optional)
        entity_type: Type of counterparty (Partner, Third Party, etc.)
    """

    # Core transaction data
    date: datetime.date
    amount: float
    flow_purpose: TransactionPurpose
    category: CashFlowCategoryEnum
    subcategory: Union[
        CapitalSubcategoryEnum,
        CapExCategoryEnum,
        ExpenseSubcategoryEnum,
        FinancingSubcategoryEnum,
        RevenueSubcategoryEnum,
        ValuationSubcategoryEnum,
    ]
    item_name: str

    # Traceability
    source_id: UUID
    asset_id: UUID
    pass_num: int

    # Optional context
    deal_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    entity_type: Optional[str] = None

    # Unique identifier for auditability
    transaction_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class SeriesMetadata:
    """
    Type-safe metadata for converting pd.Series to TransactionRecord instances.

    Encapsulates all the context needed to transform a time series of
    cash flows into individual transaction records with proper attribution.

    Attributes:
        category: Primary categorization
        subcategory: Secondary categorization
        item_name: Descriptive name
        source_id: UID of the originating model/component
        asset_id: Asset this series belongs to
        pass_num: Calculation pass (1=independent, 2=dependent)
        deal_id: Deal this series belongs to (optional)
        entity_id: Counterparty entity (optional)
        entity_type: Type of counterparty (optional)
    """

    # Required metadata
    category: CashFlowCategoryEnum
    subcategory: Union[
        CapitalSubcategoryEnum,
        CapExCategoryEnum,
        ExpenseSubcategoryEnum,
        FinancingSubcategoryEnum,
        RevenueSubcategoryEnum,
        ValuationSubcategoryEnum,
    ]
    item_name: str
    source_id: UUID
    asset_id: UUID
    pass_num: int

    # Optional context
    deal_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    entity_type: Optional[str] = None
