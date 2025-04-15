from datetime import date
from typing import Dict, List

import pandas as pd
from pydantic import Field

from ..core._cash_flow import CashFlowModel
from ..core._model import Model
from ..core._settings import GlobalSettings
from ..core._timeline import Timeline
from ._property import Property


class CashFlowAnalysis(Model):
    """
    Orchestration layer for a property's cash flow analysis.
    """

    property: Property
    settings: GlobalSettings = Field(default_factory=GlobalSettings)

    # timing
    analysis_start_date: date
    analysis_end_date: date

    # FIXME: These will need to be implemented:
    
    def create_timeline(self) -> Timeline:
        """Creates a unified timeline for all cash flows based on analysis dates."""
        # Generate appropriate Timeline object for the analysis period
    
    def collect_revenue_models(self) -> List[CashFlowModel]:
        """Extracts all revenue models from the property."""
        # Extract revenue models from property
    
    def collect_expense_models(self) -> List[CashFlowModel]:
        """Extracts all expense models from the property."""
        # Extract expense models from property
    
    def collect_other_cash_flow_models(self) -> List[CashFlowModel]:
        """Extracts any other cash flow models (capital, investment, etc.)."""
        # Extract other cash flow models
    
    def process_cash_flow_model(self, model: CashFlowModel) -> pd.Series:
        """Process a single cash flow model."""
        # Apply appropriate resolution, alignment and processing
    
    def compute_cash_flows(self) -> Dict[str, pd.Series]:
        """Compute all cash flows, organized by category."""
        # Process all models and organize into categories
    
    def create_cash_flow_dataframe(self) -> pd.DataFrame:
        """Create the master cash flow dataframe."""
        # Combine all series into a structured dataframe
    
    def net_operating_income(self) -> pd.Series:
        """Calculate net operating income series."""
        # Revenue - OpEx
    
    def cash_flow_from_operations(self) -> pd.Series:
        """Calculate cash flow from operations."""
        # NOI - CapEx - other adjustments
    
    def unlevered_cash_flow(self) -> pd.Series:
        """Calculate unlevered cash flow."""
        # Cash flow before debt service
    
    def debt_service(self) -> pd.Series:
        """Calculate debt service."""
        # Aggregate debt service from property
    
    def levered_cash_flow(self) -> pd.Series:
        """Calculate levered cash flow."""
        # Unlevered CF - Debt Service

    # TODO: add methods for calculating cash flow from revenues and expenses definitions
    # NOTE: be mindful of the order of operations for calculating cash flow and dependency graphs
