# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ...core.primitives import Model


class OfficeTenant(Model):
    """
    Office-specific tenant record.
    """
    id: str
    name: str 