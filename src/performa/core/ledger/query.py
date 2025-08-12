# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Query utilities for ledger data with Pydantic validation.

This module provides LedgerQuery for common ledger operations with
schema validation to ensure data integrity before query execution.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import pandas as pd
from pydantic import BaseModel, field_validator

from performa.core.primitives import TransactionPurpose


class LedgerQuery(BaseModel):
    """
    Query utilities for ledger data with Pydantic validation.
    
    Uses Pydantic for schema validation ensuring data integrity
    before any query operations. Pre-computes common masks for performance.
    """
    
    ledger: pd.DataFrame
    
    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True  # Allow pandas DataFrame
        validate_assignment = True
    
    @field_validator('ledger')
    @classmethod
    def validate_schema(cls, v: pd.DataFrame) -> pd.DataFrame:
        """Validate ledger has required columns."""
        required = ['date', 'amount', 'flow_purpose', 'category', 'subcategory']
        missing = [col for col in required if col not in v.columns]
        if missing:
            raise ValueError(f"Ledger missing required columns: {missing}")
        return v
    
    def __init__(self, **data):
        """Initialize with validation and pre-computed masks."""
        super().__init__(**data)
        
        # Pre-compute masks after validation for performance
        self._operating_mask = self.ledger['flow_purpose'] == TransactionPurpose.OPERATING.value
        self._capital_mask = self.ledger['flow_purpose'].isin([
            TransactionPurpose.CAPITAL_USE.value, 
            TransactionPurpose.CAPITAL_SOURCE.value
        ])
        self._financing_mask = self.ledger['flow_purpose'] == TransactionPurpose.FINANCING_SERVICE.value
        
        # Smart indexing for large ledgers
        if len(self.ledger) > 10000 and 'date' in self.ledger.columns:
            if not isinstance(self.ledger.index, pd.DatetimeIndex):
                # Only set index if not already using date index
                self.ledger = self.ledger.set_index('date', drop=False)
    
    def noi_by_period(self) -> pd.Series:
        """
        Calculate Net Operating Income (NOI) by period.
        
        Returns:
            Time series of NOI values
        """
        operating = self.ledger[self._operating_mask]
        if operating.empty:
            return pd.Series(dtype=float)
        
        return operating.groupby('date')['amount'].sum()
    
    def operating_flows(self) -> pd.DataFrame:
        """
        Filter to operating flows only.
        
        Returns:
            DataFrame containing only operating transactions
        """
        return self.ledger[self._operating_mask]
    
    def capital_flows(self) -> pd.DataFrame:
        """
        Filter to capital flows only.
        
        Returns:
            DataFrame containing only capital transactions
        """
        return self.ledger[self._capital_mask]
    
    def financing_flows(self) -> pd.DataFrame:
        """
        Filter to financing flows only.
        
        Returns:
            DataFrame containing only financing transactions
        """
        return self.ledger[self._financing_mask]
    
    def entity_flows(self, entity_id: UUID) -> pd.Series:
        """
        Get cash flows for specific entity.
        
        Args:
            entity_id: UUID of the entity
            
        Returns:
            Time series of cash flows for the entity
        """
        entity_flows = self.ledger[self.ledger['entity_id'] == entity_id]
        if entity_flows.empty:
            return pd.Series(dtype=float)
        
        return entity_flows.groupby('date')['amount'].sum()
    
    def irr_cash_flows(self, entity_id: Optional[UUID] = None) -> pd.Series:
        """
        Get cash flows for IRR calculation.
        
        Args:
            entity_id: Specific entity, or None for total project flows
            
        Returns:
            Time series suitable for IRR calculation
        """
        if entity_id:
            return self.entity_flows(entity_id)
        else:
            # Total project cash flows (capital flows only)
            capital_flows = self.ledger[self._capital_mask]
            if capital_flows.empty:
                return pd.Series(dtype=float)
            
            return capital_flows.groupby('date')['amount'].sum()
    
    def flows_by_category(self, category: str) -> pd.DataFrame:
        """
        Filter flows by category.
        
        Args:
            category: Category to filter by
            
        Returns:
            DataFrame of flows in the specified category
        """
        return self.ledger[self.ledger['category'] == category]
    
    def flows_by_subcategory(self, subcategory: str) -> pd.DataFrame:
        """
        Filter flows by subcategory.
        
        Args:
            subcategory: Subcategory to filter by
            
        Returns:
            DataFrame of flows in the specified subcategory
        """
        return self.ledger[self.ledger['subcategory'] == subcategory]
    
    def flows_by_asset(self, asset_id: UUID) -> pd.DataFrame:
        """
        Filter flows by asset.
        
        Args:
            asset_id: Asset UUID to filter by
            
        Returns:
            DataFrame of flows for the specified asset
        """
        return self.ledger[self.ledger['asset_id'] == asset_id]
    
    def flows_by_deal(self, deal_id: UUID) -> pd.DataFrame:
        """
        Filter flows by deal.
        
        Args:
            deal_id: Deal UUID to filter by
            
        Returns:
            DataFrame of flows for the specified deal
        """
        return self.ledger[self.ledger['deal_id'] == deal_id]
    
    def flows_by_pass(self, pass_num: int) -> pd.DataFrame:
        """
        Filter flows by calculation pass.
        
        Args:
            pass_num: Pass number (1 or 2)
            
        Returns:
            DataFrame of flows from the specified pass
        """
        return self.ledger[self.ledger['pass_num'] == pass_num]
    
    def summary_by_purpose(self) -> pd.DataFrame:
        """
        Summarize flows by transaction purpose.
        
        Returns:
            DataFrame with totals by flow_purpose
        """
        return self.ledger.groupby('flow_purpose')['amount'].agg(['sum', 'count', 'mean']).round(2)
    
    def summary_by_category(self) -> pd.DataFrame:
        """
        Summarize flows by category.
        
        Returns:
            DataFrame with totals by category
        """
        return self.ledger.groupby('category')['amount'].agg(['sum', 'count', 'mean']).round(2)
    
    def monthly_summary(self) -> pd.DataFrame:
        """
        Create monthly summary of all flows.
        
        Returns:
            DataFrame with monthly totals by flow_purpose
        """
        # Convert to monthly periods
        monthly_ledger = self.ledger.copy()
        monthly_ledger['month'] = pd.to_datetime(monthly_ledger['date']).dt.to_period('M')
        
        return monthly_ledger.groupby(['month', 'flow_purpose'])['amount'].sum().unstack(fill_value=0).round(2)
    
    def validate_completeness(self) -> dict:
        """
        Validate ledger completeness and return diagnostics.
        
        Returns:
            Dictionary with validation results
        """
        diagnostics = {
            'total_records': len(self.ledger),
            'date_range': {
                'start': self.ledger['date'].min() if not self.ledger.empty else None,
                'end': self.ledger['date'].max() if not self.ledger.empty else None
            },
            'missing_values': self.ledger.isnull().sum().to_dict(),
            'purpose_breakdown': self.ledger['flow_purpose'].value_counts().to_dict(),
            'zero_amounts': (self.ledger['amount'] == 0).sum(),
            'has_entities': self.ledger['entity_id'].notna().sum(),
            'pass_breakdown': self.ledger['pass_num'].value_counts().to_dict()
        }
        
        return diagnostics
