# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Flow purpose mapping utilities for the transactional ledger.

This module provides logic for mapping transaction categories and amounts
to TransactionPurpose values, following standard real estate accounting
principles and the existing Performa categorization system.
"""

from performa.core.primitives import TransactionPurpose


class FlowPurposeMapper:
    """
    Pure utility class for mapping categories to transaction purposes.
    
    No state, no __init__ - only static methods following v3.2 patterns.
    Encapsulates business rules for flow classification based on
    standard real estate accounting principles.
    """
    
    @staticmethod
    def determine_purpose(category: str, amount: float) -> TransactionPurpose:
        """
        Determine TransactionPurpose based on category and amount sign.
        
        Args:
            category: Primary transaction category (Revenue, Expense, Capital, etc.)
            amount: Transaction amount (sign indicates direction)
            
        Returns:
            TransactionPurpose enum value
            
        Rules:
            - Revenue/Expense categories -> OPERATING
            - Capital category -> CAPITAL_USE (outflow) or CAPITAL_SOURCE (inflow)  
            - Financing category -> FINANCING_SERVICE
            - TI/LC subcategories -> CAPITAL_USE (regardless of amount sign)
        """
        category_lower = category.lower().strip()
        
        # Revenue and expenses are always operating
        if category_lower in ('revenue', 'expense', 'operating'):
            return TransactionPurpose.OPERATING
        
        # Financing flows are debt service
        if category_lower in ('financing', 'debt'):
            return TransactionPurpose.FINANCING_SERVICE
        
        # Capital flows depend on direction
        if category_lower == 'capital':
            # Outflows are capital deployment, inflows are capital sources
            if amount < 0:
                return TransactionPurpose.CAPITAL_USE
            else:
                return TransactionPurpose.CAPITAL_SOURCE
        
        # Default to operating for unknown categories
        return TransactionPurpose.OPERATING
    
    @staticmethod
    def determine_purpose_with_subcategory(
        category: str, 
        subcategory: str, 
        amount: float
    ) -> TransactionPurpose:
        """
        Enhanced purpose determination considering subcategory.
        
        Args:
            category: Primary transaction category
            subcategory: Secondary categorization
            amount: Transaction amount
            
        Returns:
            TransactionPurpose enum value
            
        Special Rules:
            - TI (Tenant Improvements) -> CAPITAL_USE
            - LC (Leasing Commissions) -> CAPITAL_USE
            - Acquisition-related -> CAPITAL_USE
            - Property sales -> CAPITAL_SOURCE
        """
        subcategory_lower = subcategory.lower().strip()
        
        # TI and LC are always capital use (Phase 2.5 requirement)
        # Use word boundaries to avoid false matches (e.g., "utilities" contains "ti")
        # FIXME: clean this up with enums/categories/subcategories
        ti_lc_patterns = [
            ' ti ', 'ti ', ' ti', '^ti$',  # TI as standalone word
            'tenant improvement', 'tenant_improvement',
            'leasing commission', 'leasing_commission', 
            ' lc ', 'lc ', ' lc', '^lc$'   # LC as standalone word
        ]
        
        # Check if any TI/LC pattern matches
        for pattern in ti_lc_patterns:
            if pattern.startswith('^') and pattern.endswith('$'):
                # Exact match
                if subcategory_lower == pattern[1:-1]:
                    return TransactionPurpose.CAPITAL_USE
            elif pattern in subcategory_lower:
                return TransactionPurpose.CAPITAL_USE
        
        # Acquisition costs are capital use
        if any(term in subcategory_lower for term in ['acquisition', 'purchase', 'closing']):
            return TransactionPurpose.CAPITAL_USE
        
        # Property sales are capital source
        if any(term in subcategory_lower for term in ['sale', 'disposition', 'proceeds']):
            return TransactionPurpose.CAPITAL_SOURCE
        
        # Fall back to category-based determination
        return FlowPurposeMapper.determine_purpose(category, amount)
    
    @staticmethod
    def is_operating_flow(purpose: TransactionPurpose) -> bool:
        """Check if a transaction purpose represents operating activity."""
        return purpose == TransactionPurpose.OPERATING
    
    @staticmethod
    def is_capital_flow(purpose: TransactionPurpose) -> bool:
        """Check if a transaction purpose represents capital activity."""
        return purpose in (TransactionPurpose.CAPITAL_USE, TransactionPurpose.CAPITAL_SOURCE)
    
    @staticmethod
    def is_financing_flow(purpose: TransactionPurpose) -> bool:
        """Check if a transaction purpose represents financing activity."""
        return purpose == TransactionPurpose.FINANCING_SERVICE
