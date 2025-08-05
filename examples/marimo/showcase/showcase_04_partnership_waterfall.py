import marimo

__generated_with = "0.10.6"
app = marimo.App(width="medium", css_file="../marimo.css")


@app.cell
def __():
    """Import all required modules"""
    import marimo as mo
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import numpy as np
    from datetime import date, datetime
    from typing import Dict, List, Any
    
    from performa.deal.entities import Partner
    from performa.deal.partnership import PartnershipStructure, WaterfallTier, WaterfallPromote, CarryPromote
    from performa.deal.analysis.partnership import DistributionCalculator
    from performa.core.primitives import Timeline
    
    return (
        CarryPromote, DistributionCalculator, Partner, PartnershipStructure, 
        Timeline, WaterfallPromote, WaterfallTier, date, datetime, go, mo, np, pd, px, 
        make_subplots, Dict, List, Any
    )


@app.cell  
def __(mo):
    """Display title and introduction"""
    mo.md(
        r"""
        # 🌊 Partnership Waterfall Builder
        
        **Explore Real Estate Equity Waterfalls & IRR-Based Promotes**
        
        Understanding how returns are distributed among partners is crucial in real estate finance. This demo showcases Performa's sophisticated waterfall engine that handles:
        
        - **Partnership Structures**: General Partners (GP) and Limited Partners (LP) with ownership percentages
        - **Distribution Methods**: Simple pro-rata vs complex IRR-based waterfall structures  
        - **Promote Mechanics**: Preferred returns, catch-up provisions, and graduated promote rates
        - **Performance Metrics**: IRR, equity multiples, and cash-on-cash returns for each partner
        
        Use the controls below to configure different partnership structures and see how they affect distribution outcomes.

        ---
        
        """
    )


# @app.cell
# def __(mo):
#     """Partnership configuration UI"""
#     mo.md("## 👥 Partnership Configuration")
#     return


@app.cell
def __(mo):
    """Partner setup controls"""
    # GP Configuration
    gp_name = mo.ui.text(value="Sponsor", label="GP Name")
    gp_share = mo.ui.slider(0.05, 0.50, 0.01, value=0.20, label="GP Ownership %")
    
    # LP Configuration  
    lp_name = mo.ui.text(value="Investor", label="LP Name")
    
    # Distribution method
    distribution_method = mo.ui.dropdown(
        ["Pari Passu (Pro-Rata)", "Waterfall (IRR-Based)"],
        value="Waterfall (IRR-Based)",
        label="Distribution Method"
    )
    
    return distribution_method, gp_name, gp_share, lp_name


@app.cell
def __(mo, distribution_method):
    """Waterfall structure configuration"""
    
    # Always create waterfall controls, conditionally display
    pref_return = mo.ui.slider(0.04, 0.12, 0.005, value=0.08, label="Preferred Return (8.0%)")
    
    # First tier hurdle and promote
    tier1_hurdle = mo.ui.slider(0.08, 0.20, 0.005, value=0.12, label="Tier 1 IRR Hurdle (12.0%)") 
    tier1_promote = mo.ui.slider(0.0, 0.5, 0.05, value=0.20, label="Tier 1 GP Promote (20%)")
    
    # Second tier hurdle and promote
    tier2_hurdle = mo.ui.slider(0.12, 0.25, 0.005, value=0.18, label="Tier 2 IRR Hurdle (18.0%)")
    tier2_promote = mo.ui.slider(0.20, 0.60, 0.05, value=0.35, label="Tier 2 GP Promote (35%)")
    
    # Final promote above all tiers
    final_promote = mo.ui.slider(0.30, 0.70, 0.05, value=0.50, label="Final GP Promote (50%)")
    
    return (
        final_promote, pref_return, tier1_hurdle, tier1_promote, 
        tier2_hurdle, tier2_promote
    )


@app.cell
def __(mo):
    """Cash flow scenario controls"""
    # Scenario selection
    scenario_type = mo.ui.dropdown([
        "Strong Performance (~20% IRR)",
        "Good Performance (~14% IRR)", 
        "Modest Performance (~10% IRR)",
        "Underperformance (~6% IRR)",
        "Custom Pattern"
    ], value="Good Performance (~14% IRR)", label="Performance Scenario")
    
    # Timeline configuration  
    timeline_years = mo.ui.slider(3, 10, 1, value=7, label="Investment Period (Years)")
    
    return scenario_type, timeline_years


@app.cell
def __(
    scenario_type, timeline_years, datetime, Timeline, pd
):
    """Generate cash flow scenarios"""
    
    # Create timeline using proper API
    years = timeline_years.value
    timeline = Timeline(
        start_date=datetime(2024, 1, 1),
        duration_months=years * 12  # Convert years to months
    )
    
    # Fixed investment amount to focus on structure, not size
    investment = 10_000_000  # $10M
    
    # Generate realistic cash flows based on typical real estate IRRs
    if "Strong Performance" in scenario_type.value:
        # Strong real estate performance: ~18-22% IRR
        # For 7 years: ~3.5x equity multiple
        total_return = investment * (1.20 ** years)  # 20% IRR compound
        
    elif "Good Performance" in scenario_type.value:
        # Good real estate performance: ~12-16% IRR
        # For 7 years: ~2.5x equity multiple  
        total_return = investment * (1.14 ** years)  # 14% IRR compound
        
    elif "Modest Performance" in scenario_type.value:
        # Modest real estate performance: ~8-12% IRR
        # For 7 years: ~1.8x equity multiple
        total_return = investment * (1.10 ** years)  # 10% IRR compound
        
    elif "Underperformance" in scenario_type.value:
        # Below expectations: ~5-7% IRR
        # For 7 years: ~1.5x equity multiple
        total_return = investment * (1.06 ** years)  # 6% IRR compound
        
    else:  # Default
        total_return = investment * (1.12 ** years)  # 12% IRR compound
    
    # Create monthly cash flow series: investment at start, return at end
    total_months = years * 12
    cash_flows = []
    for month_idx in range(total_months):
        if month_idx == 0:
            cash_flows.append(-investment)  # Initial investment
        elif month_idx == total_months - 1:
            cash_flows.append(total_return)  # Final return
        else:
            cash_flows.append(0)  # Hold periods
    
    cash_flow_series = pd.Series(cash_flows, index=timeline.period_index)
    
    return timeline, cash_flow_series, investment, years


@app.cell
def __(
    gp_name, gp_share, lp_name, distribution_method, 
    pref_return, tier1_hurdle, tier1_promote, tier2_hurdle, tier2_promote, final_promote,
    Partner, PartnershipStructure, WaterfallTier, WaterfallPromote
):
    """Create partnership structure"""
    
    # Create partners
    gp_partner = Partner(name=gp_name.value, kind="GP", share=gp_share.value)
    lp_partner = Partner(name=lp_name.value, kind="LP", share=1 - gp_share.value)
    partners = [gp_partner, lp_partner]
    
    # Determine distribution method
    method = "waterfall" if "Waterfall" in distribution_method.value else "pari_passu"
    
    # Create promote structure if waterfall method
    promote = None
    if method == "waterfall":
        tiers = [
            WaterfallTier(tier_hurdle_rate=tier1_hurdle.value, promote_rate=tier1_promote.value),
            WaterfallTier(tier_hurdle_rate=tier2_hurdle.value, promote_rate=tier2_promote.value)
        ]
        promote = WaterfallPromote(
            pref_hurdle_rate=pref_return.value,
            tiers=tiers,
            final_promote_rate=final_promote.value
        )
    
    # Create partnership structure
    partnership = PartnershipStructure(
        partners=partners,
        distribution_method=method,
        promote=promote
    )
    
    return partnership, gp_partner, lp_partner, method, promote


@app.cell
def __(partnership, cash_flow_series, timeline, DistributionCalculator):
    """Calculate waterfall distributions"""
    
    # Create distribution calculator
    calculator = DistributionCalculator(partnership)
    
    # Calculate distributions
    results = calculator.calculate_distributions(cash_flow_series, timeline)
    
    return calculator, results


@app.cell
def __(results, mo, pd, px):
    """Display partnership summary"""
    
    # Extract key metrics
    dist_method = results["distribution_method"]
    total_metrics = results["total_metrics"]
    partnership_summary = results["partnership_summary"]
    
    # Format display
    total_invest = total_metrics["total_investment"]
    total_distributions = total_metrics["total_distributions"]
    net_profit = total_distributions - abs(total_invest)
    equity_multiple = total_metrics["equity_multiple"]
    irr = total_metrics.get("irr")
    
    # Partnership structure details
    gp_count = partnership_summary["gp_count"]
    lp_count = partnership_summary["lp_count"]
    gp_pct = partnership_summary["gp_total_share"]
    lp_share = partnership_summary["lp_total_share"]
    
    irr_display = f"{irr:.1%}" if irr else "N/A"
    
    # Left column: Partnership structure
    structure_md = f"""
    ## 🏛️ Partnership Structure
    
    **Partners:** {gp_count} GP + {lp_count} LP  
    **Distribution Method:** {dist_method.replace('_', ' ').title()}  
    **Ownership Split:**  
    GP Share: **{gp_pct:.0%}**
    LP Share: **{lp_share:.0%}**
    """
    
    # Right column: Performance metrics
    performance_md = f"""
    ## 📈 Overall Performance
    
    **Total Investment:** ${abs(total_invest):,.0f}  
    **Total Distributions:** ${total_distributions:,.0f}  
    **Net Profit:** ${net_profit:,.0f}  
    **Equity Multiple:** **{equity_multiple:.2f}x**  
    **IRR:** **{irr_display}**
    """
    
    # Create ownership pie chart
    ownership_data = pd.DataFrame({
        'Partner Type': ['GP', 'LP'],
        'Ownership %': [gp_pct * 100, lp_share * 100]
    })
    
    pie_fig = px.pie(
        ownership_data,
        values='Ownership %',
        names='Partner Type',
        color_discrete_map={
            'GP': '#dc2626',  # Red for GP
            'LP': '#16a34a'   # Green for LP
        },
        height=225,  # Much bigger pie chart
        width=225,
    )
    pie_fig.update_layout(margin = dict(t=5, l=5, r=5, b=5))
    
    # Configure pie chart - no title, no legend
    pie_fig.layout.showlegend = False
    # Set text properties directly to avoid update_traces
    for trace in pie_fig.data:
        trace.textposition = 'inside'
        trace.textinfo = 'percent+label'
    
    # Three-column layout: Structure | Pie Chart | Performance
    mo.hstack([
        mo.vstack([
            mo.md(structure_md)
        ]),
        mo.vstack([
            mo.md("## 📊 Ownership"),
            pie_fig
        ]),
        mo.vstack([
            mo.md(performance_md)
        ])
    ], widths="equal", gap=2)
    return (
        equity_multiple, gp_count, irr, lp_count, lp_share, 
        net_profit, partnership_summary, total_distributions, 
        total_metrics
    )


@app.cell
def __(results, pd):
    """Create partner performance data only (chart created in main layout)"""
    
    # Extract partner metrics
    partner_dist_results = results["partner_distributions"]
    
    # Create partner performance data
    chart_data = []
    for pname, pmetrics in partner_dist_results.items():
        chart_data.append({
            "Partner": pname,
            "Partner Type": pmetrics["partner_info"].kind,
            "Ownership %": pmetrics["ownership_percentage"] * 100,
            "Investment": abs(pmetrics["total_investment"]),
            "Distributions": pmetrics["total_distributions"],
            "Net Profit": pmetrics["net_profit"], 
            "Equity Multiple": pmetrics["equity_multiple"],
            "IRR": pmetrics["irr"] if pmetrics["irr"] else 0
        })
    
    partner_df = pd.DataFrame(chart_data)
    return partner_df





@app.cell
def __(
    partner_df, mo, results, px, pd, timeline, years,
    gp_name, gp_share, lp_name, distribution_method,
    pref_return, tier1_hurdle, tier1_promote, tier2_hurdle, tier2_promote, final_promote,
    scenario_type, timeline_years
):
    """Main layout: Controls on left, charts on right"""
    
    # Recreate partner performance chart
    fig = px.bar(
        partner_df, 
        x="Partner", 
        y=["Investment", "Distributions"],
        # title="Investment vs Distributions by Partner",
        color_discrete_map={
            "Investment": "#ff7f7f",  # Light red for investment  
            "Distributions": "#7fbf7f"  # Light green for distributions
        },
        text_auto='.2s',
        labels={"value": "Amount ($)"},
        height=500  # Taller for better bar visibility
    )
    fig.layout.yaxis.range = [0, 35_000_000]  # Fixed range so bars move instead of axis scaling
    fig.layout.legend = dict(orientation="h", yanchor="bottom", y=0.95, xanchor="center", x=0.5)  # Legend at top under title
    # fig.layout.title.x = 0.5  # Center the title

    # Recreate timeline chart
    partner_dist = results["partner_distributions"] 
    start_year = timeline.period_index[0].year
    all_years = list(range(start_year, start_year + years))
    timeline_data = []
    
    for partner_name, timeline_metrics in partner_dist.items():
        partner_cash_flows = timeline_metrics["cash_flows"]
        partner_type = timeline_metrics["partner_info"].kind
        ownership_pct = timeline_metrics["ownership_percentage"]
        partner_annual = partner_cash_flows.groupby(partner_cash_flows.index.year).sum()
        
        for year in all_years:
            amount = partner_annual.get(year, 0)  # Get amount or 0 if no flow
            timeline_data.append({
                "Year": year,
                "Partner": f"{partner_name} ({partner_type})",
                "Partner Type": partner_type,
                "Cash Flow": amount,
                "Ownership": f"{ownership_pct:.0%}",
                "Flow Type": "Contribution" if amount < 0 else ("Distribution" if amount > 0 else "Hold Period"),
                "Partner Short": partner_name
            })
    
    timeline_df = pd.DataFrame(timeline_data)
    fig_timeline = px.bar(
        timeline_df,
        x="Year", 
        y="Cash Flow",
        color="Partner",
        # title="Partnership Annual Cash Flows",
        color_discrete_map={
            "Sponsor (GP)": "#dc2626",  # Red for GP
            "Investor (LP)": "#16a34a"  # Green for LP
        },
        height=600,
        labels={"Cash Flow": "Annual Cash Flow ($)"}
    )
    fig_timeline.layout.title.x = 0.5  # Center title
    fig_timeline.layout.legend = dict(orientation="h", yanchor="bottom", y=0.95, xanchor="center", x=0.5)  # Legend at top
    fig_timeline.layout.yaxis.range = [-12_000_000, 30_000_000]  # Fixed range for bar movement visibility
    fig_timeline.layout.xaxis.dtick = 1  # Show every year
    fig_timeline.layout.bargap = 0.3  # Proper gap between year groups
    fig_timeline.layout.bargroupgap = 0.1  # Small gap between partners within year
    fig_timeline.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    
    # Create simple partner metrics display
    metrics_md = "| Partner | Type | Ownership | Investment | Distributions | Net Profit | Equity Multiple | IRR |\n"
    metrics_md += "|---------|------|-----------|------------|---------------|------------|-----------------|-----|\n"
    
    for _, row in partner_df.round(3).iterrows():
        table_irr_display = f"{row['IRR']:.1%}" if row['IRR'] > 0 else "N/A"
        metrics_md += f"| {row['Partner']} | {row['Partner Type']} | {row['Ownership %']:.0f}% | ${row['Investment']:,.0f} | ${row['Distributions']:,.0f} | ${row['Net Profit']:,.0f} | {row['Equity Multiple']:.2f}x | {table_irr_display} |\n"
    
    partner_table = mo.md(metrics_md)
    
    # Left column: All controls
    controls_column = mo.vstack([        
        mo.md("## 👥 Partnership Configuration"),
        mo.hstack([
            mo.vstack([
                mo.md("**General Partner (GP)**"),
                gp_name,
                gp_share
            ]),
            mo.vstack([
                mo.md("**Limited Partner (LP)**"),
                lp_name,
                mo.md("LP Share: Auto-calculated")
            ])
        ], gap=2),
        
        mo.vstack([
            mo.md("**Distribution Method**"),
            distribution_method
        ]),
        
        # Conditional waterfall controls
        mo.vstack([
            mo.md("## 📊 Waterfall Structure") if "Waterfall" in distribution_method.value else mo.md(""),
                mo.md("---"),
                mo.vstack([
                    mo.md("**Preferred Return**"),
                    pref_return,
                    mo.md("_LPs receive this return first_")
                ]) if "Waterfall" in distribution_method.value else mo.md(""),
                mo.md("---"),
                mo.vstack([
                    mo.md("**Tier 1: Growth Phase**"), 
                    tier1_hurdle,
                    tier1_promote,
                    mo.md("_GP promote once hurdle met_")
                ]) if "Waterfall" in distribution_method.value else mo.md(""),
                mo.md("---"),
                mo.vstack([
                    mo.md("**Tier 2: Strong Performance**"),
                    tier2_hurdle, 
                    tier2_promote,
                    mo.md("_Higher promote for outperformance_")
                ]) if "Waterfall" in distribution_method.value else mo.md(""),
                mo.md("---"),
                mo.vstack([
                    mo.md("**Final Tier: Exceptional Returns**"),
                    final_promote,
                    mo.md("_Maximum promote above all hurdles_")
                ]) if "Waterfall" in distribution_method.value else mo.md(""),
                mo.md("---"),

        ]),
        
    ], gap=2)
    
        ######################################################### HERE
    # Right column: Metrics first, then charts
    charts_column = mo.vstack([

        mo.md("## 💰 Cash Flow Scenario"),
        mo.vstack([
            scenario_type,
            mo.md("_Choose a performance scenario to see how it affects distributions_"),
            timeline_years,
            mo.md("**Fixed investment**: $10M (focus on structure, not size)")
        ]),
        mo.md("### Detailed Partner Metrics"),
        partner_table,
        mo.md("### Partner Performance"),
        fig,
        mo.md("### Annual Cash Flows"), 
        fig_timeline,
    ], gap=2)
    
    # Main layout: Controls left, charts right
    mo.hstack([
        controls_column,
        charts_column
    ], widths=[1, 1], gap=3)
    
    return


@app.cell
def __(results, method, mo):
    """Show waterfall details if applicable"""
    
    if method == "waterfall" and "waterfall_details" in results:
        details = results["waterfall_details"]
        
        promote_structure = details["promote_structure"] 
        tiers_used = details["tiers_used"]
        final_rate = details["final_promote_rate"]
        
        waterfall_md = f"""
        ### 🌊 Waterfall Structure Details
        
        **Promote Type:** {promote_structure}  
        **Final Promote Rate:** {final_rate:.0%}
        
        **Tier Structure:**
        """
        
        for i, (hurdle, promote_rate) in enumerate(tiers_used):
            if i == 0:
                waterfall_md += f"\n- **Preferred Return:** {hurdle:.1%} IRR → {promote_rate:.0%} GP promote"
            else:
                waterfall_md += f"\n- **Tier {i}:** {hurdle:.1%} IRR → {promote_rate:.0%} GP promote" 
        
        waterfall_md += f"\n- **Final Tier:** Above all hurdles → {final_rate:.0%} GP promote"
        
        mo.md(waterfall_md)
    else:
        mo.md("_Pari passu distribution: no waterfall tiers apply_")
    return


@app.cell
def __(mo):
    """Educational footer 1"""
    mo.md("""
    
    ---
    
    ### Understanding Waterfall Distributions
    
    **Key Concepts:**
    - **Preferred Return**: LPs receive their target return first (typically 6-8%)
    - **Promote Tiers**: Higher IRR hurdles unlock higher GP promote percentages
    - **IRR-Based**: Distribution splits change dynamically based on running IRR performance
    
    **How to Read the Charts:**
    1. **Partner Performance**: Shows GP vs LP investment and distribution amounts
    2. **Annual Cash Flows**: Shows yearly contributions (negative) and distributions (positive) by partner
        - Red bars = GP cash flows, Green bars = LP cash flows  
        - Zero line helps distinguish contributions from distributions
        - Watch how GP gets disproportionately higher distributions when performance is strong
    """)
    return

@app.cell
def __(mo):
    """Educational footer 2"""
    mo.md("""
    ---
    
    ### Educational Notes
    
    This demo showcases how **institutional-grade partnership structures** work in real estate finance:
    
    **Real-World Applications:**
    - Private equity real estate funds
    - Development joint ventures  
    - Property acquisition partnerships
    - Opportunity zone investments
    
    **Why Waterfalls Matter:**
    - Align GP/LP interests through performance-based compensation
    - Provide downside protection for LPs via preferred returns
    - Reward GPs for outperformance through graduated promote structures
    - Enable sophisticated capital formation for large real estate projects
    
    **Performa's Waterfall Engine:**
    - IRR-based promote calculations with binary search precision
    - Multi-tier hurdle structures
    - Comprehensive partnership accounting
    - Industry-standard distribution mechanics
    
    Try different scenarios above to see how partnership terms affect distribution outcomes! 🚀
          
    ---
        
    *This demo shows how to configure a partnership structure and how it affects distribution outcomes.*
         
    """)
    return


if __name__ == "__main__":
    app.run()
