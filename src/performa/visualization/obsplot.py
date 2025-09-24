# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Observable Plot visualization utilities for Performa.

This module provides clean utility functions for creating visualizations using
PyObsPlot, including data reshaping and common chart patterns for financial
modeling and real estate analysis.

## Basic Usage Example

```python
import pandas as pd
from pyobsplot import Plot
from performa.visualization.obsplot import (
    reshape_to_long_format,
    create_vertical_categorical_bar,
    create_horizontal_categorical_bar,
    create_cash_flow_time_series,
    quick_stacked_bar_from_multiindex
)

# Example 1: Quick plot from multi-index DataFrame
construction_costs = pd.DataFrame({
    ('Hard Costs', 'Site Work', 'Excavation'): [100000, 50000, 0],
    ('Hard Costs', 'Structure', 'Foundation'): [200000, 100000, 0],
    ('Soft Costs', 'Design', 'Architectural'): [50000, 25000, 12500],
}, index=pd.PeriodIndex(['2024-01', '2024-02', '2024-03'], freq='M'))

# One-liner to create stacked bar chart
plot_config = quick_stacked_bar_from_multiindex(
    construction_costs,
    title="Construction Costs by Category",
    column_names=["Cost Type", "Category", "Item"],
    scale_millions=False
)

# Render the plot
Plot.plot(plot_config)

# Example 2: Manual reshaping and plotting
long_df = reshape_to_long_format(
    construction_costs,
    column_names=["Cost Type", "Category", "Item"]
)

plot_config = create_vertical_categorical_bar(
    long_df,
    title="Construction Timeline",
    fill_column="Cost Type",
    y_label="Cost ($)",
    scale_millions=False
)

Plot.plot(plot_config)

# Example 3: Time series with cumulative data
cumulative_costs = construction_costs.cumsum()
long_cumulative = reshape_to_long_format(
    cumulative_costs,
    column_names=["Cost Type", "Category", "Item"]
)

area_config = create_cumulative_area_chart(
    long_cumulative,
    title="Cumulative Construction Costs",
    fill_column="Cost Type",
    scale_millions=False
)

Plot.plot(area_config)

# Example 4: Horizontal proportional stacked bar
cost_breakdown = pd.DataFrame({
    'Category': ['Hard Costs', 'Soft Costs', 'Land', 'Financing'],
    'Amount': [5000000, 1000000, 2000000, 500000]
})

horizontal_config = create_horizontal_stacked_bar(
    cost_breakdown,
    title="Development Cost Breakdown",
    show_percentages=True
)

Plot.plot(horizontal_config)

# Example 5: Cash flow warming stripes (bars span full height, only color varies)
cash_flow_data = pd.DataFrame({
    'Date': pd.period_range('2024-01', periods=12, freq='M'),
    'Amount': [-1000000, -500000, 100000, 200000, 300000, 400000,
              500000, 600000, 400000, 300000, 200000, -800000]
})

# Single warming stripe
cash_flow_config = create_cash_flow_time_series(
    cash_flow_data,
    title="Project Cash Flow - Warming Stripes",
    scale_millions=True,
    color_scheme="RdBu",  # Red for outflows, blue for inflows
    height=80  # Compact height for stripe effect
)

Plot.plot(cash_flow_config)
```

## Working with Real Estate Cash Flows

```python
# Common pattern for development projects
def plot_construction_timeline(project):
    \"\"\"Plot construction costs over time by category.\"\"\"

    # Get construction cash flows
    construction_cf = project.construction_before_financing_cf

    # Reshape to long format
    long_df = reshape_to_long_format(
        construction_cf,
        column_names=["Category", "Subcategory", "Item"]
    )

    # Create time series bar chart
    config = create_time_series_bars(
        long_df,
        title=f"Construction Timeline: {project.name}",
        fill_column="Category",
        scale_millions=True
    )

    return Plot.plot(config)

def plot_cumulative_investment(project):
    \"\"\"Plot cumulative investment over time.\"\"\"

    # Get cumulative investment
    cumsum_cf = project.construction_before_financing_cf.cumsum()

    # Quick stacked area chart
    config = quick_stacked_bar_from_multiindex(
        cumsum_cf,
        title=f"Cumulative Investment: {project.name}"
    )

    return Plot.plot(config)
```
"""

from typing import Any, Dict, List, Optional

import pandas as pd
from pyobsplot import Plot


def reshape_to_long_format(
    df: pd.DataFrame,
    column_names: Optional[List[str]] = None,
    value_name: str = "Amount",
    date_column: str = "Date",
) -> pd.DataFrame:
    """
    Reshape a multi-index DataFrame to long format suitable for PyObsPlot.

    Converts wide-format DataFrames with multi-level column indices into
    long-format DataFrames with proper timestamp indices for visualization.

    Args:
        df: DataFrame with multi-level column index to reshape
        column_names: Custom column names for the reshaped data. If None,
                     will infer based on column index levels
        value_name: Name for the values column (default: "Amount")
        date_column: Name for the date column (default: "Date")

    Returns:
        Long-format DataFrame with timestamp index suitable for PyObsPlot

    Example:
        ```python
        # Multi-index DataFrame with (Category, Subcategory, Item) columns
        wide_df = pd.DataFrame(...)

        # Reshape to long format
        long_df = reshape_to_long_format(
            wide_df,
            column_names=["Category", "Subcategory", "Item"]
        )
        ```
    """
    if df.empty:
        raise ValueError("Cannot reshape empty DataFrame")

    # Determine number of column levels to stack
    if isinstance(df.columns, pd.MultiIndex):
        n_levels = len(df.columns.levels)
        stack_levels = list(range(n_levels))
    else:
        # Single-level columns, convert to list for consistent handling
        df_stacked = df.stack()
        df_long = df_stacked.reset_index()

        # Set default column names if not provided
        if column_names is None:
            column_names = [date_column, "Category", value_name]
        else:
            column_names = [date_column] + column_names + [value_name]

        df_long.columns = column_names[: len(df_long.columns)]

        # Convert date index to timestamp
        df_long[date_column] = pd.to_datetime(df_long[date_column])
        if hasattr(df_long[date_column].iloc[0], "to_timestamp"):
            df_long[date_column] = df_long[date_column].dt.to_timestamp()

        return df_long

    # Stack all levels of multi-index columns
    df_stacked = df.stack(level=stack_levels)
    df_long = df_stacked.reset_index()

    # Set column names based on structure
    if column_names is None:
        # Default naming based on number of levels
        base_names = [date_column]
        for i in range(n_levels):
            base_names.append(f"Level_{i}")
        base_names.append(value_name)
        column_names = base_names
    else:
        column_names = [date_column] + column_names + [value_name]

    # Ensure we have the right number of column names
    if len(column_names) != len(df_long.columns):
        raise ValueError(
            f"Number of column_names ({len(column_names)}) doesn't match "
            f"reshaped DataFrame columns ({len(df_long.columns)})"
        )

    df_long.columns = column_names

    # Convert date column to proper timestamp format
    df_long[date_column] = pd.to_datetime(df_long[date_column])
    if hasattr(df_long[date_column].iloc[0], "to_timestamp"):
        df_long[date_column] = df_long[date_column].dt.to_timestamp()

    # Remove rows with NaN values
    df_long = df_long.dropna(subset=[value_name])

    return df_long


def create_vertical_categorical_bar(
    df: pd.DataFrame,
    x_column: str = "Date",
    y_column: str = "Amount",
    fill_column: str = "Category",
    title: Optional[str] = None,
    y_label: Optional[str] = None,
    scale_millions: bool = False,
    show_grid: bool = True,
    show_legend: bool = True,
    **plot_options: Any,
) -> Dict[str, Any]:
    """
    Create a vertical stacked bar chart using PyObsPlot.

    This creates vertical bars (Plot.barY) extending upward along the Y-axis.
    For horizontal single stacked bars, use create_horizontal_stacked_bar() instead.

    Args:
        df: Long-format DataFrame with data to plot
        x_column: Column name for x-axis (default: "Date")
        y_column: Column name for y-axis values (default: "Amount")
        fill_column: Column name for fill/color grouping (default: "Category")
        title: Optional chart title
        y_label: Optional y-axis label
        scale_millions: If True, scale y-values to millions (default: False)
        show_grid: Whether to show grid lines (default: True)
        show_legend: Whether to show color legend (default: True)
        **plot_options: Additional plot configuration options

    Returns:
        Plot configuration dictionary ready for Plot.plot()

    Example:
        ```python
        # Create vertical stacked bar chart
        plot_config = create_single_stacked_bar(
            long_df,
            title="Construction Costs by Category",
            y_label="Cost ($M)",
            scale_millions=True
        )

        # Render the plot
        Plot.plot(plot_config)
        ```
    """
    if df.empty:
        raise ValueError("Cannot create plot from empty DataFrame")

    # Validate required columns exist
    required_cols = [x_column, y_column, fill_column]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Base plot configuration
    plot_config = {
        "marks": [
            Plot.barY(
                df, {"x": x_column, "y": y_column, "fill": fill_column, "tip": True}
            ),
            Plot.ruleY([0]),  # baseline at zero
        ]
    }

    # Add grid if requested
    if show_grid:
        plot_config["grid"] = True

    # Add legend if requested
    if show_legend:
        plot_config["color"] = {"legend": True}

    # Configure y-axis
    y_config = {}
    if scale_millions:
        # Transform to millions with proper formatting
        y_config["transform"] = "(d) => d / 1000000"
        if y_label is None:
            y_label = f"{y_column} ($M)"

    if y_label:
        y_config["label"] = y_label

    if y_config:
        plot_config["y"] = y_config

    # Add title if provided
    if title:
        plot_config["title"] = title

    # Merge any additional plot options
    plot_config.update(plot_options)

    return plot_config


def create_horizontal_categorical_bar(
    df: pd.DataFrame,
    category_column: str = "Category",
    value_column: str = "Amount",
    title: Optional[str] = None,
    show_percentages: bool = True,
    height: int = 100,
    show_labels: bool = False,
    margin_left: int = 10,
    margin_right: int = 10,
    **plot_options: Any,
) -> Dict[str, Any]:
    """
    Create a horizontal single stacked bar chart (like Observable Plot example).

    This creates a single horizontal bar showing proportions of different categories,
    similar to the Observable Plot single stacked bar example.

    Args:
        df: DataFrame with category and value data
        category_column: Column name for categories (default: "Category")
        value_column: Column name for values (default: "Amount")
        title: Optional chart title
        show_percentages: If True, show as percentages (default: True)
        height: Chart height in pixels (default: 100)
        show_labels: If True, show category labels on bars (default: False)
        margin_left: Left margin in pixels for axis labels (default: 10)
        margin_right: Right margin in pixels for axis labels (default: 10)
        **plot_options: Additional plot configuration options

    Returns:
        Plot configuration dictionary ready for Plot.plot()

    Example:
        ```python
        # Create horizontal proportional stacked bar
        category_data = pd.DataFrame({
            'Category': ['Hard Costs', 'Soft Costs', 'Land', 'Financing'],
            'Amount': [5000000, 1000000, 2000000, 500000]
        })

        plot_config = create_horizontal_categorical_bar(
            category_data,
            title="Development Cost Breakdown",
            show_percentages=True,
        )

        Plot.plot(plot_config)
        ```
    """
    if df.empty:
        raise ValueError("Cannot create plot from empty DataFrame")

    # Validate required columns exist
    required_cols = [category_column, value_column]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Transform data for percentage display if requested
    if show_percentages:
        # Create a copy to avoid modifying original data
        df_plot = df.copy()
        total = df_plot[value_column].sum()
        if total == 0:
            raise ValueError("Cannot create percentage chart: sum of values is zero")
        # Convert to decimal percentages (0.0 to 1.0)
        df_plot[value_column] = (df_plot[value_column] / total).round(4)
    else:
        df_plot = df

    # Base plot configuration for horizontal stacked bar
    plot_config = {
        "height": height,
        "marginLeft": margin_left,
        "marginRight": margin_right,
        "marks": [
            Plot.barX(
                df_plot,
                {
                    "x": value_column,
                    "fill": category_column,
                    "tip": True,
                    "inset": 0,  # no gap between bars
                },
            ),
            Plot.ruleX([0]),  # baseline
            Plot.ruleX([
                1 if show_percentages else df_plot[value_column].sum()
            ]),  # end line
        ],
    }

    # Configure x-axis for percentages if requested
    if show_percentages:
        plot_config["x"] = {"percent": True}

    # Add category labels if requested
    if show_labels:
        # Add text labels for categories
        text_mark = Plot.text(
            df_plot,
            {
                "x": value_column,
                "text": category_column,
                "fill": "white",
                "fontWeight": "bold",
                "textAnchor": "middle",
            },
        )
        plot_config["marks"].insert(-2, text_mark)  # Insert before rules

    # Add title if provided
    if title:
        plot_config["title"] = title

    # Add color legend
    plot_config["color"] = {"legend": True}

    # Merge additional options
    plot_config.update(plot_options)

    return plot_config


def create_cash_flow_time_series(
    df: pd.DataFrame,
    time_column: str = "Date",
    value_column: str = "Amount",
    facet_column: Optional[str] = None,
    title: Optional[str] = None,
    scale_millions: bool = False,
    height: int = 150,
    color_scheme: str = "RdBu",
    stripe_height: int = 40,
    margin_left: int = 15,
    margin_right: int = 15,
    color_clamp_percentiles: tuple = (0.02, 0.98),
    **plot_options: Any,
) -> Dict[str, Any]:
    """
    Create a simple cash flow time series chart like Observable Plot "warming stripes".

    Creates one bar (stripe) per time period, with color representing the cash flow value.
    Optionally use facets to show multiple cash flow categories as separate stripe rows.
    Similar to the warming stripes example at https://observablehq.com/@observablehq/plot-warming-stripes

    Args:
        df: DataFrame with time series cash flow data (one row per time period)
        time_column: Column name for time periods (default: "Date")
        value_column: Column name for cash flow values (default: "Amount")
        facet_column: Optional column name for faceting (creates separate stripes per category)
        title: Optional chart title
        scale_millions: If True, scale values to millions (default: False)
        height: Chart height in pixels (default: 150)
        color_scheme: Color scheme - "RdBu", "BuRd", "PiYG", etc. (default: "RdBu" = red for outflows, blue for inflows)
        stripe_height: Height per stripe when using facets (default: 40)
        margin_left: Left margin in pixels (default: 15)
        margin_right: Right margin in pixels (default: 15)
        color_clamp_percentiles: Tuple of (low, high) percentiles for color clamping (default: (0.02, 0.98))
        **plot_options: Additional plot configuration options

    Returns:
        Plot configuration dictionary ready for Plot.plot()

    Examples:
        ```python
        # Single cash flow stripe
        cash_flow_data = pd.DataFrame({
            'Date': pd.period_range('2024-01', periods=12, freq='M'),
            'Amount': [-1000000, -500000, 100000, 200000, 300000, 400000,
                      500000, 600000, 400000, 300000, 200000, -800000]
        })

        plot_config = create_cash_flow_time_series(
            cash_flow_data,
            title="Project Cash Flow Over Time",
            scale_millions=True,
            color_scheme="RdBu"
        )

        # Multiple cash flow stripes using facets
        multi_flow_data = pd.DataFrame({
            'Date': pd.period_range('2024-01', periods=12, freq='M').repeat(3),
            'Amount': [-1000000, -500000, 100000] * 12,  # Example data
            'Flow_Type': ['NOI', 'CapEx', 'UCF'] * 12
        })

        faceted_config = create_cash_flow_time_series(
            multi_flow_data,
            facet_column="Flow_Type",
            title="Multiple Cash Flow Components",
            scale_millions=True,
            stripe_height=30,
            color_clamp_percentiles=(0.05, 0.95)  # More aggressive clamping for better gradient
        )

        Plot.plot(plot_config)
        ```
    """
    if df.empty:
        raise ValueError("Cannot create plot from empty DataFrame")

    # Validate required columns exist
    required_cols = [time_column, value_column]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Create a copy and process the data
    df_plot = df.copy()

    # Convert period index to timestamp if needed and ensure proper datetime format for PyObsPlot
    if hasattr(df_plot[time_column].iloc[0], "to_timestamp"):
        df_plot[time_column] = df_plot[time_column].dt.to_timestamp()

    # Ensure datetime conversion (handle both Period and Timestamp)
    df_plot[time_column] = pd.to_datetime(df_plot[time_column], errors="coerce")

    # Convert to ISO string format for PyObsPlot (avoid datetime parsing warnings)
    df_plot[time_column] = df_plot[time_column].dt.strftime("%Y-%m-%d")

    # Scale to millions if requested
    if scale_millions:
        df_plot[value_column] /= 1_000_000
        y_label = f"{value_column} ($M)"
    else:
        y_label = value_column

    # Apply color clamping to improve gradient distribution for all charts
    # Calculate percentiles for color clamping to avoid extreme outliers dominating
    p_low, p_high = color_clamp_percentiles
    p_low_val = df_plot[value_column].quantile(p_low)
    p_high_val = df_plot[value_column].quantile(p_high)

    # Create a normalized column for better color distribution
    df_plot["_color_value"] = df_plot[value_column].clip(p_low_val, p_high_val)
    color_column = "_color_value"

    # Configure bar marks - TRUE warming stripes style (no y dimension!)
    if facet_column:
        # Multiple stripes using facets
        bar_config = {
            "x": time_column,
            # NO y dimension - bars span full height!
            "fill": color_column,  # Color by normalized cash flow value
            "fy": facet_column,  # Facet by category (separate rows)
            "tip": True,
            "inset": 0,  # No gaps between bars
        }
        # Calculate total height based on number of facets
        n_facets = (
            df_plot[facet_column].nunique() if facet_column in df_plot.columns else 1
        )
        total_height = stripe_height * n_facets + 50  # Add some padding
    else:
        # Single stripe - exactly like warming stripes example
        bar_config = {
            "x": time_column,
            # NO y dimension - bar spans full height!
            "fill": color_column,  # Color by cash flow value
            "tip": True,
            "inset": 0,  # No gaps between bars
        }
        total_height = height

    # Base plot configuration - exactly like the warming stripes example
    plot_config = {
        "height": total_height,
        "marginLeft": margin_left,
        "marginRight": margin_right,
        "color": {"scheme": color_scheme},  # Use Observable Plot's color schemes
        "marks": [
            Plot.barX(df_plot, bar_config)  # Use barX like warming stripes
        ],
    }

    # No reference lines for true warming stripes - just pure color bands

    # Configure axes for warming stripes
    plot_config["x"] = {"round": True, "grid": True}  # Time axis

    if facet_column:
        # For faceted stripes, clean labels
        plot_config["fy"] = {"label": None}  # Clean facet labels

    # No y-axis configuration needed - bars span full height

    # Add title if provided
    if title:
        plot_config["title"] = title

    # Merge additional options
    plot_config.update(plot_options)

    return plot_config


def create_time_series_bars(
    df: pd.DataFrame,
    x_column: str = "Date",
    y_column: str = "Amount",
    fill_column: str = "Category",
    title: Optional[str] = None,
    y_label: Optional[str] = None,
    scale_millions: bool = False,
    show_grid: bool = True,
    show_legend: bool = True,
    **plot_options: Any,
) -> Dict[str, Any]:
    """
    Create a time series bar chart with stacking using PyObsPlot.

    Args:
        df: Long-format DataFrame with time series data
        x_column: Column name for x-axis (time) (default: "Date")
        y_column: Column name for y-axis values (default: "Amount")
        fill_column: Column name for fill/color grouping (default: "Category")
        title: Optional chart title
        y_label: Optional y-axis label
        scale_millions: If True, scale y-values to millions (default: False)
        show_grid: Whether to show grid lines (default: True)
        show_legend: Whether to show color legend (default: True)
        **plot_options: Additional plot configuration options

    Returns:
        Plot configuration dictionary ready for Plot.plot()
    """
    if df.empty:
        raise ValueError("Cannot create plot from empty DataFrame")

    # Validate required columns exist
    required_cols = [x_column, y_column, fill_column]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Base plot configuration for time series
    plot_config = {
        "marginLeft": 60,
        "marks": [
            Plot.barY(
                df, {"x": x_column, "y": y_column, "fill": fill_column, "tip": True}
            ),
            Plot.ruleY([0]),
        ],
    }

    # Configure x-axis for time series
    plot_config["x"] = {"type": "time", "tickFormat": "%b %Y", "grid": show_grid}

    # Configure y-axis
    y_config = {}
    if scale_millions:
        y_config["transform"] = "(d) => d / 1000000"
        if y_label is None:
            y_label = f"{y_column} ($M)"

    if y_label:
        y_config["label"] = y_label

    if show_grid:
        y_config["grid"] = True

    if y_config:
        plot_config["y"] = y_config

    # Add legend if requested
    if show_legend:
        plot_config["color"] = {"legend": True}

    # Add title if provided
    if title:
        plot_config["title"] = title

    # Merge additional options
    plot_config.update(plot_options)

    return plot_config


def create_cumulative_area_chart(
    df: pd.DataFrame,
    x_column: str = "Date",
    y_column: str = "Amount",
    fill_column: str = "Category",
    title: Optional[str] = None,
    y_label: Optional[str] = None,
    scale_millions: bool = False,
    show_grid: bool = True,
    show_legend: bool = True,
    **plot_options: Any,
) -> Dict[str, Any]:
    """
    Create a cumulative area chart using PyObsPlot.

    Useful for showing cumulative cash flows, construction costs over time, etc.

    Args:
        df: Long-format DataFrame with data to plot
        x_column: Column name for x-axis (default: "Date")
        y_column: Column name for y-axis values (default: "Amount")
        fill_column: Column name for fill/color grouping (default: "Category")
        title: Optional chart title
        y_label: Optional y-axis label
        scale_millions: If True, scale y-values to millions (default: False)
        show_grid: Whether to show grid lines (default: True)
        show_legend: Whether to show color legend (default: True)
        **plot_options: Additional plot configuration options

    Returns:
        Plot configuration dictionary ready for Plot.plot()
    """
    if df.empty:
        raise ValueError("Cannot create plot from empty DataFrame")

    # Validate required columns exist
    required_cols = [x_column, y_column, fill_column]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Base plot configuration
    plot_config = {
        "marginLeft": 60,
        "marks": [
            Plot.areaY(
                df,
                {
                    "x": x_column,
                    "y": y_column,
                    "fill": fill_column,
                    "curve": "step-after",
                    "tip": True,
                },
            ),
            Plot.ruleY([0]),
        ],
    }

    # Configure x-axis for time series
    plot_config["x"] = {"type": "time", "grid": show_grid}

    # Configure y-axis
    y_config = {}
    if scale_millions:
        y_config["transform"] = "(d) => d / 1000000"
        if y_label is None:
            y_label = f"{y_column} ($M)"

    if y_label:
        y_config["label"] = y_label

    if show_grid:
        y_config["grid"] = True

    if y_config:
        plot_config["y"] = y_config

    # Add legend if requested
    if show_legend:
        plot_config["color"] = {"legend": True}

    # Add title if provided
    if title:
        plot_config["title"] = title

    # Merge additional options
    plot_config.update(plot_options)

    return plot_config


def quick_stacked_bar_from_multiindex(
    df: pd.DataFrame,
    title: Optional[str] = None,
    column_names: Optional[List[str]] = None,
    scale_millions: bool = True,
    **plot_options: Any,
) -> Dict[str, Any]:
    """
    Convenience function to create a stacked bar from multi-index DataFrame.

    Combines reshaping and plotting in a single function call for common use cases.

    Args:
        df: Multi-index DataFrame to reshape and plot
        title: Optional chart title
        column_names: Custom column names for reshaping
        scale_millions: If True, scale y-values to millions (default: True)
        **plot_options: Additional plot configuration options

    Returns:
        Plot configuration dictionary ready for Plot.plot()

    Example:
        ```python
        # Quick plot from multi-index construction costs DataFrame
        plot_config = quick_stacked_bar_from_multiindex(
            construction_costs_df,
            title="Construction Costs by Category",
            column_names=["Category", "Subcategory", "Item"]
        )

        Plot.plot(plot_config)
        ```
    """
    # Reshape the data
    long_df = reshape_to_long_format(df, column_names=column_names)

    # Use the primary category column for fill
    fill_col = long_df.columns[1] if len(long_df.columns) > 1 else "Category"

    # Create the plot
    return create_vertical_categorical_bar(
        long_df,
        title=title,
        fill_column=fill_col,
        scale_millions=scale_millions,
        **plot_options,
    )


# EXAMPLES using observable plot: https://observablehq.com/@observablehq/plot-gallery
# TODO: single stacked bar https://observablehq.com/@observablehq/plot-stacked-percentages
# TODO: gantt chart https://observablehq.com/@observablehq/build-your-own-gantt-chart
# TODO: cash flow waterfall chart
# TODO: time series bar chart
# TODO: sankey diagram for cost components https://observablehq.com/@ee2dev/making-a-treemap-and-sankey-diagram-with-observable-plot
# TODO: sankey diagram for revenue components https://observablehq.com/@ee2dev/making-a-treemap-and-sankey-diagram-with-observable-plot
# TODO: treemap chart for cost components https://observablehq.com/@ee2dev/making-a-treemap-and-sankey-diagram-with-observable-plot
# TODO: waffle chart or cell mark chart/choropleth for stacking plans / unit absorption

# NOTE: no pie charts! they are an antipattern. https://www.ataccama.com/blog/why-pie-charts-are-evil
