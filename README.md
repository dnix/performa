> [!CAUTION]
> **Pre-Alpha Status:** This project is under active development. Breaking changes are expected; APIs and data structures may change significantly. Validation testing is in progress. We are working doggedly toward an initial release. Comments, feedback, and contributions are most welcome! 🚧

<br>
<br>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/wordmark-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/wordmark-light.svg">
    <img src="docs/wordmark.svg" alt="Performa" width="275">
  </picture>
</p>

<br>

<p align="center">
  <em>An open standard for real estate financial modeling — transparent, composable, and AI-ready</em>
</p>

  <p align="center">
    <img src="https://img.shields.io/badge/Status-Pre--Alpha-red" alt="pre-alpha" />
    <a href="https://img.shields.io/badge/License-Apache%202.0-blue.svg"><img src="https://img.shields.io/badge/License-Apache%202.0-yellow.svg" alt="Apache 2.0 License" /></a>
    <a href="https://pydantic.dev"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json" alt="Pydantic v2" /></a>
    <a href="https://github.com/performa-dev/performa/blob/main/CODE_OF_CONDUCT.md"><img src="https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg" alt="Contributor Covenant" /></a>
    <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python 3.10+" />
  </p>

<br>

**Performa** is an open-source Python library that provides transparent, composable, and rigorously tested building blocks for real estate financial modeling. It serves as a protocol designed to be the common language for the next generation of analysts, developers, investors, financiers, and AI assistants.

For decades, real estate finance has been powered by spreadsheets and proprietary "black box" software. But today, our industry stands at an inflection point. The dawn of the AI era demands models that are not just human-readable, but also machine-executable — a "glass box" approach that is transparent, auditable, and extensible.

Highlights:

- 💎 **Glass box transparency**: Every calculation is explicit and auditable—no hidden formulae
- 🏢 **Asset-centric modeling**: Deep expertise for office, residential, retail, etc.
- 🤝 **Deal structuring**: Partnership waterfalls, debt facilities, and acquisition modeling
- 💰 **Financing facilities**: Construction loans, permanent debt, and complex structures
- 📈 **Comprehensive valuation**: DCF, direct cap, and sales comparison methods
- 🏗️ **Development lifecycle**: Full project modeling from construction to stabilization
- 🧩 **Composable and extensible**: Connect components for quick scripts or complex apps
- 🐍 **Fully Pythonic**: modern language for data science and financial modeling
- ⏳ **Git-friendly**: version control for your models and assumptions
- 🤖 **Purpose-built for AI**: Structured data models that speak the native language of LLMs

<br>

<p align="center">
  <img src="docs/teaser.gif" alt="Performa Interactive Demo" width="600" />
</p>

<p align="center">
  <sup><em>Demo notebooks visually exploring real estate concepts using Performa building blocks</em></sup>
</p>

<br>


## Why Performa? An Industry at an Inflection Point

For decades, real estate finance has been powered by two remarkable tools: the infinite flexibility of the [spreadsheet](https://www.hyperindexed.com/blog/2018/7/31/visicalcs-enduring-vision) and the institutional acceptance of proprietary "black box" software. These tools built the modern real estate world. But today, our industry stands at an inflection point, much like the derivatives market did before the [ISDA Common Domain Model (CDM)](https://github.com/finos/common-domain-model) created a universal language for complex trades.

Every transaction involves the same frustrating dance: sponsor, lender, and investor each rebuild the financial model in their own format just to trust the numbers and logic. This creates friction, wastes valuable time, introduces risk, and makes the market less liquid.

**`performa` aims to be the lingua franca for real estate project economics.**

This comes at a pivotal moment: the _dawn of the AI era_ and the _maturation of data science tooling_. We can speak plain language to create complex models with rules, and with `performa` we get guardrails and reproducibility - not ad hoc AI slop or hallucinations. And now, with breakthrough work in [Pyodide](https://pyodide.org/) and [WASM](https://webassembly.org/), we can run Python - the stalwart language of data science - trivially, in a web browser.

## What is Performa

`performa` provides "Lego brick" components where each piece — a lease, expense, loan — is a validated Pydantic data model that connects seamlessly with others. Every input is validated and every calculation is explicit Python code you can audit and trust.

**For Analysts & Developers:** Spend less time on boilerplate logic and debugging formulas, and more time on what matters: the assumptions, the strategy, and the deal itself. Move from being a "spreadsheet jockey" to an architect of value.

**For Institutions & Stakeholders:** Drastically reduce transaction friction. When a developer, a lender, and an investor all speak the same language, diligence becomes faster, risk is minimized, and capital can move more efficiently.

**For the AI-Powered Future:** Stop trying to teach AI how to decipher a spreadsheet. Also don't have it reinvent the wheel! Instead, give it the native building blocks it understands. `performa` is the "math co-processor" for real estate AI, turning natural language requests into institutional-grade, auditable financial models.

_Spend less time building models and more time creating value._

### Library Architecture

`performa` is organized into logical modules that reflect the natural structure of real estate finance:

🏢 **[Asset Models](/src/performa/asset/README.md)**: Property-specific modeling with deep expertise for each asset class. Includes mature [office](/src/performa/asset/office/README.md) modeling with complex lease structures and recovery methods, [residential](/src/performa/asset/residential/README.md) multifamily properties with unit-centric modeling and value-add capabilities, and shared [commercial](/src/performa/asset/commercial/) logic. Retail, industrial, hotel modules (and more!) coming soon.

⚙️ **[Core Framework](/src/performa/core/README.md)**: The foundational building blocks that power everything. Contains [primitives](/src/performa/core/primitives/README.md) for timeline management and cash flow models, [base classes](/src/performa/core/base/README.md) that provide abstract foundations for all property types, and [capital planning](/src/performa/core/capital/README.md) tools for sophisticated project/construction management with flexible timing (linear, s-curve, upfront, etc.).

📊 **[Analysis Engine](/src/performa/analysis/README.md)**: The orchestrator that brings models to life through multi-phase cash flow calculations with dependency resolution. Features universal analysis context and assembler pattern for efficient object resolution, plus automatic scenario selection based on model type.

🤝 **[Deal Structuring](/src/performa/deal/README.md)**: Complete deal-level modeling and partnership structures supporting multi-partner waterfall mechanics with IRR hurdles. Handles acquisition terms, fee structures, and partnership accounting with distribution calculations for complex investment scenarios.

💰 **[Debt & Finance](/src/performa/debt/README.md)**: Comprehensive real estate financing capabilities including construction and permanent debt facilities. Supports amortization schedules, interest rate modeling, and multi-tranche debt structures for complex financing arrangements.

🏗️ **[Development](/src/performa/development/README.md)**: Development project modeling from ground-up to stabilization including construction budgets and timeline management. Features development blueprints and asset factory patterns for lease-up and absorption modeling throughout the development lifecycle.

📈 **[Valuation](/src/performa/valuation/README.md)**: Industry-standard valuation methodologies including DCF analysis with terminal value calculations. Supports direct capitalization and sales comparison methods with universal metrics and yield calculations.

📋 **[Reporting](/src/performa/reporting/README.md)**: Professional-grade reporting interfaces for industry-standard financial statements. Provides customizable report generation and integration with visualization tools for comprehensive analysis presentation.

## Installation & Usage

`performa` is a Python library. You can import it into your own projects, or you can consume it directly in a web browser with example notebooks. Below are the installation instructions for both.

### Local Python Installation

This assumes you have Python installed. If not, see [python.org](https://www.python.org/downloads/). We recommend using Homebrew and ASDF to install Python to a supported version. From there, use our Makefile for streamlined setup.

```bash
# Clone the repository
git clone https://github.com/performa-dev/performa.git
cd performa

# Complete development setup (includes asdf, uv, venv, and dependencies)
make dev-setup

# Verify everything is working
make check
```

For production installation only:
```bash
# Setup without development dependencies
make install-prod
```

Alternative manual installation:
```bash
# Install ASDF and a supported version of Python
brew install asdf
asdf install python 3.11.9
asdf local python 3.11.9
asdf exec python -m venv .venv
source .venv/bin/activate

# Install from GitHub (current)
pip install git+https://github.com/performa-dev/performa.git

# Coming soon to PyPI
pip install performa
```

For development installation, see [DEVELOPMENT.md](DEVELOPMENT.md).

#### Python Quick Start

```python
from performa.asset.office import OfficeProperty
from performa.analysis import run
from performa.core.primitives import Timeline, GlobalSettings

# Create property model
property = OfficeProperty(...)

# Run analysis
timeline = Timeline.from_dates('2024-01-01', '2033-12-31')
scenario = run(property, timeline, GlobalSettings())

# Get results
cash_flows = scenario.get_cash_flow_summary()
```

### Web Browser Usage

No installation, just batteries-included notebooks. Coming soon!

## Contributing & Call for Feedback

This project is in active development. Feedback from real estate professionals, developers, and academics is essential.

[Development Guide](DEVELOPMENT.md) • [Contributing](CONTRIBUTING.md) • [License](LICENSE)

## Inspiration ✨

Performa is a **reinvention** of the real estate financial model as a reproducible, interactive, auditable, shareable application instead of an error-prone spreadsheet. It is a protocol designed to be the common language for the next generation of analysts, developers, investors, and AI assistants.

Tooling matters; the tools we use shape the way we think - better tools, better minds, better outcomes. With Performa, we hope to provide the real estate community with a better structure with which to imagine the built future and to communicate it, to experiment with code and to share it; to learn financial modeling and to teach it.

Our inspiration comes from countless sources, but especially [Pydantic](https://docs.pydantic.dev/)'s data modeling standards, dataviz and abstractions in [Observable](https://observablehq.com/) + [Plot](https://observablehq.com/plot/) + [D3](https://d3js.org/), [marimo](https://marimo.io/), array math in [Numpy](https://numpy.org/) and [Pandas](https://pandas.pydata.org/), data apps in [streamlit](https://github.com/streamlit/streamlit), data ETL in [Airflow](https://airflow.apache.org/) and [DAG](https://en.wikipedia.org/wiki/Directed_acyclic_graph)s, statistics in [R](https://www.r-project.org/), configuration and convention in [Kubernetes](https://kubernetes.io/), and more esoteric terrain like [geospatial FOSS](https://www.osgeo.org/) (maps and geoprocessing), and [EnergyPlus](https://energyplus.net/) (building energy modeling).

---

_This project is underpinned by the power of data-driven decision-making and the open source movement._ 🚀
