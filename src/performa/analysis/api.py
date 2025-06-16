from typing import Type

from performa.common.primitives import GlobalSettings, Model, Timeline

from .registry import SCENARIO_REGISTRY
from .scenario import AnalysisScenarioBase


def run(
    model: Model,
    timeline: Timeline,
    settings: GlobalSettings,
) -> AnalysisScenarioBase:
    """
    Factory function to run the appropriate analysis scenario based on the model type.
    """
    model_type = type(model)
    scenario_cls = SCENARIO_REGISTRY.get(model_type)

    if scenario_cls is None:
        # Check for subclasses
        for registered_model_type, sc in SCENARIO_REGISTRY.items():
            if issubclass(model_type, registered_model_type):
                scenario_cls = sc
                break
    
    if scenario_cls is None:
        raise TypeError(f"No analysis scenario registered for model type {model_type.__name__}")

    scenario = scenario_cls(model=model, timeline=timeline, settings=settings)
    scenario.run()
    return scenario
