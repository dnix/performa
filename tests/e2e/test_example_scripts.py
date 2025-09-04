# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Example Scripts End-to-End Tests

This module executes all example scripts as end-to-end tests to catch regressions
that unit tests miss (e.g., IRR calculation failures, integration issues).

These tests validate that our public examples continue to work as expected,
ensuring that architectural changes don't break real-world usage patterns.
"""

import sys
from pathlib import Path

# Add examples directory to path for imports
examples_dir = Path(__file__).parent.parent.parent / "examples"
sys.path.insert(0, str(examples_dir))


class TestExampleScripts:
    """Test that all example scripts execute without errors."""

    def test_basic_office_development(self):
        """Test basic office development example executes and produces valid results."""
        import basic_office_development  # noqa  # type:ignore

        # Should run without exceptions and produce valid IRR
        basic_office_development.main()

    def test_stabilized_multifamily_acquisition(self):
        """Test stabilized acquisition example executes successfully."""
        import stabilized_multifamily_acquisition  # noqa  # type:ignore

        stabilized_multifamily_acquisition.main()

    def test_value_add_renovation(self):
        """Test value-add renovation example executes successfully."""
        import value_add_renovation  # noqa  # type:ignore

        value_add_renovation.main()

    def test_office_stabilized_acquisition_comparison(self):
        """Test office stabilized acquisition comparison example."""
        import office_stabilized_acquisition_comparison  # noqa  # type:ignore

        office_stabilized_acquisition_comparison.main()


class TestPatternExamples:
    """Test that pattern-based examples execute without errors."""

    def test_office_development_comparison(self):
        """Test office development pattern comparison."""
        patterns_dir = examples_dir / "patterns"
        sys.path.insert(0, str(patterns_dir))

        import office_development_comparison  # noqa  # type:ignore

        office_development_comparison.main()

    def test_residential_development_comparison(self):
        """Test residential development pattern comparison."""
        patterns_dir = examples_dir / "patterns"
        sys.path.insert(0, str(patterns_dir))

        import residential_development_comparison  # noqa  # type:ignore

        residential_development_comparison.main()

    def test_stabilized_comparison(self):
        """Test stabilized acquisition pattern comparison."""
        patterns_dir = examples_dir / "patterns"
        sys.path.insert(0, str(patterns_dir))

        import stabilized_comparison  # noqa  # type:ignore

        stabilized_comparison.main()

    def test_value_add_comparison(self):
        """Test value-add acquisition pattern comparison."""
        patterns_dir = examples_dir / "patterns"
        sys.path.insert(0, str(patterns_dir))

        import value_add_comparison  # noqa  # type:ignore

        value_add_comparison.main()
