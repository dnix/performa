# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ...core.base import MiscIncomeBase


class ResidentialMiscIncome(MiscIncomeBase):
    """
    Residential-specific miscellaneous income.
    
    Common sources in multifamily properties include:
    - Parking fees
    - Laundry income
    - Storage unit rentals
    - Pet fees
    - Application and admin fees
    - Late payment fees
    - Utility reimbursements
    - Vending machine income
    
    Inherits all functionality from MiscIncomeBase including growth
    rate application and variable/fixed income components.
    """
    pass 