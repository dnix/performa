"""
Reusable Pydantic validation utilities for common patterns across the codebase.

This module provides standardized validators for:
- Time-based validations (duration, date ordering)
- Mutual exclusivity (either/or requirements)
- Conditional requirements (if X then Y)
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from pydantic import model_validator


class ValidationMixin:
    """
    Mixin class providing reusable validation methods for Pydantic models.
    
    This class can be inherited alongside Pydantic Model to add common
    validation patterns without code duplication.
    """
    
    @classmethod
    def validate_either_or_required(
        cls, 
        data: Dict[str, Any], 
        field_a: str, 
        field_b: str,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate that exactly one of two fields is provided.
        
        Args:
            data: Model data dictionary
            field_a: First field name
            field_b: Second field name
            error_message: Custom error message
            
        Returns:
            Validated data dictionary
            
        Raises:
            ValueError: If neither or both fields are provided
        """
        value_a = data.get(field_a)
        value_b = data.get(field_b)
        
        if value_a is None and value_b is None:
            msg = error_message or f"Either {field_a} or {field_b} must be provided"
            raise ValueError(msg)
            
        if value_a is not None and value_b is not None:
            msg = error_message or f"Cannot provide both {field_a} and {field_b}"
            raise ValueError(msg)
            
        return data
    
    @classmethod
    def validate_date_ordering(
        cls,
        data: Dict[str, Any],
        start_field: str,
        end_field: str,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate that end_date is after start_date.
        
        Args:
            data: Model data dictionary
            start_field: Name of start date field
            end_field: Name of end date field
            error_message: Custom error message
            
        Returns:
            Validated data dictionary
            
        Raises:
            ValueError: If end_date is not after start_date
        """
        start_date = data.get(start_field)
        end_date = data.get(end_field)
        
        if start_date is not None and end_date is not None:
            if end_date <= start_date:
                msg = error_message or f"{end_field} must be after {start_field}"
                raise ValueError(msg)
                
        return data
    
    @classmethod
    def validate_conditional_requirement(
        cls,
        data: Dict[str, Any],
        condition_field: str,
        condition_values: Union[Any, List[Any]],
        required_field: str,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate that a field is required when a condition is met.
        
        Args:
            data: Model data dictionary
            condition_field: Field name to check condition on
            condition_values: Value(s) that trigger the requirement
            required_field: Field that becomes required
            error_message: Custom error message
            
        Returns:
            Validated data dictionary
            
        Raises:
            ValueError: If required field is missing when condition is met
        """
        condition_value = data.get(condition_field)
        required_value = data.get(required_field)
        
        # Normalize condition_values to a list
        if not isinstance(condition_values, list):
            condition_values = [condition_values]
            
        if condition_value in condition_values and required_value is None:
            msg = error_message or f"{required_field} is required when {condition_field} is {condition_value}"
            raise ValueError(msg)
            
        return data


def validate_term_specification(cls, data: Any) -> Any:
    """
    Reusable validator for term specification (end_date or term_months).
    
    This validator ensures that models have a valid duration specification
    and that dates are in logical order.
    
    Usage:
        @model_validator(mode="after")
        @classmethod
        def check_term(cls, data) -> Self:
            return validate_term_specification(cls, data)
    """
    if isinstance(data, dict):
        # Dictionary validation (mode="before")
        ValidationMixin.validate_either_or_required(
            data, "end_date", "term_months",
            "Either end_date or term_months must be provided"
        )
        ValidationMixin.validate_date_ordering(
            data, "start_date", "end_date",
            "end_date must be after start_date"
        )
        return data
    else:
        # Model instance validation (mode="after")
        if hasattr(data, 'end_date') and hasattr(data, 'term_months'):
            if data.end_date is None and data.term_months is None:
                raise ValueError("Either end_date or term_months must be provided")
            if data.end_date is not None and hasattr(data, 'start_date'):
                if data.end_date <= data.start_date:
                    raise ValueError("end_date must be after start_date")
        return data


def validate_mutual_exclusivity(
    field_a: str, 
    field_b: str, 
    error_message: Optional[str] = None
):
    """
    Decorator for mutual exclusivity validation.
    
    Args:
        field_a: First field name
        field_b: Second field name
        error_message: Custom error message
        
    Returns:
        Validator function
        
    Usage:
        @model_validator(mode="after")
        @validate_mutual_exclusivity("start_date", "start_offset_months")
        def check_start_definition(cls, data):
            return data
    """
    def validator(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ValidationMixin.validate_either_or_required(data, field_a, field_b, error_message)
        else:
            # For model instances
            value_a = getattr(data, field_a, None)
            value_b = getattr(data, field_b, None)
            
            if value_a is None and value_b is None:
                msg = error_message or f"Either {field_a} or {field_b} must be provided"
                raise ValueError(msg)
                
            if value_a is not None and value_b is not None:
                msg = error_message or f"Cannot provide both {field_a} and {field_b}"
                raise ValueError(msg)
                
        return data
    return validator


def validate_conditional_requirement_decorator(
    condition_field: str,
    condition_values: Union[Any, List[Any]],
    required_field: str,
    error_message: Optional[str] = None
):
    """
    Decorator for conditional requirement validation.
    
    Args:
        condition_field: Field name to check condition on
        condition_values: Value(s) that trigger the requirement
        required_field: Field that becomes required
        error_message: Custom error message
        
    Returns:
        Validator function
        
    Usage:
        @model_validator(mode="after")
        @validate_conditional_requirement_decorator("structure", "base_stop", "base_amount")
        def check_structure_requirements(cls, data):
            return data
    """
    def validator(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ValidationMixin.validate_conditional_requirement(
                data, condition_field, condition_values, required_field, error_message
            )
        else:
            # For model instances
            condition_value = getattr(data, condition_field, None)
            required_value = getattr(data, required_field, None)
            
            # Normalize condition_values to a list
            if not isinstance(condition_values, list):
                condition_values_list = [condition_values]
            else:
                condition_values_list = condition_values
                
            if condition_value in condition_values_list and required_value is None:
                msg = error_message or f"{required_field} is required when {condition_field} is {condition_value}"
                raise ValueError(msg)
                
        return data
    return validator 


def validate_monthly_period_index(series: pd.Series, field_name: str = "series") -> pd.Series:
    """
    Validate that a pandas Series has a monthly PeriodIndex.
    
    This is a critical requirement throughout Performa as all calculations
    assume monthly periodicity. Non-monthly data must be converted before
    being passed to Performa models.
    
    Args:
        series: The pandas Series to validate
        field_name: Name of the field for error messages
        
    Returns:
        The validated series (unchanged)
        
    Raises:
        ValueError: If the series doesn't have a monthly PeriodIndex
        
    Example:
        ```python
        # Valid monthly series
        monthly_data = pd.Series(
            [100, 200, 300],
            index=pd.period_range('2024-01', periods=3, freq='M')
        )
        validate_monthly_period_index(monthly_data)  # OK
        
        # Invalid quarterly series
        quarterly_data = pd.Series(
            [100, 200, 300],
            index=pd.period_range('2024Q1', periods=3, freq='Q')
        )
        validate_monthly_period_index(quarterly_data)  # Raises ValueError
        ```
    """
    if not isinstance(series, pd.Series):
        raise TypeError(f"{field_name} must be a pandas Series, got {type(series).__name__}")
    
    if not isinstance(series.index, pd.PeriodIndex):
        raise ValueError(
            f"{field_name} must have a PeriodIndex, got {type(series.index).__name__}. "
            "Consider using pd.PeriodIndex(dates, freq='M') or series.index = series.index.to_period('M')"
        )
    
    if series.index.freq != 'M':
        raise ValueError(
            f"{field_name} must have monthly frequency ('M'), got '{series.index.freq}'. "
            f"Performa requires all time series data to be monthly. "
            f"Please resample or convert your data to monthly frequency before passing to Performa."
        )
    
    return series 