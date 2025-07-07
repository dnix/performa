from performa.common.primitives import GlobalSettings, Model, Timeline

from .registry import get_scenario_for_model
from .scenario import AnalysisScenarioBase


def run(
    model: Model,
    timeline: Timeline,
    settings: GlobalSettings,
) -> AnalysisScenarioBase:
    """
    Factory function to run the appropriate analysis scenario based on the model type.
    """
    # Use the public helper to find the scenario class
    scenario_cls = get_scenario_for_model(model)
    
    scenario = scenario_cls(model=model, timeline=timeline, settings=settings)
    scenario.run()
    return scenario
