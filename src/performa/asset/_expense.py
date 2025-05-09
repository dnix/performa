from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import UUID

import pandas as pd

from ..core._cash_flow import CashFlowModel
from ..core._enums import ExpenseSubcategoryEnum, UnitOfMeasureEnum
from ..core._model import Model
from ..core._settings import GlobalSettings
from ..core._types import FloatBetween0And1
from ._growth_rates import GrowthRate

logger = logging.getLogger(__name__)


class ExpenseItem(CashFlowModel):
    """
    Base class for all expense items.

    Inherits from CashFlowModel and includes standard attributes like `value`,
    `timeline`, `unit_of_measure`, `reference`, etc.

    The `reference` attribute, if a string, can refer to either:
      - An attribute of the `Property` object (e.g., "net_rentable_area").
      - The string value of an `AggregateLineKey` enum member (e.g., "Total Effective Gross Income").
      Handling of the looked-up value depends on the `compute_cf` implementation.
    """

    category: str = "Expense"  # TODO: enum?
    subcategory: ExpenseSubcategoryEnum  # NOTE: instead of expense_kind
    group: Optional[str] = None  # For optional grouping (formerly parent_item)


class OpExItem(ExpenseItem):
    """Operating expenses like utilities"""

    subcategory: ExpenseSubcategoryEnum = "OpEx"
    growth_rate: Optional[GrowthRate] = None  # Growth profile for the expense
    growth_start_date: Optional[date] = None  # Date from which growth starts applying
    # TODO: maybe growth rate is passed by orchestration layer too?
    # Occupancy rate will be provided by the orchestration layer via compute_cf parameters.
    variable_ratio: Optional[FloatBetween0And1] = None  # Default is not variable.
    recoverable_ratio: Optional[FloatBetween0And1] = (
        0.0  # Default is 0% recoverable (safer default).
    )

    @property
    def is_variable(self) -> bool:
        """Check if the expense is variable."""
        return self.variable_ratio is not None

    @property
    def is_recoverable(self) -> bool:
        """Check if the expense is recoverable."""
        return (
            self.recoverable_ratio is not None and self.recoverable_ratio > 0
        )  # Check > 0

    def compute_cf(
        self,
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        lookup_fn: Optional[
            Callable[
                [Union[str, UUID]], Union[float, int, str, date, pd.Series, Dict, Any]
            ]
        ] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> pd.Series:
        """
        Compute the cash flow for the operating expense.

        Handles base value calculation (potentially using `reference` lookup),
        growth rate application, and occupancy adjustments.

        If `self.reference` is set and `lookup_fn` is provided:
          - If the lookup returns a pd.Series (e.g., an AggregateLineKey value):
            Uses the series as the base, potentially applying unit_of_measure
            factors (like percentage).
          - If the lookup returns a scalar:
            Passes the lookup to `super().compute_cf` to handle scalar-based
            calculations (e.g., $/Unit based on property area).
        If `self.reference` is not set, calculates based on `self.value` and `self.timeline`.

        Args:
            occupancy_rate: Optional occupancy rate (float or Series, typically 0-1)
                            to adjust variable portions of the expense.
            lookup_fn: Function provided by the analysis engine to resolve
                       references (UUIDs, property attributes, or AggregateLineKeys).
            global_settings: Optional global settings for analysis context (e.g., dates).

        Returns:
            A pandas Series representing the monthly cash flow for this expense item.

        Raises:
            ValueError: If `reference` is set but `lookup_fn` is not provided.
            TypeError: If the type returned by `lookup_fn` is incompatible with the
                       `unit_of_measure` or calculation logic.
        """
        logger.debug(
            f"Computing cash flow for OpExItem: '{self.name}' ({self.model_id})"
        )  # DEBUG: Entry
        calculated_flow: pd.Series
        base_value_source: Optional[Union[float, int, pd.Series]] = None

        # --- Determine Base Flow (Handles Reference) ---
        logger.debug(
            f"  Reference: {self.reference}, UnitOfMeasure: {self.unit_of_measure}"
        )  # DEBUG: Input info
        if self.reference is not None:
            if lookup_fn is None:
                raise ValueError(
                    f"Reference '{self.reference}' is set for OpExItem '{self.name}', but no lookup_fn was provided."
                )

            looked_up_value = lookup_fn(self.reference)

            if isinstance(looked_up_value, pd.Series):
                # --- Handle Reference to Aggregate (Series) ---
                # Assume the looked_up_value is the base series (e.g., Total Revenue)
                base_series = looked_up_value

                # Apply unit_of_measure logic if it involves the reference
                # Example: If OpEx is 5% of Total Revenue
                if self.unit_of_measure == UnitOfMeasureEnum.BY_PERCENT and isinstance(
                    self.value, (float, int)
                ):
                    calculated_flow = base_series * (self.value / 100.0)
                elif self.unit_of_measure == UnitOfMeasureEnum.BY_FACTOR and isinstance(
                    self.value, (float, int)
                ):
                    calculated_flow = base_series * self.value
                # TODO: Add handling for other UnitOfMeasureEnum cases if they can logically apply to a Series reference
                # If unit_of_measure is AMOUNT or PER_UNIT, referencing a Series doesn't make sense?
                # For now, assume direct use or %/Factor
                elif self.unit_of_measure == UnitOfMeasureEnum.AMOUNT:
                    # If value is an amount, does referencing a series make sense? Maybe use self.value directly?
                    # Let's assume for now OpEx defined as % or Factor of an aggregate uses that logic,
                    # otherwise, if reference is a series but UoM isn't %/Factor, it's ambiguous.
                    # We will fall back to the standard compute_cf which expects self.value as the primary driver.
                    calculated_flow = super().compute_cf(
                        lookup_fn=lookup_fn
                    )  # Re-call super, letting it handle self.value
                    logger.warning(
                        f"OpExItem '{self.name}' referenced an aggregate series '{self.reference}' but UnitOfMeasure was '{self.unit_of_measure}'. Using standard value calculation."
                    )
                else:
                    # Default case if reference is Series but UoM isn't handled above
                    # This might indicate an unsupported configuration
                    raise TypeError(
                        f"OpExItem '{self.name}' referenced an aggregate series '{self.reference}' with an unsupported UnitOfMeasure '{self.unit_of_measure}'."
                    )

                # Ensure index alignment with the analysis timeline (important!)
                # We need the timeline from the model itself if available, otherwise it's hard to align.
                if hasattr(self, "timeline") and self.timeline is not None:
                    target_periods = self.timeline.period_index
                    calculated_flow = calculated_flow.reindex(
                        target_periods, fill_value=0.0
                    )
                else:
                    # If the OpExItem itself doesn't have a timeline, aligning the referenced series is ambiguous.
                    # The analysis layer should handle final alignment. We pass the raw calculation.
                    pass

                base_value_source = (
                    looked_up_value  # Store for potential later use/debugging
                )
            elif isinstance(looked_up_value, (float, int, str, date, dict)):
                # --- Handle Reference to Scalar or compatible type ---
                # Let the parent CashFlowModel compute_cf handle scalar references
                # (e.g., property area for $/Unit calculations)
                calculated_flow = super().compute_cf(lookup_fn=lookup_fn)
                base_value_source = looked_up_value
            else:
                raise TypeError(
                    f"OpExItem '{self.name}' received an unexpected type ({type(looked_up_value)}) from lookup_fn for reference '{self.reference}'."
                )
            logger.debug(
                f"  Base flow determined via reference. Type: {type(base_value_source).__name__}"
            )  # DEBUG: Reference outcome
        else:
            # --- No Reference ---
            # Compute the base cash flow using the parent method based on self.value/timeline
            logger.debug(
                "  No reference set. Calculating base from self.value."
            )  # DEBUG: No reference
            calculated_flow = super().compute_cf(lookup_fn=lookup_fn)

        # --- Apply Adjustments (Growth, Occupancy) ---
        logger.debug(
            "  Applying growth and occupancy adjustments."
        )  # DEBUG: Adjustments start
        # --- Apply Growth (Using Helper - Placeholder for Step 4) ---
        if self.growth_rate is not None:
            # Determine the start date for growth application
            # Use the specific growth_start_date if provided, otherwise default to the item's timeline start
            effective_growth_start = (
                self.growth_start_date or self.timeline.start_date.to_timestamp().date()
            )
            logger.debug(
                f"  Applying growth profile '{self.growth_rate.name}' starting from {effective_growth_start}."
            )
            calculated_flow = self._apply_compounding_growth(
                base_series=calculated_flow,
                growth_profile=self.growth_rate,
                growth_start_date=effective_growth_start,
            )
        else:
            logger.debug("  No growth profile specified.")

        # --- Apply Occupancy Adjustment for Variable Portion ---
        if (
            self.is_variable
            and occupancy_rate is not None
            and self.variable_ratio is not None
        ):
            if pd.api.types.is_numeric_dtype(calculated_flow):
                logger.debug(
                    f"  Applying actual variable expense adjustment (Ratio: {self.variable_ratio*100:.1f}%)"
                )
                fixed_ratio = 1.0 - self.variable_ratio

                # Handle scalar or Series occupancy rate
                if isinstance(occupancy_rate, pd.Series):
                    # Align occupancy series to the calculated_flow index, forward fill for safety
                    aligned_occupancy = occupancy_rate.reindex(
                        calculated_flow.index, method="ffill"
                    ).fillna(1.0)
                    adjustment_ratio = fixed_ratio + (
                        self.variable_ratio * aligned_occupancy
                    )
                    logger.debug(
                        f"    Using occupancy Series (Min: {aligned_occupancy.min():.1%}, Max: {aligned_occupancy.max():.1%})"
                    )
                else:  # Assume float
                    # Ensure occupancy_rate is treated as float for calculation
                    occ_rate = float(occupancy_rate)
                    adjustment_ratio = fixed_ratio + (self.variable_ratio * occ_rate)
                    logger.debug(f"    Using scalar occupancy: {occ_rate:.1%})")

                calculated_flow = calculated_flow * adjustment_ratio
            else:
                logger.warning(
                    f"Cannot apply occupancy adjustment to non-numeric series for OpExItem '{self.name}'. Calculated flow type: {calculated_flow.dtype}"
                )
        elif self.is_variable and occupancy_rate is None:
            logger.warning(
                f"OpExItem '{self.name}' is variable, but no occupancy_rate was provided for adjustment. Expense calculated without variable adjustment."
            )

        # Gross-up should be handled at the Recovery calculation level.

        logger.debug(
            f"Finished computing cash flow for OpExItem: '{self.name}'. Final Sum: {calculated_flow.sum():.2f}"
        )  # DEBUG: Exit
        return calculated_flow


class CapExItem(ExpenseItem):
    """Capital expenditures with timeline"""

    subcategory: ExpenseSubcategoryEnum = "CapEx"

    value: Union[pd.Series, Dict, List]  # no scalar values allowed


class OperatingExpenses(Model):
    """
    Collection of property operating expenses.

    Attributes:
        expense_items: List of operational expense items.
    """

    expense_items: List[OpExItem]

    @property
    def recoverable_expenses(self) -> List[ExpenseItem]:
        """
        Get list of recoverable expenses.
        """
        return [item for item in self.expense_items if item.is_recoverable]


class CapitalExpenses(Model):
    """
    Collection of capital improvements/investments.

    Attributes:
        expense_items: List of capital expenditure items.
    """

    expense_items: List[CapExItem]


class Expenses(Model):
    """
    Collection of property operating expenses and capital expenditures.
    """

    operating_expenses: OperatingExpenses
    capital_expenses: CapitalExpenses
    # TODO: other_expenses?
