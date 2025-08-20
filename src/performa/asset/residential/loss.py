# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from pydantic import Field

from ...core.base.loss import (
    CreditLossConfig,
    VacancyLossConfig,
)
from ...core.primitives import Model

# Clean aliases - no residential-specific logic needed
ResidentialVacancyLoss = VacancyLossConfig
ResidentialCreditLoss = CreditLossConfig
ResidentialGeneralVacancyLoss = VacancyLossConfig


class ResidentialLosses(Model):
    """
    Residential-specific container for property-level loss configurations.
    
    Maintains backward compatibility with existing field names while
    using the new clean loss configuration classes internally.
    """
    
    uid: UUID = Field(
        default_factory=uuid4, 
        description="Unique identifier for this losses container"
    )
    general_vacancy: Optional[VacancyLossConfig] = Field(
        default=None,
        description="General vacancy loss configuration"
    )
    credit_loss: Optional[CreditLossConfig] = Field(
        default=None,
        description="Credit loss configuration"
    )
