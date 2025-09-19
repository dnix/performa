# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Acquisition Analysis Specialist

This module provides the AcquisitionAnalyzer service that handles acquisition transactions,
initial project cost calculations, and deal fee processing for commercial real estate deals.

The AcquisitionAnalyzer is responsible for the acquisition phase of deal analysis, ensuring
that all initial costs are properly recorded in the ledger and that project costs are
calculated for downstream financing calculations.

Key capabilities:
- **Purchase Price Recording**: Records acquisition purchase price to ledger
- **Closing Costs Calculation**: Calculates and records closing costs
- **Project Cost Calculation**: Determines total initial project costs for financing
- **Deal Fee Processing**: Processes and records various deal fees

Example:
    ```python
    from performa.deal.analysis import AcquisitionAnalyzer

    # Create analyzer with deal context
    analyzer = AcquisitionAnalyzer(deal_context)

    # Process acquisition transactions
    analyzer.process()

    # Context now contains project_costs for financing calculations
    print(f"Total project costs: ${deal_context.project_costs:,.0f}")
    ```
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from performa.core.ledger.records import SeriesMetadata
from performa.core.primitives import (
    CalculationPhase,
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
)

from .base import AnalysisSpecialist

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class AcquisitionAnalyzer(AnalysisSpecialist):
    """
    Specialist service for processing acquisition transactions and initial project costs.

    This service handles the acquisition phase of deal analysis including purchase price
    recording, closing costs calculation, project cost determination, and deal fee processing.
    It ensures that all initial costs are properly recorded in the ledger and that total
    project costs are available for financing calculations.

    The AcquisitionAnalyzer is typically the first specialist to run in the deal analysis
    workflow, as it establishes the initial cost basis that downstream specialists need.

    Key responsibilities:
    - Calculate total initial project costs from acquisition and development
    - Record acquisition purchase price and closing costs to ledger
    - Process and record deal fees
    - Update context with project_costs for financing calculations

    Attributes inherited from AnalysisSpecialist:
    - context: DealContext with deal, timeline, settings, and ledger
    - deal, timeline, settings, ledger: Properties from context
    - queries: LedgerQueries for data access
    """

    def process(self) -> None:
        """
        Process acquisition transactions and calculate initial project costs.

        Updates context with project_costs for downstream financing calculations.
        Records all acquisition-related transactions to the ledger.
        """
        # Calculate initial project costs for financing
        project_costs = self._calculate_initial_project_costs()
        self.context.project_costs = project_costs

        # Add acquisition transactions to ledger
        self._add_acquisition_records()

        # Process deal fees separately for clarity
        self._add_deal_fees()

        logger.debug(
            f"Acquisition processing complete. Total project costs: ${project_costs:,.0f}"
        )

    def _calculate_initial_project_costs(self) -> float:
        """
        Calculate initial project costs from deal structure for financing sizing.

        Returns:
            Total initial project costs including acquisition and development
        """
        initial_project_costs = 0.0

        # Add acquisition costs if available
        if self.deal.acquisition:
            # Get acquisition value (can be scalar or Series)
            if isinstance(self.deal.acquisition.value, (int, float)):
                acquisition_value = self.deal.acquisition.value
            elif hasattr(self.deal.acquisition.value, "sum"):
                acquisition_value = self.deal.acquisition.value.sum()
            else:
                acquisition_value = 0.0

            initial_project_costs += acquisition_value

            # Add closing costs (percentage of acquisition value)
            if acquisition_value > 0 and self.deal.acquisition.closing_costs_rate:
                initial_project_costs += (
                    acquisition_value * self.deal.acquisition.closing_costs_rate
                )

        # Add renovation/development costs if available
        # TODO: Make this more robust - use proper type checking instead of hasattr
        if hasattr(self.deal.asset, "renovation_budget"):
            initial_project_costs += self.deal.asset.renovation_budget or 0.0
        elif hasattr(self.deal.asset, "construction_plan"):
            if hasattr(self.deal.asset.construction_plan, "total_cost"):
                initial_project_costs += (
                    self.deal.asset.construction_plan.total_cost or 0.0
                )

        return initial_project_costs

    def _add_acquisition_records(self) -> None:
        """
        Add acquisition purchase price and closing costs to ledger.
        """
        if not self.deal.acquisition:
            logger.debug("No acquisition terms to add to ledger")
            return

        try:
            acquisition_date = self.deal.acquisition.acquisition_date
            purchase_price = self.deal.acquisition.value
            closing_costs_rate = self.deal.acquisition.closing_costs_rate
        except AttributeError as e:
            logger.error(f"Failed to access acquisition attributes: {e}")
            return

        # Purchase price (negative amount representing outflow/use)
        acquisition_period = pd.Period(acquisition_date, freq="M")
        purchase_price_series = pd.Series(
            [-purchase_price],
            index=pd.PeriodIndex([acquisition_period], freq="M"),
            name="Purchase Price",
        )

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.CAPITAL,
            subcategory=CapitalSubcategoryEnum.PURCHASE_PRICE,
            item_name="Property Acquisition",
            source_id=str(self.deal.uid),
            asset_id=self.deal.asset.uid,
            pass_num=CalculationPhase.ACQUISITION.value,
        )
        self.ledger.add_series(purchase_price_series, metadata)
        logger.debug(f"Added acquisition purchase price: ${purchase_price:,.0f}")

        # Closing costs (negative amount representing outflow/use) - only if rate is provided
        if closing_costs_rate is not None and closing_costs_rate > 0:
            closing_costs = purchase_price * closing_costs_rate
            closing_costs_series = pd.Series(
                [-1 * closing_costs],
                index=pd.PeriodIndex([acquisition_period], freq="M"),
                name="Closing Costs",
            )

            metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.CAPITAL,
                subcategory=CapitalSubcategoryEnum.CLOSING_COSTS,
                item_name="Acquisition Closing Costs",
                source_id=str(self.deal.uid),
                asset_id=self.deal.asset.uid,
                pass_num=CalculationPhase.ACQUISITION.value,
            )
            self.ledger.add_series(closing_costs_series, metadata)
            logger.debug(f"Added acquisition closing costs: ${closing_costs:,.0f}")
        else:
            logger.debug("No closing costs rate provided - skipping closing costs")

    def _add_deal_fees(self) -> None:
        """
        Process and record deal fees to ledger.
        """
        if not self.deal.deal_fees:
            logger.debug("No deal fees to add")
            return

        logger.debug(f"Adding {len(self.deal.deal_fees)} deal fees")
        for fee in self.deal.deal_fees:
            try:
                fee_cf = fee.compute_cf(self.timeline)
                metadata = SeriesMetadata(
                    category=CashFlowCategoryEnum.CAPITAL,
                    subcategory=CapitalSubcategoryEnum.OTHER,
                    item_name=f"Fee - {fee.name}",
                    source_id=str(fee.uid),
                    asset_id=self.deal.asset.uid,
                    pass_num=CalculationPhase.ACQUISITION.value,
                )
                self.ledger.add_series(fee_cf, metadata)
                logger.debug(f"Added deal fee: {fee.name}")
            except Exception as e:
                logger.warning(f"Failed to add deal fee: {e}")
