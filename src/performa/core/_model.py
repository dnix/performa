from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Base model with common configuration"""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
        frozen=True,  # TODO: evaluate shared state implications without freezing
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
