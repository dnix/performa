from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict, Type

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
