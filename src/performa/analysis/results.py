# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Asset-level analysis result models.

This module provides result classes for asset-only analysis, maintaining
clean module boundaries by keeping deal-related results in the deal module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List

import pandas as pd

from performa.core.ledger import LedgerBuilder, LedgerQuery
from performa.core.primitives import Timeline

if TYPE_CHECKING:
    from performa.analysis.scenario import AnalysisScenarioBase
    from performa.core.base import PropertyBaseModel
    from performa.core.primitives import CashFlowModel


@dataclass
class AssetAnalysisResult:
    """
    Results from asset-level (unlevered) analysis.
    
    Contains both the new ledger-based results and the complete scenario
    for full backward compatibility and access to all analysis data.
    
    Attributes:
        ledger_builder: The builder instance that owns the transactional ledger
        noi: Net Operating Income time series
        property: Property model used in analysis
        timeline: Timeline used for the analysis
        scenario: The executed analysis scenario with full orchestrator access
        summary_df: Direct access to the cash flow summary DataFrame
        models: Direct access to all prepared CashFlowModel instances
    """
    
    # Ledger-based results
    ledger_builder: LedgerBuilder
    noi: pd.Series
    
    # Core inputs
    property: "PropertyBaseModel"
    timeline: Timeline
    
    # Full scenario and orchestrator access
    scenario: "AnalysisScenarioBase"  # Full scenario with _orchestrator
    summary_df: pd.DataFrame  # Direct access to cash flow summary
    models: List["CashFlowModel"]  # Direct access to all models
    
    @property
    def ledger(self) -> pd.DataFrame:
        """
        Convenience accessor for the current ledger.
        
        Returns:
            The complete transactional ledger DataFrame
            
        Note:
            The ledger is owned by the builder - this property provides
            convenient access without exposing the builder's internals.
        """
        return self.ledger_builder.get_current_ledger()
    
    def get_ledger_query(self):
        """
        Create a LedgerQuery for convenient ledger operations.
        
        Returns:
            LedgerQuery instance for the current ledger
        """
        return LedgerQuery(ledger=self.ledger)
    
    def summary_stats(self) -> dict:
        """
        Generate summary statistics for the analysis.
        
        Returns:
            Dictionary with key analysis metrics
        """
        stats = {
            'total_records': len(self.ledger),
            'analysis_periods': len(self.timeline.period_index),
            'noi_total': self.noi.sum() if not self.noi.empty else 0.0,
            'noi_average': self.noi.mean() if not self.noi.empty else 0.0,
        }
        
        # Add ledger statistics if available
        if not self.ledger.empty:
            query = self.get_ledger_query()
            purpose_summary = query.summary_by_purpose()
            stats['operating_flows'] = purpose_summary.loc['Operating', 'sum'] if 'Operating' in purpose_summary.index else 0.0
            stats['capital_flows'] = (
                purpose_summary.loc[['Capital Use', 'Capital Source'], 'sum'].sum() 
                if any(p in purpose_summary.index for p in ['Capital Use', 'Capital Source']) 
                else 0.0
            )
        
        return stats
    
    def __str__(self) -> str:
        """String representation showing key metrics."""
        stats = self.summary_stats()
        return (
            f"AssetAnalysisResult(\n"
            f"  NOI Total: ${stats['noi_total']:,.2f}\n"
            f"  NOI Average: ${stats['noi_average']:,.2f}\n"
            f"  Total Records: {stats['total_records']}\n"
            f"  Analysis Periods: {stats['analysis_periods']}\n"
            f")"
        )
