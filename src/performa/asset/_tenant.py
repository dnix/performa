from __future__ import annotations

from ..core._model import Model


class Tenant(Model):
    """
    Individual tenant record.

    Attributes:
        id: Unique identifier (often the tenant name if simple).
        name: Tenant name.
    """

    id: str
    name: str
    # TODO: more fields?
