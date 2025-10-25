import marimo

__generated_with = "0.15.2"
app = marimo.App(width="medium", css_file="../marimo.css")


@app.cell
def __():
    """Import all required modules"""
    from datetime import date

    import marimo as mo
    import pandas as pd
    import plotly.express as px

    from performa.core.primitives import SweepMode
    from performa.patterns import ResidentialDevelopmentPattern

    return (
        ResidentialDevelopmentPattern,
        SweepMode,
        date,
        mo,
        pd,
        px,
    )


@app.cell
def __(mo):
    """Display title and introduction"""
    mo.md(
        """
        # 🏙️ Patterns: Shortcut to Financial Models
        
        This notebook demonstrates the "magic" of Performa's Pattern architecture:
        **a few parameters transform into a complete real estate financial model**.
        
        Configure the inputs below, and watch a single Pattern class generate:
        - Multi-unit property with lease lifecycle
        - Construction and permanent financing
        - Partnership waterfall with promotes
        - Complete cash flow model and ledger
        - Performance metrics and analysis
        
        ---
        """
    )


@app.cell
def __(mo):
    """Create pattern configuration form using mo.ui.dictionary"""

    pattern_params = mo.ui.dictionary({
        "project_name": mo.ui.text(
            value="Garden View Apartments",
            label="Project Name",
        ),
        "land_cost": mo.ui.number(
            start=1_000_000,
            stop=10_000_000,
            step=250_000,
            value=3_500_000,
            label="💰 Land Cost ($)",
        ),
        "total_units": mo.ui.number(
            start=50,
            stop=300,
            step=10,
            value=120,
            label="🏠 Total Units",
        ),
        "construction_cost_per_unit": mo.ui.number(
            start=120_000,
            stop=250_000,
            step=5_000,
            value=160_000,
            label="🔨 Construction Cost per Unit ($)",
        ),
        "construction_duration_months": mo.ui.slider(
            start=12,
            stop=30,
            step=3,
            value=18,
            label="⏱️ Construction Duration (months)",
            show_value=True,
        ),
        "hold_period_years": mo.ui.slider(
            start=5,
            stop=10,
            step=1,
            value=7,
            label="📅 Hold Period (years)",
            show_value=True,
        ),
        "exit_cap_rate": mo.ui.slider(
            start=0.04,
            stop=0.08,
            step=0.0025,
            value=0.055,
            label="🎯 Exit Cap Rate",
            show_value=True,
        ),
        # FINANCING PARAMETERS
        "construction_interest_rate": mo.ui.slider(
            start=0.050,
            stop=0.100,
            step=0.0025,
            value=0.065,
            label="🏗️ Construction Interest Rate",
            show_value=True,
        ),
        "construction_ltc_ratio": mo.ui.slider(
            start=0.50,
            stop=0.85,
            step=0.05,
            value=0.70,
            label="📊 Construction LTC Ratio",
            show_value=True,
        ),
        "permanent_interest_rate": mo.ui.slider(
            start=0.040,
            stop=0.085,
            step=0.0025,
            value=0.055,
            label="🏦 Permanent Interest Rate",
            show_value=True,
        ),
        "permanent_ltv_ratio": mo.ui.slider(
            start=0.50,
            stop=0.80,
            step=0.05,
            value=0.70,
            label="📈 Permanent LTV Ratio",
            show_value=True,
        ),
        "permanent_loan_term_years": mo.ui.slider(
            start=7,
            stop=12,
            step=1,
            value=10,
            label="⏰ Permanent Loan Term (years)",
            show_value=True,
        ),
        "permanent_amortization_years": mo.ui.slider(
            start=20,
            stop=30,
            step=5,
            value=25,
            label="📅 Amortization Period (years)",
            show_value=True,
        ),
        "construction_sweep_mode": mo.ui.dropdown(
            options=["TRAP", "PREPAY", "None"],
            value="TRAP",
            label="💰 Cash Sweep Mode (construction loan)",
        ),
        # LEASING PARAMETERS
        "absorption_pace_units_per_month": mo.ui.slider(
            start=4,
            stop=15,
            step=1,
            value=8,
            label="🚀 Absorption Pace (units/month)",
            show_value=True,
        ),
        "leasing_start_months": mo.ui.slider(
            start=12,
            stop=24,
            step=3,
            value=15,
            label="📍 Leasing Start (months from acquisition)",
            show_value=True,
        ),
    })

    return (pattern_params,)


@app.cell
def __(pattern_params, mo):
    """Display the parameter configuration form"""
    mo.md("## 📋 Pattern Configuration")


@app.cell
def __(pattern_params):
    """Display the form"""
    pattern_params


@app.cell
def __(mo):
    """Section divider"""
    mo.md(
        """
        ---
        
        ## ✨ The Magic: Pattern → Analysis
        
        Watch as a single class instantiation unfurls into a complete financial model:
        """
    )


@app.cell
def __(pattern_params, date, ResidentialDevelopmentPattern, SweepMode):
    """
    THE MAGIC HAPPENS HERE: Pattern unfurls into complete analysis

    This single cell transforms user parameters into a full deal model with:
    - Property with 120 units (mixed 1BR/2BR)
    - Construction-to-permanent financing
    - GP/LP partnership with waterfall
    - Complete ledger and cash flows
    """

    # Extract parameters from form
    params = pattern_params.value

    # Convert sweep mode string to enum
    sweep_mode_str = params.get("construction_sweep_mode", "TRAP")
    if sweep_mode_str == "None":
        sweep_mode = None
    elif sweep_mode_str == "TRAP":
        sweep_mode = SweepMode.TRAP
    elif sweep_mode_str == "PREPAY":
        sweep_mode = SweepMode.PREPAY
    else:
        sweep_mode = SweepMode.TRAP  # Default fallback

    # Define unit mix (could be parameterized further)
    unit_mix = [
        {"unit_type": "1BR", "count": 72, "avg_sf": 750, "target_rent": 2100},
        {"unit_type": "2BR", "count": 48, "avg_sf": 1050, "target_rent": 2800},
    ]

    # Create pattern with user-configured parameters
    pattern = ResidentialDevelopmentPattern(
        # Core project parameters
        project_name=params.get("project_name", "Garden View Apartments"),
        acquisition_date=date(2024, 1, 1),
        land_cost=params.get("land_cost", 3_500_000),
        total_units=params.get("total_units", 120),
        construction_cost_per_unit=params.get("construction_cost_per_unit", 160_000),
        construction_duration_months=params.get("construction_duration_months", 18),
        hold_period_years=params.get("hold_period_years", 7),
        exit_cap_rate=params.get("exit_cap_rate", 0.055),
        # Unit mix configuration
        unit_mix=unit_mix,
        # Leasing strategy (user-configurable)
        leasing_start_months=params.get("leasing_start_months", 15),
        absorption_pace_units_per_month=params.get(
            "absorption_pace_units_per_month", 8
        ),
        # Financing (user-configurable for stress testing)
        construction_interest_rate=params.get("construction_interest_rate", 0.065),
        construction_ltc_ratio=params.get("construction_ltc_ratio", 0.70),
        construction_sweep_mode=sweep_mode,
        permanent_ltv_ratio=params.get("permanent_ltv_ratio", 0.70),
        permanent_interest_rate=params.get("permanent_interest_rate", 0.055),
        permanent_loan_term_years=params.get("permanent_loan_term_years", 10),
        permanent_amortization_years=params.get("permanent_amortization_years", 25),
        # Partnership structure (smart defaults)
        distribution_method="waterfall",
        gp_share=0.10,
        lp_share=0.90,
        preferred_return=0.08,
        promote_tier_1=0.20,
        # Exit strategy
        exit_costs_rate=0.025,
    )

    # THE UNFURLING: Pattern → Complete Analysis
    results = pattern.analyze()

    return pattern, results, unit_mix, params


@app.cell
def __(mo):
    """Success message"""
    mo.md(
        """
        ✅ **Pattern Successfully Unfurled!**
        
        The `ResidentialDevelopmentPattern` has generated a complete deal model with:
        - Residential property with unit-level lease modeling
        - Construction and permanent debt facilities
        - Partnership waterfall with GP promote
        - Multi-year cash flow projections
        - Comprehensive transactional ledger
        
        Let's explore the results below...
        
        ---
        """
    )


@app.cell
def __(mo):
    """Performance metrics section header"""
    mo.md("## 📊 Top-Level Performance Metrics")


@app.cell
def __(results, mo):
    """Display top-level performance metrics from actual results"""

    # Extract metrics from actual DealResults
    levered_irr = results.levered_irr
    unlevered_irr = results.unlevered_irr
    equity_multiple = results.equity_multiple
    net_profit = results.net_profit

    # Format for display
    levered_irr_str = f"{levered_irr:.2%}" if levered_irr is not None else "N/A"
    unlevered_irr_str = f"{unlevered_irr:.2%}" if unlevered_irr is not None else "N/A"
    equity_multiple_str = (
        f"{equity_multiple:.2f}x" if equity_multiple is not None else "N/A"
    )
    net_profit_str = f"${net_profit:,.0f}" if net_profit is not None else "N/A"

    # Create metric cards
    mo.hstack(
        [
            mo.stat(value=levered_irr_str, label="Levered IRR"),
            mo.stat(value=unlevered_irr_str, label="Unlevered IRR"),
            mo.stat(value=equity_multiple_str, label="Equity Multiple"),
            mo.stat(value=net_profit_str, label="Net Profit"),
        ],
        widths="equal",
    )


@app.cell
def __(mo):
    """Ledger section header"""
    mo.md(
        """
        ---
        
        ## 📖 The Ledger: Glass Box Transparency
        
        Every transaction in the model is recorded in the ledger. Here's the annual view:
        """
    )


@app.cell
def __(results, mo, pd):
    """Display ledger pivot table using reporting interface"""

    # Generate annual pivot table from the ledger (no built-in formatting)
    pivot_table = results.reporting.pivot_table(
        frequency="A",  # Annual frequency
        include_subtotals=True,
        include_totals_column=True,
        currency_format=False,  # Disable built-in formatting
    )

    # Reorder rows chronologically for development deal flow
    def chronological_sort_key(line_item):
        """Sort line items in chronological deal order."""
        # Priority order for development deals
        if "Acquisition" in line_item or "Land" in line_item:
            return (0, line_item)  # First: acquisition
        elif "Capital" in line_item or "Construction" in line_item:
            return (1, line_item)  # Second: construction
        elif "Financing" in line_item and "Draw" in line_item:
            return (2, line_item)  # Third: debt draws
        elif "Revenue" in line_item:
            return (3, line_item)  # Fourth: operations revenue
        elif "Expense" in line_item:
            return (4, line_item)  # Fifth: operations expenses
        elif "Financing" in line_item and (
            "Payoff" in line_item or "Payment" in line_item
        ):
            return (5, line_item)  # Sixth: debt service/payoff
        elif "Disposition" in line_item or "Sale" in line_item or "Exit" in line_item:
            return (6, line_item)  # Seventh: exit/sale
        else:
            return (7, line_item)  # Other items last

    sorted_index = sorted(pivot_table.index, key=chronological_sort_key)
    pivot_table = pivot_table.reindex(sorted_index)

    # Clean up row labels: remove category prefix from subcategories
    # "Capital → Closing Costs" becomes "→ Closing Costs"
    cleaned_index = []
    for label in pivot_table.index:
        if " → " in label:
            # Keep only the arrow and subcategory name
            subcategory = label.split(" → ", 1)[1]
            cleaned_index.append(f"→ {subcategory}")
        else:
            # Keep category-level labels as-is
            cleaned_index.append(label)
    pivot_table.index = cleaned_index

    # Format as full dollars (no abbreviations, no dollar signs, comma separators)
    formatted_pivot = pivot_table.copy()
    for col in formatted_pivot.columns:
        formatted_pivot[col] = formatted_pivot[col].apply(
            lambda x: f"{x:,.0f}" if not pd.isna(x) else "0"
        )

    # Identify subtotal rows (rows without arrow)
    def highlight_subtotals(row):
        """Apply gray background to subtotal rows."""
        if not row.name.startswith("→"):  # Subtotal rows don't start with arrow
            return ["background-color: #f0f0f0; font-weight: bold"] * len(row)
        return [""] * len(row)

    # Apply styling: smaller text, right-aligned numbers, gray subtotals
    styled_html = (
        formatted_pivot.style.apply(highlight_subtotals, axis=1)
        .set_properties(**{
            "text-align": "right",
            "font-size": "11px",
            "padding": "4px 8px",
        })
        .set_table_styles([
            {
                "selector": "th",
                "props": [
                    ("text-align", "left"),
                    ("font-size", "11px"),
                    ("padding", "4px 8px"),
                    ("background-color", "#e0e0e0"),
                    ("font-weight", "bold"),
                    ("cursor", "cell"),  # Excel-style cursor
                ],
            },
            {
                "selector": "th:first-child",
                "props": [
                    ("min-width", "167px"),  # 33% less than 250px
                    ("white-space", "nowrap"),  # Prevent text wrapping
                ],
            },
            {
                "selector": "td",
                "props": [
                    ("text-align", "right"),
                    ("font-size", "11px"),
                    ("padding", "4px 8px"),
                    ("cursor", "cell"),  # Excel-style cursor
                    ("border", "1px solid transparent"),  # For hover effect
                ],
            },
            {
                "selector": "td:first-child",
                "props": [
                    ("text-align", "left"),  # Left-align row labels
                    ("min-width", "167px"),  # 33% less than 250px
                    ("white-space", "nowrap"),  # Prevent text wrapping
                ],
            },
            {
                "selector": "td:hover",
                "props": [
                    ("outline", "2px solid #ff69b4"),  # Pink outline on cell hover
                    ("outline-offset", "-1px"),  # Keep outline inside cell
                ],
            },
            {
                "selector": "table",
                "props": [("border-collapse", "collapse"), ("width", "100%")],
            },
            {"selector": "tr:hover", "props": [("background-color", "#f8f8f8")]},
        ])
        .to_html()
    )

    # Display using marimo HTML
    mo.Html(f"""
    <div style="max-height: 600px; overflow-y: auto;">
        <h3>Annual Cash Flow Ledger (Category + Subcategory)</h3>
        {styled_html}
    </div>
    """)


@app.cell
def __(mo):
    """Deal summary section header"""
    mo.md(
        """
        ---
        
        ## 💼 Deal Summary & Metrics
        
        Comprehensive deal-level metrics and analysis:
        """
    )


@app.cell
def __(results, mo, pd):
    """Display deal metrics as a formatted table"""

    # Get deal metrics dictionary
    metrics = results.deal_metrics

    # Create a formatted DataFrame
    metrics_df = pd.DataFrame([
        {
            "Metric": "Levered IRR",
            "Value": f"{metrics['levered_irr']:.2%}"
            if metrics["levered_irr"] is not None
            else "N/A",
        },
        {
            "Metric": "Unlevered IRR",
            "Value": f"{metrics['unlevered_irr']:.2%}"
            if metrics["unlevered_irr"] is not None
            else "N/A",
        },
        {
            "Metric": "Equity Multiple",
            "Value": f"{metrics['equity_multiple']:.2f}x"
            if metrics["equity_multiple"] is not None
            else "N/A",
        },
        {
            "Metric": "Unlevered Return on Cost",
            "Value": f"{metrics['unlevered_return_on_cost']:.2%}"
            if metrics["unlevered_return_on_cost"] is not None
            else "N/A",
        },
        {
            "Metric": "Net Profit",
            "Value": f"${metrics['net_profit']:,.0f}"
            if metrics["net_profit"] is not None
            else "N/A",
        },
        {"Metric": "Total Investment", "Value": f"${metrics['total_investment']:,.0f}"},
        {
            "Metric": "Total Distributions",
            "Value": f"${metrics['total_distributions']:,.0f}",
        },
        {
            "Metric": "Stabilized DSCR",
            "Value": f"{results.stabilized_dscr:.2f}x"
            if results.stabilized_dscr is not None
            else "N/A",
        },
        {
            "Metric": "Min Operating DSCR",
            "Value": f"{results.minimum_operating_dscr:.2f}x"
            if results.minimum_operating_dscr is not None
            else "N/A",
        },
        {
            "Metric": "Covenant Compliance",
            "Value": f"{results.covenant_compliance_rate:.1f}%"
            if results.covenant_compliance_rate is not None
            else "N/A",
        },
    ])

    mo.ui.table(
        metrics_df,
        selection=None,
        label="Key Performance Indicators",
    )


@app.cell
def __(mo):
    """Cash flow visualization section"""
    mo.md(
        """
        ---
        
        ## 📈 Cash Flow Visualization
        
        Annual equity cash flows over the hold period:
        """
    )


@app.cell
def __(results, px, mo, pd):
    """Visualize annual equity cash flows"""

    # Get annual equity cash flows from ledger
    equity_flows = results.levered_cash_flow

    # Convert PeriodIndex to DatetimeIndex and resample to annual frequency
    equity_flows_dt = equity_flows.to_timestamp()
    annual_flows = equity_flows_dt.resample("YE").sum()

    # Create DataFrame for plotly
    flow_df = pd.DataFrame({
        "Year": annual_flows.index.year,
        "Cash Flow": annual_flows.values,
        "Type": [
            "Investment" if x < 0 else "Distribution" for x in annual_flows.values
        ],
    })

    # Create bar chart
    fig = px.bar(
        flow_df,
        x="Year",
        y="Cash Flow",
        color="Type",
        title="Annual Equity Cash Flows",
        labels={"Cash Flow": "Cash Flow ($)", "Year": "Year"},
        color_discrete_map={"Investment": "#e74c3c", "Distribution": "#2ecc71"},
    )

    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="Cash Flow ($)",
        hovermode="x unified",
        showlegend=True,
    )

    mo.ui.plotly(fig)


@app.cell
def __(mo):
    """Partnership analysis section"""
    mo.md(
        """
        ---
        
        ## 🤝 Partnership Distribution Analysis
        
        How profits flow through the GP/LP waterfall:
        """
    )


@app.cell
def __(results, mo, pd):
    """Display partner distribution metrics"""

    # Get partner data from results.partners (PartnerMetrics objects)
    partner_data = []

    for partner_id, partner_info in results.partners.items():
        # Calculate investment and distributions from cash flow
        cf = partner_info.cash_flow
        total_investment = abs(cf[cf < 0].sum()) if not cf.empty else 0.0
        total_distributions = cf[cf > 0].sum() if not cf.empty else 0.0

        partner_data.append({
            "Partner": partner_info.partner_name or partner_id,
            "Type": partner_info.entity_type or "Unknown",
            "Ownership %": f"{partner_info.ownership_share:.1%}"
            if partner_info.ownership_share
            else "N/A",
            "Investment": f"${total_investment:,.0f}",
            "Distributions": f"${total_distributions:,.0f}",
            "Net Profit": f"${partner_info.net_profit:,.0f}",
            "IRR": f"{partner_info.irr:.2%}" if partner_info.irr is not None else "N/A",
            "Equity Multiple": f"{partner_info.equity_multiple:.2f}x"
            if partner_info.equity_multiple is not None
            else "N/A",
        })

    # Add aggregate row from deal_metrics
    deal_metrics = results.deal_metrics
    partner_data.append({
        "Partner": "TOTAL",
        "Type": "ALL",
        "Ownership %": "100.0%",
        "Investment": f"${deal_metrics['total_investment']:,.0f}",
        "Distributions": f"${deal_metrics['total_distributions']:,.0f}",
        "Net Profit": f"${deal_metrics['net_profit']:,.0f}",
        "IRR": f"{deal_metrics['levered_irr']:.2%}"
        if deal_metrics["levered_irr"] is not None
        else "N/A",
        "Equity Multiple": f"{deal_metrics['equity_multiple']:.2f}x"
        if deal_metrics["equity_multiple"] is not None
        else "N/A",
    })

    partner_df = pd.DataFrame(partner_data)

    mo.ui.table(
        partner_df,
        selection=None,
        label="Partner-Level Returns",
    )


@app.cell
def __(mo):
    """Educational footer"""
    mo.md(
        """
        ---
        
        ### 🎓 What Just Happened?
        
        **The Pattern Architecture at Work:**
        
        You configured just 7 parameters at the top of this notebook. From those inputs, 
        the `ResidentialDevelopmentPattern` automatically generated:
        
        1. **Property Model**: 120-unit multifamily with detailed unit mix (1BR/2BR)
        2. **Leasing Strategy**: Unit-by-unit lease execution with absorption modeling
        3. **Construction Financing**: Interest-only debt during construction
        4. **Permanent Financing**: Long-term amortizing debt after stabilization
        5. **Partnership Structure**: GP/LP waterfall with preferred return and promote
        6. **Complete Ledger**: Every transaction categorized and timestamped
        7. **Performance Metrics**: IRR, equity multiple, DSCR, and more
        
        **This is the power of the Pattern abstraction**: complex institutional-grade 
        financial models assembled from simple, business-focused parameters.
        
        **Try This**: Go back to the top and change the hold period or exit cap rate. 
        Watch all metrics update instantly across the entire model.
        
        ---
        
        *Powered by the **Performa** open-source financial modeling framework*
        """
    )


if __name__ == "__main__":
    app.run()
