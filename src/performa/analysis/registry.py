from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict, Type

# Import Model for type hinting
from ..core.primitives import Model

if TYPE_CHECKING:
    from .scenario import AnalysisScenarioBase

SCENARIO_REGISTRY: Dict[Type, Type["AnalysisScenarioBase"]] = {}


def register_scenario(model_cls: Type) -> Callable:
    """
    A decorator to register a scenario class for a specific model type.
    """

    def decorator(scenario_cls: Type["AnalysisScenarioBase"]) -> Type["AnalysisScenarioBase"]:
        if model_cls in SCENARIO_REGISTRY:
            raise ValueError(f"Scenario for model {model_cls.__name__} is already registered.")
        SCENARIO_REGISTRY[model_cls] = scenario_cls
        return scenario_cls

    return decorator


def get_scenario_for_model(model: Model) -> Type["AnalysisScenarioBase"]:
    """
    Finds and returns the appropriate analysis scenario class for a given model.
    
    This function encapsulates the logic for looking up scenario classes in the registry,
    including checking for subclass matches when a direct type match isn't found.
    
    Args:
        model: The model instance to find a scenario for
        
    Returns:
        The scenario class that can handle the given model type
        
    Raises:
        TypeError: If no registered scenario can handle the model type
        
    Example:
        ```python
        scenario_cls = get_scenario_for_model(office_property)
        scenario = scenario_cls(model=office_property, timeline=timeline, settings=settings)
        scenario.run()
        ```
    """
    model_type = type(model)
    scenario_cls = SCENARIO_REGISTRY.get(model_type)

    if scenario_cls is None:
        # Check for subclasses if a direct match isn't found
        for registered_model_type, sc in SCENARIO_REGISTRY.items():
            if issubclass(model_type, registered_model_type):
                scenario_cls = sc
                break
    
    if scenario_cls is None:
        raise TypeError(f"No analysis scenario registered for model type {model_type.__name__}")
        
    return scenario_cls
