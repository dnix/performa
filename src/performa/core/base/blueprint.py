# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Development blueprint base class and contracts.

This module defines the abstract contract that asset modules must implement
to participate in the development process. This contract enables polymorphic
behavior without circular dependencies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..primitives import Model, ProgramUseEnum, Timeline
from .property import PropertyBaseModel


class DevelopmentBlueprintBase(Model, ABC):
    """
    Abstract base class for development blueprints.

    A development blueprint is a specification for creating a stabilized asset
    from development inputs. Each asset type (office, residential, etc.) provides
    its own concrete implementation that knows how to:

    1. Take vacant inventory specifications
    2. Apply an absorption plan (business plan for stabilization)
    3. Create a fully-formed, stabilized asset ready for operations analysis

    This follows the "Asset Factory" pattern where development projects
    create assets, they don't become assets.
    """

    name: str
    """Human-readable name for this blueprint component."""

    use_type: ProgramUseEnum
    """The asset type this blueprint will create (OFFICE, RESIDENTIAL, etc.)."""

    @abstractmethod
    def to_stabilized_asset(self, timeline: Timeline) -> PropertyBaseModel:
        """
        Factory method to create a stabilized asset model.

        This method transforms the blueprint's vacant inventory and absorption plan
        into a fully-formed asset ready for operations analysis. The implementation
        is asset-type specific and lives in the respective asset module.

        Args:
            timeline: The project timeline for phasing construction and absorption

        Returns:
            A stabilized asset model (e.g., OfficeProperty, ResidentialProperty)
            ready for operations analysis
        """
        pass
