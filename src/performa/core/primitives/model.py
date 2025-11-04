# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Base Pydantic model with common configuration.

    Immutable, slot-based models for efficient attribute access and reduced
    memory footprint. Mutable runtime state is handled outside of models.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,  # Immutable models; runtime mutable state lives in external objects
        slots=True,  # Faster attribute access and reduced memory usage
        extra="forbid",  # Catches typos and missing field definitions immediately
    )
