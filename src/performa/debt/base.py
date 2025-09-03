# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Base debt facility implementation as financing model.

This module provides the foundation for debt-ledger integration by creating
a parallel hierarchy for financing instruments that write to the ledger
without inheriting asset-level concerns from CashFlowModel.
"""

import warnings
from abc import abstractmethod
from typing import TYPE_CHECKING, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field

from ..core.ledger import SeriesMetadata
from ..core.primitives import (
    CalculationPhase,
    CashFlowCategoryEnum,
    FinancingSubcategoryEnum,
    Model,
    Timeline,
)

if TYPE_CHECKING:
    from performa.deal.orchestrator import DealContext

from .rates import InterestRate


class DebtFacilityBase(Model):
    """
    Base class for debt facilities as ledger participants.

    This is a parallel hierarchy to CashFlowModel, specifically designed for
    financing instruments that operate at the deal level rather than asset level.
    Provides the same ledger integration capabilities without asset-level concerns.

    Phase 1 Approach (Explicit Sizing):
    - Requires explicit loan_amount (no auto-sizing from ledger metrics)
    - Writes loan proceeds and debt service to ledger
    - Uses factory methods for convenient construction
    - Maintains architectural purity with single source of truth

    Phase 2 Future (Intelligent Sizing):
    - Will support auto-sizing from LTV/DSCR/debt yield constraints
    - Will query ledger for property value and NOI metrics
    - Will enable dynamic refinancing detection

    All debt facilities must implement:
    - _generate_debt_service(): Create amortization schedule
    - Any facility-specific validation logic

    The compute_cf() method handles:
    1. Writing loan proceeds to ledger (at origination)
    2. Writing debt service to ledger (each period)
    3. Returning debt service series for analysis results
    """

    # Core financing model fields
    uid: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(..., description="Facility name")

    # Required debt facility fields (Phase 1: Explicit)
    loan_amount: float = Field(..., gt=0, description="Loan principal amount")
    interest_rate: Union[float, InterestRate] = Field(
        ..., description="Annual interest rate (simple float or InterestRate object)"
    )
    loan_term_months: int = Field(..., gt=0, description="Loan term in months")

    @abstractmethod
    def _generate_debt_service(self, timeline: Timeline) -> pd.Series:
        """
        Generate debt service schedule for the loan.

        This method must be implemented by each specific debt facility type
        to handle their unique amortization patterns (e.g., fixed payment,
        interest-only periods, balloon payments, etc.).

        Args:
            timeline: Analysis timeline to generate schedule for

        Returns:
            pd.Series: Monthly debt service amounts indexed by timeline
        """
        pass

    def _get_effective_rate(
        self, period: pd.Period = None, index_curve: pd.Series = None
    ) -> float:
        """
        Get effective interest rate handling both float and InterestRate objects.

        Args:
            period: Optional period for floating rate calculations
            index_curve: Optional index curve for floating rate calculations

        Returns:
            float: Annual interest rate as decimal
        """
        if isinstance(self.interest_rate, (int, float)):
            return float(self.interest_rate)
        elif period is not None:
            return self.interest_rate.get_rate_for_period(period, index_curve)
        else:
            return self.interest_rate.effective_rate

    def compute_cf(self, context: "DealContext") -> pd.Series:
        """
        Compute debt cash flows and write ALL transactions to ledger.

        This method implements the core ledger integration by:
        1. Generating the debt service schedule
        2. Writing loan proceeds as positive inflow at origination
        3. Writing debt service as negative outflow each period
        4. Returning debt service series for analysis results

        All debt transactions are recorded in the ledger with proper metadata
        for full auditability and query capabilities.

        Args:
            context: Deal context containing ledger, timeline, and deal data

        Returns:
            pd.Series: Debt service schedule for aggregation
        """
        # Validate context for development deals
        if hasattr(self, "kind") and self.kind == "permanent":
            if context.deal and hasattr(context.deal, "is_development_deal"):
                if context.deal.is_development_deal:
                    # Check if this facility has refinance timing configured
                    has_timing = (
                        hasattr(self, "refinance_timing")
                        and self.refinance_timing is not None
                    )
                    if not has_timing:
                        warnings.warn(
                            f"PermanentFacility '{self.name}' used in development deal without "
                            f"refinance timing. The loan will fund on day 1 instead of after "
                            f"construction completion, creating INCORRECT leverage ratios.",
                            UserWarning,
                            stacklevel=2,
                        )

        timeline = context.timeline

        # Generate debt service schedule
        debt_service = self._generate_debt_service(timeline)

        # Write loan proceeds to ledger
        # Check if this facility has refinance timing (for permanent loans in development deals)
        funding_period = timeline.period_index[0]  # Default to first period

        if hasattr(self, "refinance_timing") and self.refinance_timing is not None:
            # Delay funding until refinance month
            refinance_idx = min(
                self.refinance_timing - 1, len(timeline.period_index) - 1
            )
            funding_period = timeline.period_index[refinance_idx]

        if self.loan_amount > 0:
            proceeds_series = pd.Series([self.loan_amount], index=[funding_period])

            proceeds_metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.FINANCING,
                subcategory=FinancingSubcategoryEnum.LOAN_PROCEEDS,
                item_name=f"{self.name} - Proceeds",
                source_id=self.uid,
                asset_id=context.deal.asset.uid,  # Clean access via DealContext
                pass_num=CalculationPhase.FINANCING.value,
            )
            context.ledger.add_series(proceeds_series, proceeds_metadata)

        # Write debt service to ledger (negative outflows)
        if not debt_service.empty and debt_service.sum() != 0:
            service_metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.FINANCING,
                subcategory=FinancingSubcategoryEnum.DEBT_SERVICE,
                item_name=f"{self.name} - Debt Service",
                source_id=self.uid,
                asset_id=context.deal.asset.uid,  # Clean access via DealContext
                pass_num=CalculationPhase.FINANCING.value,
            )
            # Debt service is outflow (negative in ledger)
            context.ledger.add_series(-debt_service, service_metadata)

        return debt_service
