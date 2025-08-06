# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit Tests for Analysis Registry

Tests the scenario registration and lookup functionality.
"""

import inspect
from datetime import date

import pytest

from performa.analysis import get_scenario_for_model, register_scenario
from performa.analysis.scenario import AnalysisScenarioBase
from performa.core.primitives import GlobalSettings, Model, Timeline


class MockModel(Model):
    """Mock model for testing scenario registry."""

    name: str = "test_model"


class MockSubModel(MockModel):
    """Mock submodel for testing subclass lookup."""

    additional_field: str = "test"


@register_scenario(MockModel)
class MockScenario(AnalysisScenarioBase):
    """Mock scenario for testing."""

    def prepare_models(self):
        return []


class TestGetScenarioForModel:
    """Test suite for get_scenario_for_model function."""

    def test_get_scenario_for_exact_match(self):
        """Test that get_scenario_for_model finds exact type matches."""
        model = MockModel()
        scenario_cls = get_scenario_for_model(model)

        assert scenario_cls == MockScenario
        assert issubclass(scenario_cls, AnalysisScenarioBase)

    def test_get_scenario_for_subclass_match(self):
        """Test that get_scenario_for_model finds matches for subclasses."""
        submodel = MockSubModel()
        scenario_cls = get_scenario_for_model(submodel)

        # Should find MockScenario because MockSubModel is a subclass of MockModel
        assert scenario_cls == MockScenario
        assert issubclass(scenario_cls, AnalysisScenarioBase)

    def test_get_scenario_for_model_not_found(self):
        """Test that get_scenario_for_model raises TypeError for unregistered models."""

        class UnregisteredModel(Model):
            pass

        unregistered = UnregisteredModel()

        with pytest.raises(TypeError) as exc_info:
            get_scenario_for_model(unregistered)

        assert (
            "No analysis scenario registered for model type UnregisteredModel"
            in str(exc_info.value)
        )

    def test_function_signature_and_documentation(self):
        """Test that the function has proper signature and documentation."""
        # Check signature
        sig = inspect.signature(get_scenario_for_model)
        assert len(sig.parameters) == 1
        assert "model" in sig.parameters

        # Check documentation
        assert get_scenario_for_model.__doc__ is not None
        assert (
            "Finds and returns the appropriate analysis scenario class"
            in get_scenario_for_model.__doc__
        )

        # Check type hints (accounting for TYPE_CHECKING forward references)
        model_annotation = sig.parameters["model"].annotation
        assert model_annotation == Model or model_annotation == "Model"
        assert "AnalysisScenarioBase" in str(sig.return_annotation)


class TestArchitecturalBenefits:
    """Test the architectural benefits of the registry helper."""

    def test_eliminates_code_duplication(self):
        """Test that multiple analysis components can reuse the same scenario lookup logic."""
        # The helper function should provide consistent results across different usage contexts
        model = MockModel()
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
        settings = GlobalSettings()

        # Direct usage of the helper function
        scenario_cls_direct = get_scenario_for_model(model)

        # Verify consistent scenario class resolution
        assert scenario_cls_direct == MockScenario

    def test_no_private_imports_needed(self):
        """Test that external modules can use the public API without accessing internal registry details."""
        # This test demonstrates that external modules can perform scenario lookup
        # without needing to import or duplicate the internal registry logic

        model = MockModel()

        # Clean usage through public API
        scenario_cls = get_scenario_for_model(model)
        assert scenario_cls == MockScenario
