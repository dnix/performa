import logging
from datetime import date
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Union,
)
from uuid import UUID

import pandas as pd

# Core imports
from ..core._cash_flow import CashFlowModel
from ..core._enums import (
    RevenueSubcategoryEnum,
    UnitOfMeasureEnum,
)
from ..core._settings import GlobalSettings  # Restore import

# from ..core._timeline import Timeline # Unused import
from ..core._types import (
    FloatBetween0And1,
)

# Asset-level imports needed
from ._growth_rates import GrowthRate

logger = logging.getLogger(__name__)


# --- Misc Income ---
class MiscIncome(CashFlowModel):
    """
    Represents miscellaneous income items like parking revenue, vending, antenna income, etc.
    
    (See original file for full docstring)
    """
    category: str = "Revenue"
    subcategory: RevenueSubcategoryEnum = "Miscellaneous"
    
    variable_ratio: Optional[FloatBetween0And1] = None
    growth_rate: Optional[GrowthRate] = None
    growth_start_date: Optional[date] = None
    
    @property
    def is_variable(self) -> bool:
        return self.variable_ratio is not None
    
    def compute_cf(
        self,
        occupancy_rate: Optional[float] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Union[float, int, str, date, pd.Series, Dict, Any]]] = None,
        global_settings: Optional[GlobalSettings] = None # Added for consistency
    ) -> pd.Series:
        # (Implementation kept from previous move)
        logger.debug(f"Computing cash flow for MiscIncome: '{self.name}' ({self.model_id})") 
        calculated_flow: pd.Series
        base_value_source: Optional[Union[float, int, pd.Series]] = None

        if self.reference is not None:
            if lookup_fn is None:
                raise ValueError(f"Reference '{self.reference}' is set for MiscIncome '{self.name}', but no lookup_fn was provided.")
            looked_up_value = lookup_fn(self.reference)
            
            if isinstance(looked_up_value, pd.Series):
                base_series = looked_up_value
                if self.unit_of_measure == UnitOfMeasureEnum.BY_PERCENT and isinstance(self.value, (float, int)):
                    calculated_flow = base_series * (self.value / 100.0)
                elif self.unit_of_measure == UnitOfMeasureEnum.BY_FACTOR and isinstance(self.value, (float, int)):
                     calculated_flow = base_series * self.value
                elif self.unit_of_measure == UnitOfMeasureEnum.AMOUNT:
                      calculated_flow = super().compute_cf(lookup_fn=lookup_fn)
                      logger.warning(f"MiscIncome '{self.name}' referenced aggregate series '{self.reference}' but UoM was '{self.unit_of_measure}'. Using standard calc.")
                else: 
                    raise TypeError(f"MiscIncome '{self.name}' referenced aggregate series '{self.reference}' with unsupported UoM '{self.unit_of_measure}'.")
                if hasattr(self, 'timeline') and self.timeline is not None:
                    calculated_flow = calculated_flow.reindex(self.timeline.period_index, fill_value=0.0)
                base_value_source = looked_up_value
                logger.debug(f"  Base value derived from looked up series ref '{self.reference}'.") 
            elif isinstance(looked_up_value, (float, int, str, date, dict)): 
                calculated_flow = super().compute_cf(lookup_fn=lookup_fn)
                base_value_source = looked_up_value
                logger.debug(f"  Base value derived from looked up scalar ref '{self.reference}': {base_value_source}") 
            else:
                 raise TypeError(f"MiscIncome '{self.name}' received unexpected type ({type(looked_up_value)}) from lookup_fn for ref '{self.reference}'.")
        else:
            calculated_flow = super().compute_cf(lookup_fn=lookup_fn)

        if self.growth_rate is not None:
            # Check if CashFlowModel has _apply_compounding_growth before calling
            if hasattr(self, '_apply_compounding_growth'):
                 effective_growth_start = self.growth_start_date or self.timeline.start_date.to_timestamp().date()
                 logger.debug(f"  Applying growth profile '{self.growth_rate.name}' starting from {effective_growth_start}.")
                 calculated_flow = self._apply_compounding_growth(
                     base_series=calculated_flow,
                     growth_profile=self.growth_rate,
                     growth_start_date=effective_growth_start
                 )
            else:
                 logger.warning(f"MiscIncome '{self.name}' has growth_rate but _apply_compounding_growth method not found.")
        
        if occupancy_rate is not None and self.is_variable:
             if pd.api.types.is_numeric_dtype(calculated_flow) and self.variable_ratio is not None:
                 variable_ratio = self.variable_ratio
                 fixed_ratio = 1.0 - variable_ratio
                 adjustment_ratio = fixed_ratio + (variable_ratio * float(occupancy_rate)) 
                 calculated_flow = calculated_flow * adjustment_ratio
             else:
                 logger.warning(f"Cannot apply occupancy adjustment to non-numeric series or missing var_ratio for MiscIncome '{self.name}'.")
        
        logger.debug(f"Finished computing cash flow for MiscIncome: '{self.name}'.") 
        return calculated_flow 