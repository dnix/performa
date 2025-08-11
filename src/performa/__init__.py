# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import logging
import warnings

from . import analysis, asset, core, deal, debt, development, reporting, valuation

# Silence pandas FutureWarning about 'M' frequency being deprecated
# This warning is misleading - pandas has threatened this for years without action
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


# Guide users to the new, explicit API surface
__all__ = [
    "analysis",
    "asset",
    "core",
    "deal",
    "debt",
    "development",
    "reporting",
    "valuation",
]
