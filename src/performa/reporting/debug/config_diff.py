# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Configuration Diff Debug Utilities

Debugging capabilities for deal configuration comparison in financial model validation.
These utilities provide deep object comparison to identify parameter differences
that affect financial results.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List
from uuid import UUID

if TYPE_CHECKING:
    from performa.deal.deal import Deal

logger = logging.getLogger(__name__)


def compare_deal_configurations(
    deal1: "Deal", deal2: "Deal", 
    include_defaults: bool = False
) -> Dict[str, Any]:
    """
    Compare configurations between two deals with deep object inspection.
    
    This utility performs deep comparison of deal configurations to identify
    ALL parameter differences that could cause analysis result variations.
    
    No filtering is applied - all differences are reported since seemingly
    "minor" differences can have major impacts on deal economics.
    
    Args:
        deal1: First deal for comparison
        deal2: Second deal for comparison  
        include_defaults: Whether to include default parameters in comparison
        
    Returns:
        Dict containing comprehensive configuration diff analysis with all differences
        
    Example:
        ```python
        diff = compare_deal_configurations(comp_deal, pattern_deal)
        if diff['differences']:
            print(f"Found {len(diff['differences'])} parameter differences")
            for difference in diff['differences']:
                print(f"{difference['path']}: {difference['description']}")
        ```
    """
    # Extract configurations from both deals
    config1 = _extract_deal_configuration(deal1, include_defaults)
    config2 = _extract_deal_configuration(deal2, include_defaults)
    
    # Perform deep comparison
    differences = _deep_compare_configs(config1, config2)
    
    # Return all differences without filtering - every difference matters
    result = {
        'deal1_config': config1,
        'deal2_config': config2,
        'differences': differences,  # All differences (no filtering)
        'all_differences': differences,  # Alias for backward compatibility
        'has_differences': len(differences) > 0,
        'impact_assessment': _assess_difference_impact(differences),
        'recommendations': _generate_fix_recommendations(differences)
    }
    
    return result


def _extract_deal_configuration(deal: "Deal", include_defaults: bool) -> Dict[str, Any]:
    """Extract configuration from a deal object."""
    config = {}
    
    # Deal-level properties
    config['name'] = getattr(deal, 'name', None)
    config['description'] = getattr(deal, 'description', None)
    
    # Asset configuration
    if deal.asset:
        config['asset'] = _extract_object_config(deal.asset, include_defaults)
    
    # Acquisition configuration
    if deal.acquisition:
        config['acquisition'] = _extract_object_config(deal.acquisition, include_defaults)
    
    # Financing configuration
    if deal.financing:
        config['financing'] = _extract_financing_config_deep(deal.financing, include_defaults)
    
    # Exit configuration
    if deal.exit_valuation:
        config['exit'] = _extract_object_config(deal.exit_valuation, include_defaults)
    
    # Partnership configuration
    if deal.equity_partners:
        config['partnership'] = _extract_object_config(deal.equity_partners, include_defaults)
    
    return config


def _extract_financing_config_deep(financing, include_defaults: bool) -> Dict[str, Any]:
    """Extract detailed financing configuration."""
    config = _extract_object_config(financing, include_defaults)
    
    # Add facility-specific details
    if hasattr(financing, 'facilities') and financing.facilities:
        config['facilities'] = []
        for i, facility in enumerate(financing.facilities):
            facility_config = _extract_object_config(facility, include_defaults)
            facility_config['_facility_index'] = i
            config['facilities'].append(facility_config)
    
    return config


def _extract_object_config(obj: Any, include_defaults: bool) -> Dict[str, Any]:
    """Extract configuration from any Pydantic object."""
    config = {}
    
    if hasattr(obj, 'model_fields'):  # Pydantic v2
        for field_name, field_info in obj.model_fields.items():
            try:
                value = getattr(obj, field_name)
                
                # Skip None values unless they're meaningful
                if value is None and not include_defaults:
                    continue
                    
                # Handle UUID objects
                if isinstance(value, UUID):
                    continue  # Skip UUIDs as they're not configuration
                    
                # Store value with type info
                config[field_name] = {
                    'value': value,
                    'type': type(value).__name__,
                    'is_default': _is_default_value(value, field_info)
                }
            except Exception:
                continue
    
    return config


def _deep_compare_configs(config1: Dict[str, Any], config2: Dict[str, Any], path: str = "") -> List[Dict[str, Any]]:
    """Perform deep comparison of configuration dictionaries."""
    differences = []
    
    all_keys = set(config1.keys()) | set(config2.keys())
    
    for key in all_keys:
        current_path = f"{path}.{key}" if path else key
        
        value1 = config1.get(key)
        value2 = config2.get(key)
        
        if value1 is None and value2 is None:
            continue
        elif value1 is None or value2 is None:
            differences.append({
                'path': current_path,
                'type': 'missing_parameter',
                'value1': value1,
                'value2': value2,
                'description': f"Parameter exists in only one configuration"
            })
        elif isinstance(value1, dict) and isinstance(value2, dict):
            # Recursive comparison for nested objects
            nested_diffs = _deep_compare_configs(value1, value2, current_path)
            differences.extend(nested_diffs)
        elif isinstance(value1, list) and isinstance(value2, list):
            # Compare lists (e.g., facilities)
            if len(value1) != len(value2):
                differences.append({
                    'path': current_path,
                    'type': 'list_length_difference',
                    'value1': len(value1),
                    'value2': len(value2),
                    'description': f"List lengths differ: {len(value1)} vs {len(value2)}"
                })
            else:
                for i, (item1, item2) in enumerate(zip(value1, value2)):
                    if isinstance(item1, dict) and isinstance(item2, dict):
                        nested_diffs = _deep_compare_configs(item1, item2, f"{current_path}[{i}]")
                        differences.extend(nested_diffs)
        else:
            # Handle different value extraction patterns
            val1 = value1['value'] if isinstance(value1, dict) and 'value' in value1 else value1
            val2 = value2['value'] if isinstance(value2, dict) and 'value' in value2 else value2
            
            if val1 != val2:
                differences.append({
                    'path': current_path,
                    'type': 'value_difference',
                    'value1': val1,
                    'value2': val2,
                    'description': f"Values differ: {val1} vs {val2}"
                })
    
    return differences


def _assess_difference_impact(differences: List[Dict[str, Any]]) -> str:
    """Assess the likely impact of all differences on results."""
    if not differences:
        return "No differences - results should match perfectly"
    
    high_impact_types = [
        'rate', 'cap_rate', 'exit', 'hold_period', 'loan_amount', 'interest_rate',
        'timeline', 'refinance_timing', 'duration_months'  # Added timeline-related 
    ]
    
    high_impact_count = sum(
        1 for diff in differences
        if any(keyword in diff['path'].lower() for keyword in high_impact_types)
    )
    
    if high_impact_count > 0:
        return f"Impact expected: {high_impact_count} differences in rates/timing/amounts from {len(differences)} total"
    elif len(differences) > 5:
        return f"Medium impact possible: {len(differences)} parameter differences"  
    else:
        return f"Low impact expected: {len(differences)} minor differences"


def _generate_fix_recommendations(differences: List[Dict[str, Any]]) -> List[str]:
    """Generate specific recommendations for fixing all differences."""
    recommendations = []
    
    for diff in differences:
        path = diff['path']
        
        if 'financing' in path.lower():
            recommendations.append(f"Check financing configuration: {path}")
        elif 'exit' in path.lower() or 'cap_rate' in path.lower():
            recommendations.append(f"Verify exit assumptions: {path}")
        elif 'timeline' in path.lower() or 'term' in path.lower():
            recommendations.append(f"Check timeline alignment: {path}")
        elif 'rate' in path.lower():
            recommendations.append(f"Verify rate parameter: {path}")
        else:
            recommendations.append(f"Review parameter: {path}")
    
    return list(set(recommendations))  # Remove duplicates


def _is_default_value(value: Any, field_info: Any) -> bool:
    """Determine if a value is the default for a field."""
    try:
        if hasattr(field_info, 'default') and field_info.default is not None:
            return value == field_info.default
        return False
    except Exception:
        return False
