# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Flow purpose mapping utilities for the transactional ledger.

This module provides logic for mapping transaction categories and amounts
to TransactionPurpose values, following standard real estate accounting
principles and the existing Performa categorization system.
"""

from functools import lru_cache
from typing import TYPE_CHECKING, Dict, List, Union

if TYPE_CHECKING:
    from .records import TransactionRecord

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


class FlowPurposeMapper:
    """
    Pure utility class for mapping categories to transaction purposes.

    No state, no __init__ - only static methods following v3.2 patterns.
    Encapsulates business rules for flow classification based on
    standard real estate accounting principles.
    """

    # Cache enum value lists to avoid repeated list comprehensions
    @staticmethod
    @lru_cache(maxsize=None)
    def _get_capital_subcategory_values():
        return [e.value for e in CapitalSubcategoryEnum]

    @staticmethod
    @lru_cache(maxsize=None)
    def _get_capex_category_values():
        return [e.value for e in CapExCategoryEnum]

    @staticmethod
    @lru_cache(maxsize=None)
    def _get_revenue_subcategory_values():
        return [e.value for e in RevenueSubcategoryEnum]

    @staticmethod
    @lru_cache(maxsize=None)
    def _get_financing_subcategory_values():
        return [e.value for e in FinancingSubcategoryEnum]

    @staticmethod
    @lru_cache(maxsize=None)
    def _get_expense_subcategory_values():
        return [e.value for e in ExpenseSubcategoryEnum]

    @staticmethod
    def determine_purpose(
        category: CashFlowCategoryEnum, amount: float
    ) -> TransactionPurpose:
        """
        Determine TransactionPurpose based on category and amount sign.

        Uses actual enum values instead of brittle string matching.

        Args:
            category: Primary transaction category (Revenue, Expense, Capital, etc.)
            amount: Transaction amount (sign indicates direction)

        Returns:
            TransactionPurpose enum value

        Rules:
            - Revenue/Expense categories -> OPERATING
            - Capital category -> CAPITAL_USE (outflow) or CAPITAL_SOURCE (inflow)
            - Financing category -> FINANCING_SERVICE (outflow) or CAPITAL_SOURCE (inflow)
        """
        # Use enum values for robust classification
        if (
            category == CashFlowCategoryEnum.REVENUE
            or category == CashFlowCategoryEnum.EXPENSE
        ):
            return TransactionPurpose.OPERATING

        # Financing flows depend on direction (like Capital)
        if category == CashFlowCategoryEnum.FINANCING:
            # Outflows are debt service, inflows are capital sources (loan proceeds)
            if amount < 0:
                return TransactionPurpose.FINANCING_SERVICE
            else:
                return TransactionPurpose.CAPITAL_SOURCE

        # Capital flows depend on direction
        if category == CashFlowCategoryEnum.CAPITAL:
            # Outflows are capital deployment, inflows are capital sources
            if amount < 0:
                return TransactionPurpose.CAPITAL_USE
            else:
                return TransactionPurpose.CAPITAL_SOURCE

        # Valuation category (asset appraisals and mark-to-market records)
        if category == CashFlowCategoryEnum.VALUATION:
            return TransactionPurpose.VALUATION

        # No fallback - force proper enum usage
        raise ValueError(
            f"Unknown category: {category} (type: {type(category)}). Use proper CashFlowCategoryEnum values."
        )

    @staticmethod
    def determine_purpose_with_subcategory(
        category: CashFlowCategoryEnum,
        subcategory: Union[
            CapitalSubcategoryEnum,
            CapExCategoryEnum,
            ExpenseSubcategoryEnum,
            RevenueSubcategoryEnum,
            ValuationSubcategoryEnum,
        ],
        amount: float,
    ) -> TransactionPurpose:
        """
        Comprehensive purpose determination considering subcategory.

        Uses actual enum values instead of brittle string patterns.

        Args:
            category: Primary transaction category
            subcategory: Secondary categorization
            amount: Transaction amount

        Returns:
            TransactionPurpose enum value

        Special Rules:
            - Capital subcategories -> CAPITAL_USE or CAPITAL_SOURCE based on type
            - CapEx subcategories -> CAPITAL_USE
            - Revenue subcategories -> CAPITAL_SOURCE (for sales) or OPERATING
            - Financing subcategories -> CAPITAL_SOURCE (proceeds) or FINANCING_SERVICE
        """

        # Use enum values for robust classification (OPTIMIZED: cached enum lists)
        try:
            # Capital subcategories - check amount sign like base logic
            # Must check amount sign for capital subcategories
            # Positive amounts (like Exit Sale) are SOURCES, not USES
            if subcategory in FlowPurposeMapper._get_capital_subcategory_values():
                if amount < 0:
                    return TransactionPurpose.CAPITAL_USE
                else:
                    return TransactionPurpose.CAPITAL_SOURCE

            # CapEx subcategories (tenant improvements, leasing costs, renovations)
            if subcategory in FlowPurposeMapper._get_capex_category_values():
                return TransactionPurpose.CAPITAL_USE

            # Revenue subcategories
            if subcategory in FlowPurposeMapper._get_revenue_subcategory_values():
                if subcategory == RevenueSubcategoryEnum.SALE:
                    return TransactionPurpose.CAPITAL_SOURCE
                else:
                    return TransactionPurpose.OPERATING

            # Financing subcategories based on common patterns
            if category == CashFlowCategoryEnum.FINANCING:
                # CRITICAL FIX: Proper classification of equity vs debt transactions

                # EQUITY_CONTRIBUTION: Capital coming IN from partners = CAPITAL_SOURCE
                if subcategory == FinancingSubcategoryEnum.EQUITY_CONTRIBUTION:
                    return TransactionPurpose.CAPITAL_SOURCE

                # Partner returns/fees: Capital costs going OUT to partners = FINANCING_SERVICE
                elif (
                    subcategory
                    in [
                        FinancingSubcategoryEnum.EQUITY_DISTRIBUTION,  # Distributions to partners
                        FinancingSubcategoryEnum.PREFERRED_RETURN,  # Preferred return payments
                        FinancingSubcategoryEnum.PROMOTE,  # GP promote/carry payments
                    ]
                ):
                    return TransactionPurpose.FINANCING_SERVICE

                # All other financing: Debt proceeds (positive) vs debt service (negative)
                elif amount > 0:  # Positive = proceeds/draws (debt proceeds)
                    return TransactionPurpose.CAPITAL_SOURCE
                else:  # Negative = service payments (debt service)
                    return TransactionPurpose.FINANCING_SERVICE

        except (ImportError, AttributeError):
            pass  # Fall through to category-based determination

        # Fall back to category-based determination
        return FlowPurposeMapper.determine_purpose(category, amount)

    @staticmethod
    def is_operating_flow(purpose: TransactionPurpose) -> bool:
        """Check if a transaction purpose represents operating activity."""
        return purpose == TransactionPurpose.OPERATING

    @staticmethod
    def is_capital_flow(purpose: TransactionPurpose) -> bool:
        """Check if a transaction purpose represents capital activity."""
        return purpose in (
            TransactionPurpose.CAPITAL_USE,
            TransactionPurpose.CAPITAL_SOURCE,
        )

    @staticmethod
    def is_financing_flow(purpose: TransactionPurpose) -> bool:
        """Check if a transaction purpose represents financing activity."""
        return purpose == TransactionPurpose.FINANCING_SERVICE

    @staticmethod
    def generate_sql_flow_purpose_case() -> str:
        """
        Generate SQL CASE statement for flow purpose mapping.

        This allows DuckDB to handle flow purpose calculation natively
        instead of expensive Python enum processing, providing
        performance improvements for bulk operations.

        Returns:
            SQL CASE statement string for flow purpose determination
        """
        return """
        CASE 
            WHEN category = 'Revenue' THEN 'Operating'
            WHEN category = 'Expense' THEN 'Operating'
            WHEN category = 'Capital' AND amount < 0 THEN 'Capital Use'
            WHEN category = 'Capital' AND amount >= 0 THEN 'Capital Source' 
            WHEN category = 'Financing' AND amount < 0 THEN 'Financing Service'
            WHEN category = 'Financing' AND amount >= 0 THEN 'Capital Source'
            WHEN category = 'Valuation' THEN 'Valuation'
            ELSE 'Operating'
        END
        """.strip()

    @staticmethod
    def generate_optimized_raw_data(
        records: List["TransactionRecord"],
    ) -> Dict[str, List]:
        """
        Generate minimal raw data structure optimized for SQL-native processing.

        Avoids expensive Python object creation and enum processing by creating
        a minimal DataFrame with only the essential data needed for SQL operations.

        Args:
            records: List of transaction records to process

        Returns:
            Dictionary of lists suitable for DataFrame construction
        """
        return {
            "date": [r.date for r in records],
            "amount": [float(r.amount) for r in records],
            "category": [r.category.value for r in records],
            "subcategory": [r.subcategory.value for r in records],
            "item_name": [r.item_name for r in records],
            "source_id_str": [str(r.source_id) for r in records],
            "asset_id_str": [str(r.asset_id) for r in records],
            "pass_num": [r.pass_num for r in records],
            "deal_id_str": [str(r.deal_id) if r.deal_id else None for r in records],
            "entity_id_str": [
                str(r.entity_id) if r.entity_id else None for r in records
            ],
            "entity_type": [r.entity_type for r in records],
        }
