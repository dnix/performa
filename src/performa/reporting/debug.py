# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Debug utilities for financial model validation and troubleshooting.

These utilities provide visibility into model configuration and ledger data
to help diagnose issues with deal calculations and identify unrealistic parameters.

Enhanced with polymorphic object introspection - can debug any Performa component:
- Assets (ResidentialProperty, OfficeDevelopmentProject, etc.)
- Deals (complete Deal objects)
- Primitives (Timeline, GlobalSettings, etc.)
- Patterns (ResidentialDevelopmentPattern, etc.)
- Constructs (FinancingPlan, etc.)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from pydantic import BaseModel

from ..core.ledger import Ledger
from ..core.primitives import GlobalSettings, Timeline
from ..deal import Deal
from ..debt.plan import FinancingPlan


def dump_deal_config(
    deal: Deal,
    exclude_defaults: bool = True,
    exclude_unset: bool = False,
    include_computed: bool = False,
) -> Dict[str, Any]:
    """
    Extract complete configuration from Deal and all components.

    Provides visibility into all Pydantic model parameters to spot
    unrealistic assumptions and configuration drift.

    Args:
        deal: Deal object to analyze
        exclude_defaults: Only show parameters that differ from defaults
        exclude_unset: Only show parameters explicitly set by user
        include_computed: Include computed/derived properties

    Returns:
        Nested dictionary of configuration parameters organized by component

    Example:
        ```python
        config = dump_deal_config(deal, exclude_defaults=True)
        print(f"Asset rent: ${config['asset']['target_rent_psf']}/SF")
        print(f"Exit cap: {config['exit']['cap_rate']:.1%}")
        ```
    """
    config = {}

    # Deal-level configuration with class info
    config["deal"] = {"_class_name": type(deal).__name__, "_object_type": "Deal"}
    deal_config = deal.model_dump(
        exclude_defaults=exclude_defaults,
        exclude_unset=exclude_unset,
        exclude={
            "asset",
            "financing",
            "equity_partners",
            "exit_valuation",
        },  # Handle separately
    )
    config["deal"].update(deal_config)

    # Asset configuration
    if deal.asset:
        config["asset"] = _extract_asset_config(
            deal.asset, exclude_defaults, exclude_unset, include_computed
        )

    # Acquisition configuration
    if deal.acquisition:
        config["acquisition"] = {
            "_class_name": type(deal.acquisition).__name__,
            "_object_type": _classify_performa_object(deal.acquisition),
        }
        acquisition_config = deal.acquisition.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )
        config["acquisition"].update(acquisition_config)

    # Financing configuration
    if deal.financing:
        config["financing"] = _extract_financing_config(
            deal.financing, exclude_defaults, exclude_unset
        )

    # Partnership configuration
    if deal.equity_partners:
        config["partnership"] = _extract_partnership_config(
            deal.equity_partners, exclude_defaults, exclude_unset
        )

    # Exit configuration
    if deal.exit_valuation:
        config["exit"] = {
            "_class_name": type(deal.exit_valuation).__name__,
            "_object_type": _classify_performa_object(deal.exit_valuation),
        }
        exit_config = deal.exit_valuation.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )
        config["exit"].update(exit_config)

    return config


def dump_performa_object(
    obj: Any,
    exclude_defaults: bool = True,
    exclude_unset: bool = False,
    include_computed: bool = False,
    include_class_info: bool = True,
) -> Dict[str, Any]:
    """
    Polymorphic debug utility for any Performa object.

    Handles all Performa object types with appropriate introspection:
    - Deal objects (full deal analysis)
    - Asset objects (property, development project, etc.)
    - Primitive objects (Timeline, GlobalSettings, etc.)
    - Pattern objects (ResidentialDevelopmentPattern, etc.)
    - Construct results (FinancingPlan, etc.)

    Args:
        obj: Any Performa object to analyze
        exclude_defaults: Only show parameters that differ from defaults
        exclude_unset: Only show parameters explicitly set by user
        include_computed: Include computed/derived properties
        include_class_info: Include class name and type information

    Returns:
        Dictionary with object configuration and metadata

    Example:
        ```python
        # Debug any object type
        config = dump_performa_object(timeline)
        config = dump_performa_object(residential_pattern)
        config = dump_performa_object(financing_plan)
        config = dump_performa_object(deal)
        ```
    """
    result = {}

    # Add class information
    if include_class_info:
        result["_object_info"] = {
            "class_name": type(obj).__name__,
            "module": type(obj).__module__,
            "object_type": _classify_performa_object(obj),
        }

    # Dispatch to appropriate handler based on object type
    # NOTE: Order matters! More specific checks must come before generic ones
    if isinstance(obj, Deal):
        result["config"] = _handle_deal_object(
            obj, exclude_defaults, exclude_unset, include_computed
        )

    elif isinstance(obj, FinancingPlan):
        # Handle FinancingPlan before generic Pydantic check
        result["config"] = _handle_financing_plan(obj, exclude_defaults, exclude_unset)

    elif isinstance(obj, (Timeline, GlobalSettings)):
        result["config"] = _handle_primitive_object(
            obj, exclude_defaults, exclude_unset
        )

    elif hasattr(obj, "model_dump") and callable(obj.model_dump):
        # Generic Pydantic model (assets, patterns, etc.) - must come after specific checks
        result["config"] = _handle_pydantic_object(
            obj, exclude_defaults, exclude_unset, include_computed
        )

    else:
        # Fallback: try to extract what we can
        result["config"] = _handle_generic_object(obj, exclude_defaults, exclude_unset)

    return result


def _classify_performa_object(obj: Any) -> str:
    """
    Classify Performa object type for appropriate debugging strategy.

    This classification system enables the debug utility to apply the most
    appropriate introspection method for each object category.

    Args:
        obj: Any object to classify

    Returns:
        str: Object classification for debugging strategy

    Classification Categories:
        - Deal: Complete deal objects requiring full component analysis
        - Pattern: High-level pattern interfaces (ResidentialDevelopmentPattern, etc.)
        - Asset: Property and project objects (ResidentialProperty, DevelopmentProject, etc.)
        - Primitive: Core system objects (Timeline, GlobalSettings, etc.)
        - Debt: Financing objects (FinancingPlan, PermanentFacility, etc.)
        - Valuation: Exit valuation models (DirectCapValuation, etc.)
        - Partnership: Equity structure objects (PartnershipStructure, etc.)
        - Unknown: Fallback for unrecognized objects

    Example:
        ```python
        obj_type = _classify_performa_object(residential_pattern)
        # Returns: "Pattern"

        obj_type = _classify_performa_object(timeline)
        # Returns: "Primitive"
        ```
    """
    obj_type = type(obj).__name__

    # Deal objects: Complete deal structures requiring comprehensive analysis
    if isinstance(obj, Deal):
        return "Deal"

    # Pattern objects: High-level interfaces for rapid deal creation
    if "Pattern" in obj_type:
        return "Pattern"

    # Asset objects: Properties and development projects
    if any(
        asset_indicator in obj_type
        for asset_indicator in ["Property", "Project", "Blueprint"]
    ):
        return "Asset"

    # Primitive objects: Core system components
    if any(primitive in obj_type for primitive in ["Timeline", "Settings", "Context"]):
        return "Primitive"

    # Debt objects: Financing facilities and plans
    if any(
        debt_indicator in obj_type for debt_indicator in ["Facility", "Plan", "Tranche"]
    ):
        return "Debt"

    # Valuation objects: Exit valuation models
    if "Valuation" in obj_type:
        return "Valuation"

    # Partnership objects: Equity structure and waterfall models
    if any(
        partnership_indicator in obj_type
        for partnership_indicator in ["Partnership", "Partner"]
    ):
        return "Partnership"

    # Fallback for unrecognized objects
    return "Unknown"


def _handle_deal_object(
    deal: Deal, exclude_defaults: bool, exclude_unset: bool, include_computed: bool
) -> Dict[str, Any]:
    """
    Handle Deal objects using comprehensive component analysis.

    Deal objects require special handling because they contain multiple
    complex components (asset, financing, partnership, etc.) that need
    individual introspection and class identification.

    Args:
        deal: Deal object to analyze
        exclude_defaults: Filter out default parameter values
        exclude_unset: Filter out unset parameter values
        include_computed: Include computed/derived properties

    Returns:
        Dict containing complete deal configuration with component class info
    """
    return dump_deal_config(deal, exclude_defaults, exclude_unset, include_computed)


def _handle_pydantic_object(
    obj: BaseModel, exclude_defaults: bool, exclude_unset: bool, include_computed: bool
) -> Dict[str, Any]:
    """
    Handle generic Pydantic model objects (patterns, assets, etc.).

    This handler works with any Pydantic-based Performa object and provides
    standardized configuration extraction plus computed properties for
    objects that support them (patterns, assets, etc.).

    Args:
        obj: Pydantic BaseModel object to analyze
        exclude_defaults: Filter out default parameter values
        exclude_unset: Filter out unset parameter values
        include_computed: Include computed/derived properties

    Returns:
        Dict containing object configuration and optional computed properties

    Supported Computed Properties:
        - total_project_cost: For objects with cost calculations
        - net_rentable_area: For property objects with area calculations
        - total_units: For residential objects with unit calculations
        - derived_timeline: For pattern objects with timeline derivation
    """
    config = obj.model_dump(
        exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
    )

    # Add computed properties for specific object types
    if include_computed:
        computed = {}

        # Asset objects
        if hasattr(obj, "total_project_cost"):
            computed["total_project_cost"] = obj.total_project_cost
        if hasattr(obj, "net_rentable_area"):
            computed["net_rentable_area"] = obj.net_rentable_area
        if hasattr(obj, "total_units"):
            computed["total_units"] = obj.total_units

        # Pattern objects
        if hasattr(obj, "_derive_timeline"):
            try:
                timeline = obj._derive_timeline()
                computed["derived_timeline"] = {
                    "duration_months": timeline.duration_months,
                    "start_date": str(timeline.start_date),
                }
            except:
                pass

        if computed:
            config["_computed"] = computed

    return config


def _handle_financing_plan(
    plan: FinancingPlan, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """
    Handle FinancingPlan objects with facility class identification.

    FinancingPlan objects contain multiple debt facilities that need individual
    class identification for proper debugging and cash-out refinancing analysis.

    Args:
        plan: FinancingPlan object to analyze
        exclude_defaults: Filter out default parameter values
        exclude_unset: Filter out unset parameter values

    Returns:
        Dict containing plan configuration with facility class information

    Example Output Structure:
        ```python
        {
            "_class_name": "FinancingPlan",
            "_object_type": "Debt",
            "name": "Construction-to-Permanent",
            "facilities": [
                {
                    "_class_name": "ConstructionFacility",
                    "_object_type": "Debt",
                    "name": "Construction Loan",
                    "loan_amount": 15000000,
                    # ... other config
                },
                {
                    "_class_name": "PermanentFacility",
                    "_object_type": "Debt",
                    "name": "Permanent Loan",
                    "loan_amount": 18000000,
                    # ... other config
                }
            ]
        }
        ```
    """
    return _extract_financing_config(plan, exclude_defaults, exclude_unset)


def _handle_primitive_object(
    obj: Any, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """
    Handle primitive Performa objects (Timeline, GlobalSettings, etc.).

    Primitive objects are core system components that provide foundational
    functionality. They may or may not be Pydantic models.

    Args:
        obj: Primitive object to analyze (Timeline, GlobalSettings, etc.)
        exclude_defaults: Filter out default parameter values
        exclude_unset: Filter out unset parameter values

    Returns:
        Dict containing primitive object configuration

    Supported Primitives:
        - Timeline: Project timeline with dates and duration
        - GlobalSettings: System-wide configuration settings
        - AnalysisContext: Analysis execution context (future)
        - Other core system objects
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )
    else:
        # For non-Pydantic primitives, extract what we can
        return {
            attr: getattr(obj, attr)
            for attr in dir(obj)
            if not attr.startswith("_") and not callable(getattr(obj, attr))
        }


def _handle_generic_object(
    obj: Any, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """
    Fallback handler for unknown or non-Performa object types.

    This handler attempts to extract useful information from any object
    type that doesn't fit into the standard Performa categories. It tries
    multiple extraction strategies to provide useful debugging information.

    Args:
        obj: Unknown object to analyze
        exclude_defaults: Filter out default parameter values (if applicable)
        exclude_unset: Filter out unset parameter values (if applicable)

    Returns:
        Dict containing extracted object information with fallback note

    Extraction Strategy:
        1. Try Pydantic model_dump() if available
        2. Fall back to basic attribute extraction for simple types
        3. Include diagnostic note about handler used

    Example Output:
        ```python
        {
            "_note": "Generic handler for CustomClass",
            "some_attr": "value",
            "numeric_attr": 42
        }
        ```
    """
    config = {"_note": f"Generic handler for {type(obj).__name__}"}

    # Try Pydantic model_dump first
    if hasattr(obj, "model_dump"):
        try:
            config.update(
                obj.model_dump(
                    exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
                )
            )
        except:
            pass

    # Fallback to basic attribute extraction
    if len(config) == 1:  # Only has the _note
        for attr in dir(obj):
            if not attr.startswith("_") and not callable(getattr(obj, attr)):
                try:
                    value = getattr(obj, attr)
                    # Only include simple types
                    if isinstance(value, (str, int, float, bool, type(None))):
                        config[attr] = value
                except:
                    pass

    return config


def _extract_asset_config(
    asset, exclude_defaults: bool, exclude_unset: bool, include_computed: bool
) -> Dict[str, Any]:
    """Extract configuration from asset and its components."""
    config = {
        "_class_name": type(asset).__name__,
        "_object_type": _classify_performa_object(asset),
    }

    asset_config = asset.model_dump(
        exclude_defaults=exclude_defaults,
        exclude_unset=exclude_unset,
        exclude={"capital_plans", "absorption_plans", "unit_mix", "expenses", "losses"},
    )
    config.update(asset_config)

    # Add computed properties if requested
    if include_computed:
        computed = {}
        if hasattr(asset, "total_project_cost"):
            computed["total_project_cost"] = asset.total_project_cost
        if hasattr(asset, "construction_plan") and asset.construction_plan:
            computed["total_construction_cost"] = asset.construction_plan.total_cost
        config["_computed"] = computed

    # Capital plans
    if hasattr(asset, "capital_plans") and asset.capital_plans:
        config["capital_plans"] = []
        for plan in asset.capital_plans:
            plan_config = plan.model_dump(
                exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
            )
            config["capital_plans"].append(plan_config)

    # Construction plan (for development assets)
    if hasattr(asset, "construction_plan") and asset.construction_plan:
        config["construction_plan"] = asset.construction_plan.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )

    # Absorption plans
    if hasattr(asset, "absorption_plans") and asset.absorption_plans:
        config["absorption_plans"] = []
        for plan in asset.absorption_plans:
            plan_config = plan.model_dump(
                exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
            )
            config["absorption_plans"].append(plan_config)

    # Operating assumptions (expenses, losses)
    if hasattr(asset, "expenses") and asset.expenses:
        config["expenses"] = asset.expenses.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )

    if hasattr(asset, "losses") and asset.losses:
        config["losses"] = asset.losses.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )

    return config


def _extract_financing_config(
    financing, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """Extract financing configuration including all facilities."""
    config = {
        "_class_name": type(financing).__name__,
        "_object_type": _classify_performa_object(financing),
    }

    financing_config = financing.model_dump(
        exclude_defaults=exclude_defaults,
        exclude_unset=exclude_unset,
        exclude={"facilities"},
    )
    config.update(financing_config)

    # Facilities
    config["facilities"] = []
    for facility in financing.facilities:
        facility_config = facility.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )

        # Add facility class information
        facility_config["_class_name"] = type(facility).__name__
        facility_config["_object_type"] = _classify_performa_object(facility)

        config["facilities"].append(facility_config)

    return config


def _extract_partnership_config(
    partnership, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """Extract partnership configuration including partners and promotes."""
    config = {
        "_class_name": type(partnership).__name__,
        "_object_type": _classify_performa_object(partnership),
    }

    partnership_config = partnership.model_dump(
        exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
    )
    config.update(partnership_config)

    return config


def compare_deal_configs(
    deal1: Deal, deal2: Deal, name1: str = "Deal 1", name2: str = "Deal 2"
) -> Dict[str, Any]:
    """
    Compare configurations between two deals to spot differences.

    Args:
        deal1: First deal to compare
        deal2: Second deal to compare
        name1: Label for first deal
        name2: Label for second deal

    Returns:
        Dictionary showing parameter differences between deals
    """
    config1 = dump_deal_config(deal1, exclude_defaults=True)
    config2 = dump_deal_config(deal2, exclude_defaults=True)

    differences = {}

    # Compare each section
    for section in config1.keys():
        if section in config2:
            section_diffs = _compare_dict_values(
                config1[section],
                config2[section],
                f"{name1}.{section}",
                f"{name2}.{section}",
            )
            if section_diffs:
                differences[section] = section_diffs
        else:
            differences[section] = {f"missing_in_{name2}": config1[section]}

    # Check for sections only in deal2
    for section in config2.keys():
        if section not in config1:
            differences[section] = {f"missing_in_{name1}": config2[section]}

    return differences


def _compare_dict_values(
    dict1: Dict, dict2: Dict, path1: str, path2: str
) -> Dict[str, Any]:
    """Recursively compare dictionary values and return differences."""
    differences = {}

    all_keys = set(dict1.keys()) | set(dict2.keys())

    for key in all_keys:
        if key not in dict1:
            differences[key] = {path2: dict2[key], path1: "<MISSING>"}
        elif key not in dict2:
            differences[key] = {path1: dict1[key], path2: "<MISSING>"}
        elif dict1[key] != dict2[key]:
            if isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
                # Recursive comparison for nested dicts
                nested_diffs = _compare_dict_values(
                    dict1[key], dict2[key], f"{path1}.{key}", f"{path2}.{key}"
                )
                if nested_diffs:
                    differences[key] = nested_diffs
            else:
                differences[key] = {path1: dict1[key], path2: dict2[key]}

    return differences


def analyze_ledger_semantically(ledger: Ledger) -> Dict[str, Any]:
    """
    Comprehensive semantic analysis of ledger for debugging.

    Provides structured analysis to identify:
    - Cash flow patterns and anomalies
    - Timeline validation issues
    - Sign and magnitude problems
    - Balance and consistency checks

    Args:
        ledger: Ledger object to analyze

    Returns:
        Structured analysis dictionary with multiple analysis dimensions

    Example:
        ```python
        analysis = analyze_ledger_semantically(ledger)
        print(f"Revenue total: ${analysis['by_category']['Revenue']['total']:,.0f}")
        print(f"Timeline issues: {analysis['anomalies']['timeline']}")
        ```
    """
    # Get ledger DataFrame
    if hasattr(ledger, "_to_dataframe"):
        df = ledger._to_dataframe()
    elif isinstance(ledger, pd.DataFrame):
        df = ledger
    else:
        # Try to get DataFrame from ledger object
        df = getattr(ledger, "df", None) or getattr(ledger, "data", None)
        if df is None:
            return {
                "error": "Could not extract DataFrame from ledger",
                "ledger_type": type(ledger).__name__,
            }

    if df.empty:
        return {"error": "Ledger is empty", "record_count": 0}

    analysis = {
        "record_count": len(df),
        "date_range": {
            "start": df["date"].min(),
            "end": df["date"].max(),
            "span_months": None,
        },
        "by_category": {},
        "by_timeline": {},
        "anomalies": {},
        "balance_checks": {},
        "summary_stats": {},
    }

    # Calculate date span
    if pd.notnull(df["date"].min()) and pd.notnull(df["date"].max()):
        date_span = df["date"].max() - df["date"].min()
        analysis["date_range"]["span_months"] = (
            date_span.days / 30.44
        )  # Average month length

    # Analysis by financial category
    analysis["by_category"] = _analyze_by_category(df)

    # Analysis by timeline phases
    analysis["by_timeline"] = _analyze_by_timeline(df)

    # Anomaly detection
    analysis["anomalies"] = _detect_anomalies(df)

    # Balance validation
    analysis["balance_checks"] = _validate_balances(df)

    # Summary statistics
    analysis["summary_stats"] = _calculate_summary_stats(df)

    return analysis


def _analyze_by_category(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze ledger entries by financial category."""
    if "category" not in df.columns:
        return {"error": "No category column in ledger"}

    category_summary = {}

    for category in df["category"].unique():
        cat_data = df[df["category"] == category]

        category_summary[category] = {
            "total": cat_data["amount"].sum(),
            "count": len(cat_data),
            "avg_amount": cat_data["amount"].mean(),
            "date_range": {
                "first": cat_data["date"].min(),
                "last": cat_data["date"].max(),
            },
            "subcategories": {},
        }

        # Subcategory breakdown
        if "subcategory" in df.columns:
            for subcat in cat_data["subcategory"].unique():
                subcat_data = cat_data[cat_data["subcategory"] == subcat]
                category_summary[category]["subcategories"][subcat] = {
                    "total": subcat_data["amount"].sum(),
                    "count": len(subcat_data),
                }

    return category_summary


def _analyze_by_timeline(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze ledger entries by timeline phases."""
    timeline_analysis = {"by_year": {}, "by_month": {}, "cumulative_by_year": {}}

    # Convert dates for grouping
    df["year"] = pd.to_datetime(df["date"]).dt.year
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")

    # Yearly analysis
    yearly = df.groupby("year")["amount"].sum()
    timeline_analysis["by_year"] = yearly.to_dict()

    # Monthly analysis (first 24 months only to avoid clutter)
    monthly = df.groupby("month")["amount"].sum()
    timeline_analysis["by_month"] = dict(monthly.head(24))

    # Cumulative by year
    cumulative = yearly.cumsum()
    timeline_analysis["cumulative_by_year"] = cumulative.to_dict()

    return timeline_analysis


def _detect_anomalies(df: pd.DataFrame) -> Dict[str, List[str]]:
    """Detect potential issues in ledger data."""
    warnings = {"magnitude": [], "timing": [], "sign": [], "balance": []}

    # Magnitude checks
    amounts = df["amount"].abs()
    if amounts.max() > amounts.median() * 100:
        warnings["magnitude"].append(
            f"Extreme outlier: ${amounts.max():,.0f} is {amounts.max() / amounts.median():.0f}x median"
        )

    # Sign checks (basic heuristics)
    if "category" in df.columns and "subcategory" in df.columns:
        # Revenue should generally be positive
        revenue_negative = df[(df["category"] == "Revenue") & (df["amount"] < 0)]
        if len(revenue_negative) > 0:
            warnings["sign"].append(
                f"Negative revenue entries: {len(revenue_negative)} records"
            )

        # Expenses should generally be negative
        expense_positive = df[(df["category"] == "Expense") & (df["amount"] > 0)]
        if len(expense_positive) > 0:
            warnings["sign"].append(
                f"Positive expense entries: {len(expense_positive)} records"
            )

    # Timeline checks
    if "date" in df.columns:
        # Check for future dates (potential config error)
        future_dates = df[pd.to_datetime(df["date"]) > datetime.now()]
        if len(future_dates) > 0:
            max_future = pd.to_datetime(future_dates["date"]).max()
            warnings["timing"].append(
                f"Future dates detected (latest: {max_future.date()})"
            )

        # Check for entries spanning > 20 years (potential config error)
        date_span_years = (
            pd.to_datetime(df["date"]).max() - pd.to_datetime(df["date"]).min()
        ).days / 365
        if date_span_years > 20:
            warnings["timing"].append(
                f"Very long timeline: {date_span_years:.1f} years"
            )

    return warnings


def _validate_balances(df: pd.DataFrame) -> Dict[str, Any]:
    """Validate mathematical balances in ledger."""
    balances = {
        "total_net_flow": df["amount"].sum(),
        "positive_flows": df[df["amount"] > 0]["amount"].sum(),
        "negative_flows": df[df["amount"] < 0]["amount"].sum(),
    }

    # Check if net flow is close to zero (should be for closed deals)
    balances["net_flow_close_to_zero"] = abs(balances["total_net_flow"]) < 1000
    balances["balance_ratio"] = (
        abs(balances["negative_flows"] / balances["positive_flows"])
        if balances["positive_flows"] > 0
        else None
    )

    return balances


def _calculate_summary_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate high-level summary statistics."""
    stats = {
        "total_records": len(df),
        "total_amount": df["amount"].sum(),
        "amount_stats": {
            "mean": df["amount"].mean(),
            "median": df["amount"].median(),
            "std": df["amount"].std(),
            "min": df["amount"].min(),
            "max": df["amount"].max(),
        },
    }

    # Category counts
    if "category" in df.columns:
        stats["category_counts"] = df["category"].value_counts().to_dict()

    return stats


def format_config_analysis(
    config: Dict[str, Any], title: str = "Deal Configuration"
) -> str:
    """
    Format configuration analysis as readable text.

    Args:
        config: Configuration dictionary from dump_deal_config()
        title: Title for the analysis output

    Returns:
        Formatted string suitable for printing or logging
    """
    output = [f"# {title}\n"]

    # Deal-level info
    if "deal" in config:
        output.append("## Deal Overview")
        deal_info = config["deal"]
        if "name" in deal_info:
            output.append(f"- **Name**: {deal_info['name']}")
        if "description" in deal_info:
            output.append(f"- **Description**: {deal_info['description']}")
        output.append("")

    # Asset configuration
    if "asset" in config:
        output.append("## Asset Configuration")
        asset = config["asset"]

        # Basic property info
        if "net_rentable_area" in asset:
            output.append(
                f"- **Net Rentable Area**: {asset['net_rentable_area']:,.0f} SF"
            )
        if "property_type" in asset:
            output.append(f"- **Property Type**: {asset['property_type']}")

        # Construction costs (for development)
        if "_computed" in asset:
            computed = asset["_computed"]
            if "total_project_cost" in computed:
                output.append(
                    f"- **Total Project Cost**: ${computed['total_project_cost']:,.0f}"
                )
            if "total_construction_cost" in computed:
                output.append(
                    f"- **Construction Cost**: ${computed['total_construction_cost']:,.0f}"
                )

        output.append("")

    # Financing configuration
    if "financing" in config:
        output.append("## Financing Configuration")
        financing = config["financing"]

        if "facilities" in financing:
            for i, facility in enumerate(financing["facilities"]):
                facility_type = facility.get("_facility_type", "Facility")
                output.append(f"### {facility_type} {i + 1}")

                if "loan_amount" in facility:
                    output.append(f"- **Loan Amount**: ${facility['loan_amount']:,.0f}")
                if "interest_rate" in facility:
                    rate = facility["interest_rate"]
                    if isinstance(rate, dict):
                        # Handle complex rate structures
                        if "details" in rate and "rate" in rate["details"]:
                            output.append(
                                f"- **Interest Rate**: {rate['details']['rate']:.2%}"
                            )
                    else:
                        output.append(f"- **Interest Rate**: {rate:.2%}")
                if "ltv_ratio" in facility:
                    output.append(f"- **LTV Ratio**: {facility['ltv_ratio']:.1%}")
                if "loan_term_years" in facility:
                    output.append(
                        f"- **Loan Term**: {facility['loan_term_years']} years"
                    )

        output.append("")

    # Exit configuration
    if "exit" in config:
        output.append("## Exit Configuration")
        exit_config = config["exit"]

        if "cap_rate" in exit_config:
            output.append(f"- **Exit Cap Rate**: {exit_config['cap_rate']:.2%}")
        if "hold_period_months" in exit_config:
            output.append(
                f"- **Hold Period**: {exit_config['hold_period_months']} months"
            )
        if "transaction_costs_rate" in exit_config:
            output.append(
                f"- **Transaction Costs**: {exit_config['transaction_costs_rate']:.1%}"
            )

        output.append("")

    return "\n".join(output)


def format_ledger_analysis(
    analysis: Dict[str, Any], title: str = "Ledger Analysis"
) -> str:
    """
    Format ledger analysis as readable text.

    Args:
        analysis: Analysis dictionary from analyze_ledger_semantically()
        title: Title for the analysis output

    Returns:
        Formatted string suitable for printing or logging
    """
    if "error" in analysis:
        return f"# {title}\n\n❌ Error: {analysis['error']}"

    output = [f"# {title}\n"]

    # Basic info
    output.append(f"**Records**: {analysis['record_count']:,}")
    if analysis["date_range"]["span_months"]:
        output.append(
            f"**Timeline**: {analysis['date_range']['span_months']:.1f} months"
        )
    output.append("")

    # Category summary
    if "by_category" in analysis:
        output.append("## Cash Flow by Category")
        output.append("| Category | Total Amount | Count | Avg Amount |")
        output.append("|----------|--------------|-------|------------|")

        for category, data in analysis["by_category"].items():
            if isinstance(data, dict) and "total" in data:
                output.append(
                    f"| {category} | ${data['total']:,.0f} | {data['count']} | ${data['avg_amount']:,.0f} |"
                )

        output.append("")

    # Anomaly warnings
    if "anomalies" in analysis:
        anomalies = analysis["anomalies"]
        has_warnings = any(len(warnings) > 0 for warnings in anomalies.values())

        if has_warnings:
            output.append("## ⚠️ Anomalies Detected")
            for category, warnings in anomalies.items():
                if warnings:
                    output.append(f"### {category.title()} Issues")
                    for warning in warnings:
                        output.append(f"- {warning}")
            output.append("")

    # Balance validation
    if "balance_checks" in analysis:
        balances = analysis["balance_checks"]
        output.append("## Balance Validation")
        output.append(f"- **Net Flow**: ${balances['total_net_flow']:,.0f}")
        output.append(f"- **Positive Flows**: ${balances['positive_flows']:,.0f}")
        output.append(f"- **Negative Flows**: ${balances['negative_flows']:,.0f}")

        if balances["net_flow_close_to_zero"]:
            output.append("- **Balance Check**: ✅ Net flow ~$0 (good)")
        else:
            output.append(
                f"- **Balance Check**: ⚠️ Net flow ${balances['total_net_flow']:,.0f}"
            )

        output.append("")

    return "\n".join(output)


def ledger_sanity_check(
    ledger, expected_returns: Optional[Dict[str, float]] = None
) -> List[str]:
    """
    Quick sanity check for common ledger issues.

    Args:
        ledger: Ledger to check
        expected_returns: Optional dict with expected IRR/EM for validation
            e.g., {"irr": 0.12, "equity_multiple": 1.8}

    Returns:
        List of warning/error messages
    """
    warnings = []
    analysis = analyze_ledger_semantically(ledger)

    # Check for empty ledger
    if analysis.get("record_count", 0) == 0:
        warnings.append("❌ CRITICAL: Ledger is empty")
        return warnings

    # Check anomalies
    for category, issues in analysis.get("anomalies", {}).items():
        for issue in issues:
            warnings.append(f"⚠️ {category.title()}: {issue}")

    # Balance validation
    balance_checks = analysis.get("balance_checks", {})
    if not balance_checks.get("net_flow_close_to_zero", True):
        net_flow = balance_checks.get("total_net_flow", 0)
        warnings.append(f"⚠️ Balance: Net flow ${net_flow:,.0f} (should be ~$0)")

    # Expected returns validation
    if expected_returns:
        # We'd need to calculate actual returns from ledger here
        # This would require implementing IRR calculation from ledger cash flows
        pass  # TODO: Implement return calculation validation

    if not warnings:
        warnings.append("✅ No obvious ledger issues detected")

    return warnings


def format_performa_object(obj: Any, title: Optional[str] = None) -> str:
    """
    Format any Performa object analysis as readable text.

    Args:
        obj: Any Performa object to analyze and format
        title: Optional title for the output

    Returns:
        Formatted string showing object class info and key parameters

    Example:
        ```python
        print(format_performa_object(residential_pattern))
        print(format_performa_object(timeline, "Project Timeline"))
        ```
    """
    analysis = dump_performa_object(obj, exclude_defaults=True, include_computed=True)

    # Generate title
    if title is None:
        class_name = analysis["_object_info"]["class_name"]
        object_type = analysis["_object_info"]["object_type"]
        title = f"{class_name} ({object_type})"

    output = [f"# {title}\n"]

    # Object metadata
    obj_info = analysis["_object_info"]
    output.append("## Object Information")
    output.append(f"- **Class**: `{obj_info['class_name']}`")
    output.append(f"- **Type**: {obj_info['object_type']}")
    output.append(f"- **Module**: `{obj_info['module']}`")
    output.append("")

    # Configuration summary
    config = analysis["config"]
    output.append("## Configuration")

    # Handle different object types appropriately
    if obj_info["object_type"] == "Pattern":
        _format_pattern_config(config, output)
    elif obj_info["object_type"] == "Asset":
        _format_asset_config(config, output)
    elif obj_info["object_type"] == "Debt":
        _format_debt_config(config, output)
    elif obj_info["object_type"] == "Primitive":
        _format_primitive_config(config, output)
    else:
        _format_generic_config(config, output)

    return "\n".join(output)


def analyze_configuration_intentionality(
    obj: Any, critical_params: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze configuration intentionality: what's user-specified vs defaulted.

    This analysis is CRITICAL for financial modeling where defaults can be
    dangerous and lead to unrealistic or inappropriate assumptions.

    Args:
        obj: Any Performa object to analyze
        critical_params: List of parameters that should rarely use defaults
                        (e.g., ['cap_rate', 'interest_rate', 'rent_psf'])

    Returns:
        Dict containing intentionality analysis with risk assessment

    Example:
        ```python
        analysis = analyze_configuration_intentionality(pattern,
            critical_params=['exit_cap_rate', 'target_rent', 'construction_cost_per_unit'])

        print(f"Configuration completeness: {analysis['completeness_score']:.1%}")
        print(f"Critical defaults: {len(analysis['critical_defaults'])}")
        ```
    """
    # Get three views of the configuration
    user_only = dump_performa_object(obj, exclude_defaults=True, exclude_unset=True)
    user_and_set_defaults = dump_performa_object(
        obj, exclude_defaults=True, exclude_unset=False
    )
    full_config = dump_performa_object(obj, exclude_defaults=False, exclude_unset=False)

    analysis = {
        "configuration_views": {
            "user_explicit": user_only["config"],
            "user_plus_set_defaults": user_and_set_defaults["config"],
            "full_with_all_defaults": full_config["config"],
        },
        "intentionality_metrics": {},
        "risk_assessment": {},
        "recommendations": [],
    }

    # Calculate configuration metrics
    user_params = _count_config_parameters(user_only["config"])
    set_params = _count_config_parameters(user_and_set_defaults["config"])
    total_params = _count_config_parameters(full_config["config"])

    analysis["intentionality_metrics"] = {
        "user_explicit_count": user_params,
        "user_plus_set_count": set_params,
        "total_available_count": total_params,
        "explicit_ratio": user_params / total_params if total_params > 0 else 0,
        "defaulted_ratio": (total_params - set_params) / total_params
        if total_params > 0
        else 0,
        "completeness_score": set_params / total_params if total_params > 0 else 0,
    }

    # Identify defaulted parameters
    defaulted_params = _identify_defaulted_parameters(
        user_and_set_defaults["config"], full_config["config"]
    )

    # Risk assessment for critical parameters
    if critical_params:
        critical_defaults = []
        for param in critical_params:
            if _is_parameter_defaulted(
                param, user_and_set_defaults["config"], full_config["config"]
            ):
                critical_defaults.append(param)

        analysis["risk_assessment"] = {
            "critical_defaults": critical_defaults,
            "critical_default_count": len(critical_defaults),
            "critical_risk_score": len(critical_defaults) / len(critical_params)
            if critical_params
            else 0,
        }

        # Generate recommendations
        if critical_defaults:
            analysis["recommendations"].append(
                f"⚠️ RISK: {len(critical_defaults)} critical parameters using defaults: {critical_defaults}"
            )
            analysis["recommendations"].append(
                "💡 Review these defaults carefully - they may not suit your specific deal/market"
            )

    analysis["defaulted_parameters"] = defaulted_params

    # Configuration quality assessment
    completeness = analysis["intentionality_metrics"]["completeness_score"]
    if completeness < 0.3:
        analysis["recommendations"].append(
            "⚠️ LOW configuration completeness - many parameters using defaults"
        )
    elif completeness < 0.7:
        analysis["recommendations"].append(
            "📊 MEDIUM configuration completeness - review key defaults"
        )
    else:
        analysis["recommendations"].append(
            "✅ HIGH configuration completeness - well-specified model"
        )

    return analysis


def compare_configuration_intentionality(
    obj1: Any, obj2: Any, name1: str = "Object 1", name2: str = "Object 2"
) -> Dict[str, Any]:
    """
    Compare configuration intentionality between two similar objects.

    Critical for validating that pattern and compositional approaches
    have equivalent levels of configuration intentionality, not just
    equivalent outputs.

    Args:
        obj1: First object to compare
        obj2: Second object to compare
        name1: Label for first object
        name2: Label for second object

    Returns:
        Dict containing comparative intentionality analysis

    Example:
        ```python
        comparison = compare_configuration_intentionality(
            comp_deal, pattern_deal, "Composition", "Pattern"
        )

        if comparison['intentionality_parity']:
            print("✅ Both approaches have equivalent configuration depth")
        else:
            print(f"⚠️ Configuration depth mismatch: {comparison['differences']}")
        ```
    """
    analysis1 = analyze_configuration_intentionality(obj1)
    analysis2 = analyze_configuration_intentionality(obj2)

    comparison = {
        "objects": {name1: analysis1, name2: analysis2},
        "metrics_comparison": {},
        "intentionality_parity": False,
        "differences": [],
        "recommendations": [],
    }

    # Compare key metrics
    metrics1 = analysis1["intentionality_metrics"]
    metrics2 = analysis2["intentionality_metrics"]

    comparison["metrics_comparison"] = {
        "completeness_scores": {
            name1: metrics1["completeness_score"],
            name2: metrics2["completeness_score"],
        },
        "explicit_ratios": {
            name1: metrics1["explicit_ratio"],
            name2: metrics2["explicit_ratio"],
        },
        "defaulted_ratios": {
            name1: metrics1["defaulted_ratio"],
            name2: metrics2["defaulted_ratio"],
        },
    }

    # Check for intentionality parity (within 10% tolerance)
    completeness_diff = abs(
        metrics1["completeness_score"] - metrics2["completeness_score"]
    )
    explicit_diff = abs(metrics1["explicit_ratio"] - metrics2["explicit_ratio"])

    comparison["intentionality_parity"] = (
        completeness_diff < 0.1 and explicit_diff < 0.1
    )

    if not comparison["intentionality_parity"]:
        comparison["differences"].append(
            f"Completeness gap: {name1} {metrics1['completeness_score']:.1%} vs "
            f"{name2} {metrics2['completeness_score']:.1%}"
        )
        comparison["differences"].append(
            f"Explicit config gap: {name1} {metrics1['explicit_ratio']:.1%} vs "
            f"{name2} {metrics2['explicit_ratio']:.1%}"
        )

    # Risk comparison
    risk1 = analysis1.get("risk_assessment", {})
    risk2 = analysis2.get("risk_assessment", {})

    if risk1.get("critical_defaults") or risk2.get("critical_defaults"):
        comparison["recommendations"].append(
            "⚠️ One or both objects have critical parameters using defaults"
        )

    return comparison


def generate_configuration_report(
    obj: Any,
    critical_params: Optional[List[str]] = None,
    include_recommendations: bool = True,
) -> str:
    """
    Generate comprehensive configuration intentionality report.

    Provides actionable insights about configuration quality and potential
    risks from over-reliance on defaults in financial modeling.

    Args:
        obj: Object to analyze
        critical_params: Parameters that should rarely use defaults
        include_recommendations: Include actionable recommendations

    Returns:
        Formatted report string with configuration analysis

    Example:
        ```python
        report = generate_configuration_report(
            residential_pattern,
            critical_params=['exit_cap_rate', 'target_rent', 'construction_cost_per_unit']
        )
        print(report)
        ```
    """
    analysis = analyze_configuration_intentionality(obj, critical_params)

    # Object identification
    obj_info = dump_performa_object(obj)["_object_info"]
    title = f"{obj_info['class_name']} Configuration Analysis"

    output = [f"# {title}\n"]

    # Object metadata
    output.append("## Object Information")
    output.append(f"- **Class**: `{obj_info['class_name']}`")
    output.append(f"- **Type**: {obj_info['object_type']}")
    output.append(f"- **Module**: `{obj_info['module']}`")
    output.append("")

    # Configuration metrics
    metrics = analysis["intentionality_metrics"]
    output.append("## Configuration Metrics")
    output.append(f"- **User Explicit Parameters**: {metrics['user_explicit_count']}")
    output.append(
        f"- **Total Available Parameters**: {metrics['total_available_count']}"
    )
    output.append(
        f"- **Configuration Completeness**: {metrics['completeness_score']:.1%}"
    )
    output.append(f"- **Explicit Configuration**: {metrics['explicit_ratio']:.1%}")
    output.append(f"- **Using Defaults**: {metrics['defaulted_ratio']:.1%}")
    output.append("")

    # Risk assessment
    if "risk_assessment" in analysis and analysis["risk_assessment"]:
        risk = analysis["risk_assessment"]
        output.append("## ⚠️ Risk Assessment")
        output.append(
            f"- **Critical Defaults Count**: {risk['critical_default_count']}"
        )
        output.append(f"- **Critical Risk Score**: {risk['critical_risk_score']:.1%}")

        if risk["critical_defaults"]:
            output.append("- **Critical Parameters Using Defaults**:")
            for param in risk["critical_defaults"]:
                output.append(f"  - `{param}`")
        output.append("")

    # Defaulted parameters (non-critical)
    defaulted = analysis["defaulted_parameters"]
    if defaulted:
        output.append("## Parameters Using Defaults")
        output.append(
            "Parameters relying on system defaults (review for appropriateness):"
        )
        output.append("")
        for param in sorted(defaulted)[:10]:  # Show first 10 to avoid clutter
            output.append(f"- `{param}`")

        if len(defaulted) > 10:
            output.append(f"- ... and {len(defaulted) - 10} more")
        output.append("")

    # Recommendations
    if include_recommendations and analysis["recommendations"]:
        output.append("## 💡 Recommendations")
        for rec in analysis["recommendations"]:
            output.append(f"- {rec}")
        output.append("")

    return "\n".join(output)


def _count_config_parameters(config: Dict[str, Any]) -> int:
    """
    Count total parameters in configuration dictionary.

    Recursively counts parameters while excluding metadata fields
    that start with underscore.

    Args:
        config: Configuration dictionary to count

    Returns:
        Total count of configuration parameters
    """
    count = 0

    for key, value in config.items():
        # Skip metadata fields
        if key.startswith("_"):
            continue

        if isinstance(value, dict):
            # Recursively count nested dictionaries
            count += _count_config_parameters(value)
        elif isinstance(value, list):
            # Count list items that are dictionaries
            for item in value:
                if isinstance(item, dict):
                    count += _count_config_parameters(item)
                else:
                    count += 1
        else:
            count += 1

    return count


def _identify_defaulted_parameters(
    user_config: Dict[str, Any], full_config: Dict[str, Any]
) -> List[str]:
    """
    Identify parameters that are using defaults (not explicitly set by user).

    Compares user-specified configuration against full configuration to
    identify parameters that are relying on system defaults.

    Args:
        user_config: Configuration with user-specified values only
        full_config: Complete configuration including defaults

    Returns:
        List of parameter names that are using defaults
    """
    defaulted = []

    def _find_defaulted_recursive(
        user_dict: Dict[str, Any], full_dict: Dict[str, Any], prefix: str = ""
    ):
        for key, full_value in full_dict.items():
            # Skip metadata fields
            if key.startswith("_"):
                continue

            full_key = f"{prefix}.{key}" if prefix else key

            if key not in user_dict:
                # Parameter exists in full but not in user config = defaulted
                defaulted.append(full_key)
            elif isinstance(full_value, dict) and isinstance(user_dict.get(key), dict):
                # Recursively check nested dictionaries
                _find_defaulted_recursive(user_dict[key], full_value, full_key)
            elif isinstance(full_value, list) and isinstance(user_dict.get(key), list):
                # Handle lists (like facilities, unit_mix, etc.)
                user_list = user_dict[key]
                full_list = full_value

                for i, full_item in enumerate(full_list):
                    if (
                        i < len(user_list)
                        and isinstance(full_item, dict)
                        and isinstance(user_list[i], dict)
                    ):
                        _find_defaulted_recursive(
                            user_list[i], full_item, f"{full_key}[{i}]"
                        )

    _find_defaulted_recursive(user_config, full_config)
    return defaulted


def _is_parameter_defaulted(
    param_name: str, user_config: Dict[str, Any], full_config: Dict[str, Any]
) -> bool:
    """
    Check if a specific parameter is using defaults.

    Args:
        param_name: Name of parameter to check (supports dot notation for nested)
        user_config: User-specified configuration
        full_config: Full configuration including defaults

    Returns:
        True if parameter is using defaults, False if user-specified
    """

    # Handle dot notation for nested parameters (e.g., "exit.cap_rate")
    def _get_nested_value(config: Dict[str, Any], path: str) -> Any:
        keys = path.split(".")
        value = config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    user_value = _get_nested_value(user_config, param_name)
    full_value = _get_nested_value(full_config, param_name)

    # Parameter is defaulted if it exists in full config but not in user config
    return full_value is not None and user_value is None


def create_actionable_config_summary(
    obj: Any, focus_areas: Optional[List[str]] = None
) -> Tuple[str, List[str]]:
    """
    Create actionable configuration summary with specific next steps.

    Provides focused insights and concrete actions for improving
    configuration quality and reducing reliance on potentially
    inappropriate defaults.

    Args:
        obj: Object to analyze
        focus_areas: Specific parameter categories to focus on
                    (e.g., ['financing', 'exit', 'asset'])

    Returns:
        Tuple of (summary_text, action_items)

    Example:
        ```python
        summary, actions = create_actionable_config_summary(
            pattern, focus_areas=['financing', 'exit']
        )

        print(summary)
        for action in actions:
            print(f"TODO: {action}")
        ```
    """
    # Define critical parameters by object type
    obj_type = _classify_performa_object(obj)
    critical_params = _get_critical_params_by_type(obj_type, focus_areas)

    analysis = analyze_configuration_intentionality(obj, critical_params)

    # Generate summary
    obj_info = dump_performa_object(obj)["_object_info"]
    metrics = analysis["intentionality_metrics"]

    summary_lines = [
        f"📊 **{obj_info['class_name']}** Configuration Summary",
        f"   • Completeness: {metrics['completeness_score']:.1%}",
        f"   • Explicit: {metrics['explicit_ratio']:.1%}",
        f"   • Using Defaults: {metrics['defaulted_ratio']:.1%}",
    ]

    # Risk summary
    if (
        "risk_assessment" in analysis
        and analysis["risk_assessment"]["critical_defaults"]
    ):
        critical_count = analysis["risk_assessment"]["critical_default_count"]
        summary_lines.append(f"   • ⚠️ Critical Defaults: {critical_count}")
    else:
        summary_lines.append("   • ✅ No Critical Defaults")

    summary = "\n".join(summary_lines)

    # Generate actionable items
    action_items = []

    # Configuration completeness actions
    if metrics["completeness_score"] < 0.5:
        action_items.append(
            f"Review {obj_info['class_name']} configuration - low completeness ({metrics['completeness_score']:.1%})"
        )

    # Critical defaults actions
    if "risk_assessment" in analysis:
        for param in analysis["risk_assessment"].get("critical_defaults", []):
            action_items.append(
                f"Specify explicit value for critical parameter: {param}"
            )

    # General recommendations
    action_items.extend(analysis["recommendations"])

    return summary, action_items


def _get_critical_params_by_type(
    obj_type: str, focus_areas: Optional[List[str]] = None
) -> List[str]:
    """
    Get critical parameters that should rarely use defaults by object type.

    Args:
        obj_type: Object type from _classify_performa_object
        focus_areas: Specific areas to focus on (optional)

    Returns:
        List of critical parameter names for the object type
    """
    # Define critical parameters by object type - these should rarely use defaults
    critical_by_type = {
        "Pattern": [
            "exit_cap_rate",
            "target_rent",
            "construction_cost_per_unit",
            "land_cost",
            "interest_rate",
            "ltv_ratio",
            "purchase_price",
        ],
        "Deal": [
            "acquisition.purchase_price",
            "exit.cap_rate",
            "financing.facilities",
            "asset.rent_roll",
            "asset.expenses",
        ],
        "Asset": ["rent_roll", "expenses", "absorption_plans", "construction_plan"],
        "Debt": ["loan_amount", "interest_rate", "ltv_ratio", "dscr_hurdle"],
        "Valuation": ["cap_rate", "hold_period_months", "transaction_costs_rate"],
    }

    base_critical = critical_by_type.get(obj_type, [])

    # Filter by focus areas if specified
    if focus_areas:
        filtered = []
        for param in base_critical:
            for area in focus_areas:
                if area.lower() in param.lower():
                    filtered.append(param)
        return filtered

    return base_critical


def _format_pattern_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format pattern object configuration for readable output.

    Pattern objects (ResidentialDevelopmentPattern, OfficeDevelopmentPattern, etc.)
    have specific high-level parameters that are most relevant for debugging.
    This formatter extracts and displays the key pattern parameters in a
    structured, human-readable format.

    Args:
        config: Pattern configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Key Parameters Displayed:
        - project_name: Deal/project identifier
        - total_units: Unit count (for residential patterns)
        - net_rentable_area: Area in SF (for office patterns)
        - land_cost: Land acquisition cost
        - Computed properties: total_project_cost, derived_timeline
    """
    # Key pattern parameters
    if "project_name" in config:
        output.append(f"- **Project**: {config['project_name']}")
    if "total_units" in config:
        output.append(f"- **Units**: {config['total_units']:,}")
    if "net_rentable_area" in config:
        output.append(f"- **Area**: {config['net_rentable_area']:,} SF")
    if "land_cost" in config:
        output.append(f"- **Land Cost**: ${config['land_cost']:,}")

    # Computed properties
    if "_computed" in config:
        computed = config["_computed"]
        if "total_project_cost" in computed:
            output.append(
                f"- **Total Project Cost**: ${computed['total_project_cost']:,}"
            )
        if "derived_timeline" in computed:
            timeline = computed["derived_timeline"]
            output.append(f"- **Timeline**: {timeline['duration_months']} months")


def _format_asset_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format asset object configuration for readable output.

    Asset objects (ResidentialProperty, DevelopmentProject, etc.) have
    property-specific parameters that are crucial for understanding the
    underlying real estate asset being modeled.

    Args:
        config: Asset configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Key Parameters Displayed:
        - net_rentable_area: Leasable area in square feet
        - property_type: Asset type (RESIDENTIAL, OFFICE, etc.)
        - Computed properties: total_project_cost (for development assets)
    """
    # Asset basics
    if "net_rentable_area" in config:
        output.append(f"- **Net Rentable Area**: {config['net_rentable_area']:,} SF")
    if "property_type" in config:
        output.append(f"- **Property Type**: {config['property_type']}")

    # Computed properties
    if "_computed" in config:
        computed = config["_computed"]
        if "total_project_cost" in computed:
            output.append(
                f"- **Total Project Cost**: ${computed['total_project_cost']:,}"
            )


def _format_debt_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format debt object configuration for readable output.

    Debt objects (FinancingPlan, ConstructionFacility, PermanentFacility, etc.)
    have financing-specific parameters that are essential for understanding
    deal leverage, cash-out refinancing potential, and debt service coverage.

    Args:
        config: Debt configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Key Parameters Displayed:
        - name: Financing plan or facility name
        - facilities: Individual debt facilities with class identification
        - loan_amount: Principal amount for each facility
        - interest_rate: Borrowing cost for each facility

    Special Focus:
        - Class identification for each facility (critical for cash-out analysis)
        - Loan amounts for construction vs permanent (enables cash-out calculation)
    """
    if "name" in config:
        output.append(f"- **Name**: {config['name']}")

    # Facilities
    if "facilities" in config:
        facilities = config["facilities"]
        output.append(f"- **Facilities**: {len(facilities)} facilities")
        output.append("")
        output.append("### Facilities")

        for i, facility in enumerate(facilities):
            facility_class = facility.get("_class_name", "Unknown")
            facility_name = facility.get("name", "Unnamed")
            output.append(f"#### {i + 1}. {facility_class}")
            output.append(f"- **Name**: {facility_name}")

            if "loan_amount" in facility:
                output.append(f"- **Loan Amount**: ${facility['loan_amount']:,}")
            if "interest_rate" in facility:
                rate = facility["interest_rate"]
                if isinstance(rate, (int, float)):
                    output.append(f"- **Interest Rate**: {rate:.2%}")
            output.append("")


def _format_primitive_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format primitive object configuration for readable output.

    Primitive objects (Timeline, GlobalSettings, etc.) have system-level
    parameters that affect analysis behavior and execution context.

    Args:
        config: Primitive configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Key Parameters Displayed:
        - duration_months: Timeline duration for project analysis
        - start_date/end_date: Project timeline boundaries
        - period_frequency: Analysis frequency (monthly, quarterly, etc.)
        - Other system configuration parameters
    """
    # Show key primitive parameters
    key_params = ["duration_months", "start_date", "end_date", "period_frequency"]
    for param in key_params:
        if param in config:
            output.append(f"- **{param.replace('_', ' ').title()}**: {config[param]}")


def _format_generic_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format unknown object configuration for readable output.

    This formatter handles objects that don't fit into standard Performa
    categories, providing basic parameter visibility for debugging purposes.

    Args:
        config: Generic configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Display Strategy:
        - Shows generic object note
        - Lists first few public parameters for inspection
        - Provides minimal useful information for debugging
    """
    output.append("- **Configuration**: Generic object")

    # Show first few non-private keys
    public_keys = [k for k in config.keys() if not k.startswith("_")][:5]
    if public_keys:
        output.append(f"- **Key Parameters**: {', '.join(public_keys)}")
