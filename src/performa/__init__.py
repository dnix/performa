# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import importlib
import logging
import warnings

# Silence pandas FutureWarning related to monthly frequency alias 'M'.
# Performa standardizes monthly PeriodIndex usage across modules and
# suppresses this warning to reduce log noise during analysis.
warnings.filterwarnings(
    "ignore",
    message=".*'M' is deprecated and will be removed in a future version.*",
    category=FutureWarning,
)

"""
Performa - Open-Source Real Estate Financial Modeling Framework

Building blocks for sophisticated real estate analysis, from simple property
valuations to complex development projects and institutional-grade deal structuring.

Key Entry Points:
- performa.deal.analyze() - Complete deal analysis with strongly-typed results
- performa.analysis.run() - Asset-level analysis (unlevered)
- performa.asset.* - Property and development modeling
- performa.debt.* - Financing structures
- performa.valuation.* - Valuation methodologies

Example Usage:
    ```python
    from performa.deal import analyze, Deal
    from performa.asset.office import OfficeProperty
    from performa.debt import FinancingPlan
    from performa.core.primitives import Timeline

    # Create deal structure
    deal = Deal(
        name="Investment Deal",
        asset=office_property,
        acquisition=acquisition_terms,
        financing=financing_plan
    )

    # Analyze with strongly-typed results
    results = analyze(deal, timeline)
    print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
    ```
"""

# Add a NullHandler to the root logger to prevent "No handlers could be found" warnings
# when the library is used in applications that don't configure logging.
# This follows the logging best practice for libraries as described in the Python
# logging documentation. Applications using this library can configure their own
# logging handlers as needed.
logging.getLogger(__name__).addHandler(logging.NullHandler())


# Public API surface (lazy-loaded on first attribute access)
__all__ = [  # noqa: F822 - lazy loading
    "analysis",
    "asset",
    "core",
    "deal",
    "debt",
    "development",
    "reporting",
    "valuation",
]


_LAZY_MODULES = {
    "analysis": "performa.analysis",
    "asset": "performa.asset",
    "core": "performa.core",
    "deal": "performa.deal",
    "debt": "performa.debt",
    "development": "performa.development",
    "reporting": "performa.reporting",
    "valuation": "performa.valuation",
}


def __getattr__(name: str):
    module_path = _LAZY_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module 'performa' has no attribute '{name}'")
    module = importlib.import_module(module_path)
    globals()[name] = module
    return module
