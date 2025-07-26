# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Commercial Asset Base Classes

This module provides shared base classes and patterns for commercial real estate
properties including office, retail, and industrial assets. These base classes
capture the common characteristics and behaviors of commercial properties while
enabling asset-specific customization.

Key Components:

Commercial Analysis (CommercialAnalysisScenarioBase):
- Assembler pattern implementation for commercial properties
- Recovery method lookup maps and object injection
- TI/LC template resolution and cost modeling
- Complex rollover scenario handling

Commercial Leases (CommercialLeaseBase):
- Multi-escalation support for complex lease structures
- Expense recovery calculations (base year, net, gross-up)
- TI and LC integration with proper payment timing
- Rollover projection with state transitions

Commercial Recovery (CommercialRecoveryMethodBase):
- Sophisticated expense recovery calculations
- Support for multiple recovery structures (net, base year, fixed)
- Gross-up functionality for occupancy adjustments
- Administrative fees and caps handling

Commercial Rollover (CommercialRolloverProfileBase):
- Market vs. renewal rate blending logic
- Complex term negotiations and cost structures
- State machine transitions for value-add scenarios

Architecture:
Commercial properties share common patterns:
- Complex lease structures with multiple components
- Expense recovery from tenants (CAM, taxes, insurance)
- Tenant improvement and leasing commission costs
- Sophisticated rollover and renewal scenarios

These base classes provide the foundation for:
- Office buildings with multiple tenants and recovery methods
- Retail properties with percentage rent and CAM recoveries
- Industrial properties with net lease structures

Example:
    ```python
    from performa.asset.commercial import CommercialLeaseBase
    from performa.asset.office import OfficeLease
    
    # Office lease inherits commercial functionality
    office_lease = OfficeLease.from_spec(lease_spec, ...)
    
    # Automatic recovery calculations
    recoveries = office_lease.recovery_method.compute_cf(context)
    ```

Commercial base classes enable sophisticated modeling while maintaining
consistency across different commercial property types.
"""

from .analysis import CommercialAnalysisScenarioBase
from .lc import CommercialLeasingCommissionBase
from .lease import CommercialLeaseBase
from .recovery import CommercialRecoveryMethodBase
from .rollover import CommercialRolloverProfileBase

__all__ = [
    "CommercialAnalysisScenarioBase",
    "CommercialLeasingCommissionBase",
    "CommercialLeaseBase",
    "CommercialRecoveryMethodBase",
    "CommercialRolloverProfileBase",
]
