# Performa Marimo Showcase Demos

Interactive demonstrations of Performa's real estate financial modeling capabilities using Marimo notebooks.

## Quick Start

### Prerequisites

For installation and setup instructions, see [DEVELOPMENT.md](../../../DEVELOPMENT.md) in the main repository.

### Run Any Demo

```bash
# Navigate to showcase directory
cd examples/marimo/showcase/

# Demo 1.1: Compare multiple draw schedules
marimo run showcase_01_draw_schedules.py

# Demo 1.2: Build a single custom draw schedule  
marimo run showcase_02_single_schedule_builder.py

# Demo 1.3: Office absorption modeling (RECOMMENDED)
marimo run showcase_03_office_absorption.py

# Demo 1.4: Partnership waterfall & promote structures
marimo run showcase_04_partnership_waterfall.py

# Demo 1.5: Complete residential development (NEW!)  
marimo run showcase_05_residential_development.py

# Alternative: Run as Python script (no browser, just output)
python showcase_01_draw_schedules.py
python showcase_02_single_schedule_builder.py
python showcase_03_office_absorption.py
python showcase_04_partnership_waterfall.py
python showcase_05_residential_development.py
```

### Open in Browser

- Demo opens automatically at `http://localhost:2718` (or auto-assigned port)
- Interactive controls allow real-time parameter exploration
- All visualizations update automatically

## Available Demos

### 📊 Demo 1.1: Draw Schedule Comparison

**File**: `showcase_01_draw_schedules.py`

Showcases 6 different capital deployment patterns side-by-side:
- **Uniform**: Even spending over time
- **S-Curve**: Realistic construction pattern (slow → fast → slow)  
- **Front-Loaded**: All money upfront (land acquisition)
- **Back-Loaded**: All money at completion (retention release)
- **First/Last Split**: Split between start and end periods
- **Custom Manual**: User-defined pattern

**Controls**: Project cost, duration, curve parameters (sliders)

### 🎯 Demo 1.2: Single Schedule Builder (RECOMMENDED)

**File**: `showcase_02_single_schedule_builder.py`

Build and customize one draw schedule at a time:

- **Dropdown Selection**: Choose from 6 schedule types
- **Dynamic Parameters**: Smart forms that change based on your selection
- **Dual Visualization**: Monthly bars + cumulative progress line
- **Detailed Analysis**: Period-by-period cash flow table with percentages
- **Contextual Help**: Educational content that changes per pattern

**Controls**: Project naming, cost/duration, pattern-specific parameters

### 🏢 Demo 1.3: Office Absorption Modeling (RECOMMENDED)
**File**: `showcase_03_office_absorption.py`

Transform vacant office space into multiple leases using sophisticated leasing strategies:

- **Building Setup**: Configure floors, square footage, building characteristics
- **Leasing Strategies**: Fixed Quantity (lease X SF every Y months) vs Equal Spread (even pace)
- **Market Terms**: Set base rent, lease duration, leasing start timing
- **Live Execution**: Watch vacant floors subdivide into individual tenant leases
- **Visual Timeline**: Dual-axis charts showing individual leases and cumulative progress
- **Revenue Analysis**: Total rent, occupancy rates, leasing velocity metrics

**Controls**: Building configuration, strategy selection, market lease terms

**Real-World Applications**:
- Office development lease-up planning
- Vacant building repositioning strategies
- Investment underwriting for office properties
- Leasing team target setting and performance tracking

### 🌊 Demo 1.4: Partnership Waterfall & Promote Structures

**File**: `showcase_04_partnership_waterfall.py`

Explore sophisticated real estate equity distribution mechanisms:

- **Partnership Setup**: Configure General Partners (GP) and Limited Partners (LP) with ownership percentages
- **Waterfall Types**: Simple pro-rata vs complex IRR-based waterfall structures
- **Promote Mechanics**: Preferred returns, catch-up provisions, and graduated promote rates
- **Performance Analysis**: IRR, equity multiples, and cash-on-cash returns for each partner
- **Distribution Scenarios**: Test different return scenarios and see how they flow through the waterfall
- **Interactive Tables**: Detailed distribution breakdowns with cumulative tracking

**Controls**: Partnership percentages, preferred returns, promote rates, cash flow scenarios

### 🏙️ Demo 1.5: Pattern Unfurling Showcase (NEW!)

**File**: `showcase_05_residential_development.py`

**The flagship demonstration of Performa's Pattern architecture:**

This notebook showcases the "magic" of Pattern unfurling—how a few simple parameters transform into a complete institutional-grade financial model.

- **Pattern → Analysis**: Watch `ResidentialDevelopmentPattern` generate a complete deal from 7 parameters
- **Real Results, No Hardcoding**: All metrics and displays use actual analysis results
- **Glass Box Transparency**: Complete ledger displayed as annual pivot table using `results.reporting.pivot_table()`
- **Top-Level Metrics**: Levered/unlevered IRR, equity multiple, net profit from `DealResults`
- **Partnership Analysis**: Partner-level returns with GP/LP waterfall distributions
- **Cash Flow Visualization**: Annual equity flows with investment vs distribution breakdown

**What Gets Generated Automatically**:
- 120-unit multifamily property with detailed unit mix (1BR/2BR)
- Construction-to-permanent financing structure
- GP/LP partnership with waterfall and promote
- Complete transactional ledger with every cash flow
- Multi-year projections and performance metrics

**Key Architecture Demonstrations**:
- `marimo.ui.dictionary` for clean parameter entry
- Pattern `.analyze()` method generating full `DealResults`
- `results.reporting.pivot_table()` for ledger display
- `marimo.ui.table()` for interactive data tables
- Real-time reactive updates across all visualizations

**Controls**: Project name, land cost, units, construction cost/duration, hold period, exit cap rate

**Real-World Applications**:
- Teaching the Pattern abstraction to new users
- Demonstrating Performa's "simple parameters → complex model" philosophy
- Interactive investment committee presentations
- Developer education on institutional modeling standards

## Features Showcased

### Performa Core Capabilities

- **Draw Schedules**: Multiple deployment patterns with configurable parameters
- **Timeline Management**: Flexible period-based modeling
- **Office Absorption**: Sophisticated vacant space lease-up modeling with subdivision logic
- **Partnership Structures**: Complex equity waterfalls and promote calculations
- **Cash Flow Modeling**: Comprehensive financial projections

### Marimo Integration

- **Reactive Programming**: UI changes trigger automatic recalculation
- **Interactive Visualizations**: Plotly charts with hover tooltips and zooming
- **Responsive Layouts**: Adaptive UI components using vstack/hstack
- **Educational Content**: Rich markdown with explanations and context

### Data Visualization

- **Timeline Charts**: Annual and cumulative cash flow patterns
- **Performance Metrics**: IRR, equity multiples, cash-on-cash returns
- **Comparative Analysis**: Side-by-side schedule and partner comparisons
- **Interactive Tables**: Sortable data exploration

## Tips

- Adjust sliders to see immediate visualization updates
- Compare patterns side-by-side in the stacked bar chart
- Review summary table for key statistics
- Read explanations to understand real estate applications

## Troubleshooting

If demo doesn't start:

1. Ensure you're in the correct directory
2. Check that Performa is installed: `python -c "import performa; print('✅ Performa working')"`
3. Verify marimo installation: `marimo --version`

## Educational Value

These demos serve as:

- **Learning Tools**: Interactive exploration of real estate finance concepts
- **Documentation**: Working examples of Performa API usage
- **Prototyping Platform**: Foundation for building custom analysis tools
- **Client Presentations**: Professional interactive demonstrations

## Next Steps

- Start with **Demo 1.3** (Office Absorption) for the most comprehensive real estate modeling example
- Explore **Demo 1.4** (Partnership Waterfall) for equity distribution and promote structures
- Try **Demo 1.2** (Single Schedule Builder) for capital deployment planning
- Review **Demo 1.1** (Draw Schedule Comparison) for pattern analysis
- Modify the demo code to experiment with your own scenarios
- Check out `basic_office_development.py` for complete deal examples

Future demos may include:

- Development project cash flows
- Debt facility modeling  
- Valuation methodologies
- Portfolio analysis
- Risk and sensitivity analysis

## Support

For questions or issues with the demos:

- Review the Performa documentation
- Check the Marimo usage guide
- Examine the demo source code for implementation details
