# Performa

Open-source real estate financial analysis framework purpose-built for the AI era.

## Vision

Performa aims to be the open standard for real estate financial modeling, providing:

- Atomic, composable primitives and tools for real estate financial analysis
- AI-ready data models and schemas for automated underwriting
- A Python framework to enable browser-based modeling templates and applications such as in Marimo using Pyodide (WASM)
- Eventually provide a backend API and SDK for real-time data integration and self-building financial models and MCP servers for LLM-powered underwriting
- Enable a future with real-time data integration and self-building financial models
- Power a common model specification (similar to what ISDA Common Model does for financial derivatives)

### Why FOSS?

- Excel is problematic despite being "free"
  - Too freeform, leading to replication and trust issues
  - Prone to errors
  - Hard to share, limited real-time collaboration
- Proprietary solutions are limiting
  - Not auditable
  - Not composable
  - Expensive barrier to entry (not even education resources are free!)
  - Data ownership concerns
- Industry needs a free standard to drive consistency and broad adoption

## Project Structure

```sh
src/performa/
├── asset/                # Core real estate asset primitives
│   ├── _property.py      # Property characteristics
│   ├── _tenant.py        # Tenant and lease modeling
│   ├── _revenue.py       # Revenue modeling
│   ├── _expense.py       # Expense modeling
│   ├── _recovery.py      # Recovery calculations
│   ├── _rollover.py      # Lease rollover analysis
│   ├── _growth.py        # Growth assumptions
│   ├── _line_item.py     # Financial line items
│   ├── _types.py         # Type definitions
│   └── _enums.py         # Enumerations
├── debt/                 # Debt modeling components
│   ├── _permanent.py     # Permanent debt facilities
│   ├── _construction.py  # Construction financing
│   ├── _amortization.py  # Loan amortization
│   └── _rates.py         # Interest rate modeling
├── development/          # Development project modeling
│   ├── _project.py       # Project definition
│   ├── _program.py       # Development program
│   ├── _budget.py        # Development budget
│   ├── _model.py         # Financial modeling
│   └── _cash_flow.py     # Cash flow projections
├── utils/                # Utility functions and tools
│   ├── _decimal.py       # Decimal number handling
│   ├── _money.py         # Currency calculations
│   └── _viz.py           # Visualization tools
└── valuation/            # Valuation methodologies
```

## Core Principles

1. **Transparency**
   - Auditable calculations
   - Clear methodology documentation
   - Open-source codebase

2. **Composability**
   - Modular components
   - Clear interfaces
   - Extensible design

3. **Accuracy**
   - Industry-standard methods
   - Proper rounding and precision
   - Comprehensive validation

4. **AI-Ready**
   - Structured data models
   - Strong typing and data validation
   - Clear schemas
   - Consistent interfaces

## (Future)Business Model

- Hosted applications powered by OSS core
  - Real-time collaboration
  - Model persistence
  - Analytics tools
- Enterprise support and integration
- Education and training
- Data integration services
  - Market data
  - Assumptions support
  - Benchmarking

## Why Now?

1. **AI Revolution**
   - Code is the new spreadsheet
   - Need for machine-readable models
   - Automated underwriting potential

2. **Technology Maturity**
   - WASM and Pyodide enable browser-based Python
   - Reactive Python frameworks (e.g., Marimo)
   - Modern data science tools

3. **Market Conditions**
   - Increased deal scrutiny
   - Need for faster analysis
   - Data-driven decision making
   - Concerns over data rights
