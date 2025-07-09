from __future__ import annotations

from ...core.primitives import Model


class OfficeTenant(Model):
    """
    Office-specific tenant record.
    """
    id: str
    name: str 