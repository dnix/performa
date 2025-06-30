from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        use_enum_values=True,
        # validate_assignment=True,  # TODO: evaluate if this is needed
    )
