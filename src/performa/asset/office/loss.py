# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Optional

from pydantic import Field

from ...core.base.loss import (
    CreditLossConfig,
    VacancyLossConfig,
)
from ...core.primitives import Model

# Clean aliases - no office-specific logic needed
OfficeVacancyLoss = VacancyLossConfig
OfficeCreditLoss = CreditLossConfig
OfficeGeneralVacancyLoss = VacancyLossConfig


class OfficeLosses(Model):
    """
    Office-specific container for property-level loss configurations.
    
    Maintains backward compatibility with existing field names while
    using the new clean loss configuration classes internally.
    """
    
    general_vacancy: Optional[VacancyLossConfig] = Field(
        default=None,
        description="General vacancy loss configuration"
    )
    credit_loss: Optional[CreditLossConfig] = Field(
        default=None,
        description="Credit loss configuration"
    )
