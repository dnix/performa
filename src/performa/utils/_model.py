"""Base model for all modules"""

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Base model with common configuration"""
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
    ) 