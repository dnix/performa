from datetime import date
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import UUID

import numpy as np
import pandas as pd

from ..core._cash_flow import CashFlowModel
from ..core._enums import ExpenseSubcategoryEnum, UnitOfMeasureEnum
from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat


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
    parent_item: Optional[str] = None  # For optional grouping
    # TODO: rename parent_item to group?


class OpExItem(ExpenseItem):
    """Operating expenses like utilities"""
    subcategory: ExpenseSubcategoryEnum = "OpEx"
    growth_rate: Optional[float] = None  # annual growth rate (e.g., 0.02 for 2% growth)
    # TODO: future support lookup of GrowthRates instance
    # TODO: maybe growth rate is passed by orchestration layer too?
    # Occupancy rate will be provided by the orchestration layer via compute_cf parameters.
    variable_ratio: Optional[FloatBetween0And1] = None  # Default is not variable.
    recoverable_ratio: Optional[FloatBetween0And1] = 1.0  # Default is 100% recoverable.
    # FIXME: confirm we want 100% recoverable by default

    @property
    def is_variable(self) -> bool:
        """Check if the expense is variable."""
        return self.variable_ratio is not None

    @property
    def is_recoverable(self) -> bool:
        """Check if the expense is recoverable."""
        return self.recoverable_ratio is not None

    def compute_cf(
        self,
        occupancy_rate: Optional[float] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Union[float, int, str, date, pd.Series, Dict, Any]]] = None
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
            occupancy_rate: Optional occupancy rate (as a float, typically 0-1) 
                            to adjust variable portions of the expense.
            lookup_fn: Function provided by the analysis engine to resolve 
                       references (UUIDs, property attributes, or AggregateLineKeys).
                       
        Returns:
            A pandas Series representing the monthly cash flow for this expense item.
            
        Raises:
            ValueError: If `reference` is set but `lookup_fn` is not provided.
            TypeError: If the type returned by `lookup_fn` is incompatible with the
                       `unit_of_measure` or calculation logic.
        """
        calculated_flow: pd.Series
        base_value_source: Optional[Union[float, int, pd.Series]] = None

        if self.reference is not None:
            if lookup_fn is None:
                raise ValueError(f"Reference '{self.reference}' is set for OpExItem '{self.name}', but no lookup_fn was provided.")
            
            looked_up_value = lookup_fn(self.reference)
            
            if isinstance(looked_up_value, pd.Series):
                # --- Handle Reference to Aggregate (Series) --- 
                # Assume the looked_up_value is the base series (e.g., Total Revenue)
                base_series = looked_up_value
                
                # Apply unit_of_measure logic if it involves the reference
                # Example: If OpEx is 5% of Total Revenue
                if self.unit_of_measure == UnitOfMeasureEnum.BY_PERCENT and isinstance(self.value, (float, int)):
                    calculated_flow = base_series * (self.value / 100.0)
                elif self.unit_of_measure == UnitOfMeasureEnum.BY_FACTOR and isinstance(self.value, (float, int)):
                     calculated_flow = base_series * self.value
                # TODO: Add handling for other UnitOfMeasureEnum cases if they can logically apply to a Series reference
                # If unit_of_measure is AMOUNT or PER_UNIT, referencing a Series doesn't make sense?
                # For now, assume direct use or %/Factor
                elif self.unit_of_measure == UnitOfMeasureEnum.AMOUNT:
                     # If value is an amount, does referencing a series make sense? Maybe use self.value directly?
                     # Let's assume for now OpEx defined as % or Factor of an aggregate uses that logic,
                     # otherwise, if reference is a series but UoM isn't %/Factor, it's ambiguous.
                     # We will fall back to the standard compute_cf which expects self.value as the primary driver.
                      calculated_flow = super().compute_cf(lookup_fn=lookup_fn) # Re-call super, letting it handle self.value
                      print(f"Warning: OpExItem '{self.name}' referenced an aggregate series '{self.reference}' but UnitOfMeasure was '{self.unit_of_measure}'. Using standard value calculation.")
                else: 
                    # Default case if reference is Series but UoM isn't handled above
                    # This might indicate an unsupported configuration
                    raise TypeError(f"OpExItem '{self.name}' referenced an aggregate series '{self.reference}' with an unsupported UnitOfMeasure '{self.unit_of_measure}'.")
                
                # Ensure index alignment with the analysis timeline (important!) 
                # We need the timeline from the model itself if available, otherwise it's hard to align.
                if hasattr(self, 'timeline') and self.timeline is not None:
                    target_periods = self.timeline.period_index
                    calculated_flow = calculated_flow.reindex(target_periods, fill_value=0.0)
                else:
                    # If the OpExItem itself doesn't have a timeline, aligning the referenced series is ambiguous.
                    # The analysis layer should handle final alignment. We pass the raw calculation.
                    pass 
                
                base_value_source = looked_up_value # Store for potential later use/debugging

            elif isinstance(looked_up_value, (float, int, str, date, dict)): 
                # --- Handle Reference to Scalar or compatible type --- 
                # Let the parent CashFlowModel compute_cf handle scalar references 
                # (e.g., property area for $/Unit calculations)
                calculated_flow = super().compute_cf(lookup_fn=lookup_fn)
                base_value_source = looked_up_value
            else:
                 raise TypeError(f"OpExItem '{self.name}' received an unexpected type ({type(looked_up_value)}) from lookup_fn for reference '{self.reference}'.")
        else:
            # --- No Reference --- 
            # Compute the base cash flow using the parent method based on self.value/timeline
            calculated_flow = super().compute_cf(lookup_fn=lookup_fn)

        # --- Apply Adjustments (Growth, Occupancy) --- 
        
        # Apply growth rate adjustment to the calculated flow.
        if self.growth_rate is not None:
            # Ensure we are working with a numeric series
            if pd.api.types.is_numeric_dtype(calculated_flow):
                months = np.arange(len(calculated_flow))
                # Ensure growth rate is treated as float for division
                annual_growth_rate = float(self.growth_rate)
                growth_factors = np.power(1 + (annual_growth_rate / 12), months)
                # Apply growth factor
                calculated_flow = calculated_flow * growth_factors
            else:
                print(f"Warning: Cannot apply growth rate to non-numeric series for OpExItem '{self.name}'.")

        # Apply occupancy adjustment if applicable.
        if occupancy_rate is not None and self.is_variable:
             # Ensure we are working with a numeric series
             if pd.api.types.is_numeric_dtype(calculated_flow) and self.variable_ratio is not None:
                 variable_ratio = self.variable_ratio  # e.g., 0.3 for 30% variability
                 fixed_ratio = 1.0 - variable_ratio
                 # Ensure occupancy_rate is float
                 current_occupancy = float(occupancy_rate)
                 adjustment_ratio = fixed_ratio + (variable_ratio * current_occupancy)
                 calculated_flow = calculated_flow * adjustment_ratio
             else:
                 print(f"Warning: Cannot apply occupancy adjustment to non-numeric series or missing variable_ratio for OpExItem '{self.name}'.")
        
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
    def total_annual_expenses(self) -> PositiveFloat:
        """
        Calculate total annual base expenses by summing the value field of each expense item.
        """
        return sum(item.value for item in self.expense_items)

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

    @property
    def total_capex(self) -> PositiveFloat:
        """
        Calculate the total capital expenditure amount by summing the value field of each capex item.
        """
        return sum(item.value for item in self.expense_items)


class Expenses(Model):
    """
    Collection of property operating expenses and capital expenditures.
    """
    operating_expenses: OperatingExpenses
    capital_expenses: CapitalExpenses
    # TODO: other_expenses?
