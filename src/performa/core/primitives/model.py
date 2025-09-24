# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Base model with common configuration"""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,  # Decision: Stick with frozen=True. Mutable state for specific processes (e.g., absorption, recovery pre-calcs) will be handled by external state objects.
        # TODO: Add extra="forbid" after fixing existing parameter validation issues throughout codebase
        # extra="forbid",  # Prevent silent parameter failures in financial models
    )
