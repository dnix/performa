from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Base model with common configuration"""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
        frozen=True,  # Decision: Stick with frozen=True. Mutable state for specific processes (e.g., absorption, recovery pre-calcs) will be handled by external state objects.
    )

    def copy(self, *, updates: dict = None) -> "Model":
        """
        Return a deep copy of the model (shorter alias for model_copy)

        Args:
            updates: Optional dictionary of field values to update

        Returns:
            A deep copy of the model with any specified updates
        """
        return self.model_copy(deep=True, update=updates) 