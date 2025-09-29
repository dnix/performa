#!/usr/bin/env python3
# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Diagnostic Runner

Generates comprehensive diagnostics for a single deal and backend:
- Assumptions (formatted and raw)
- Configuration intentionality analysis
- Ledger semantic analysis and shape analysis
- Flow reasonableness and timeline analysis
- Pro forma summaries (annual, monthly)
- Pivot tables (monthly and annual)
- Key series exports (csv)

Writes artifacts to diagnostics/<deal>/<backend>/

Usage:
    uv run python tools/diagnostic_runner.py --backend pandas --deal office_development
    uv run python tools/diagnostic_runner.py --backend duckdb --deal value_add
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd

EXAMPLES = {
    "office_development": "examples.patterns.office_development_comparison",
    "residential_development": "examples.patterns.residential_development_comparison",
    "stabilized_acquisition": "examples.patterns.stabilized_comparison",
    "value_add": "examples.patterns.value_add_comparison",
}


def load_baseline_timeline(deal_key: str):
    path = Path(f"baselines/{deal_key}/metrics.json")
    data = json.loads(path.read_text())
    meta = data["core_metrics"]
    start = meta["timeline_start"]
    end = meta["timeline_end"]
    return start, end


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable structures.

    - Converts dict keys (including Period) to str
    - Converts pandas Period/Timestamp to str
    - Converts sets to lists
    - Leaves DataFrames/Series to caller (we output CSVs for those)
    """
    import pandas as pd  # local import to avoid global dependency

    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, set):
        return [_to_jsonable(v) for v in sorted(obj, key=lambda x: str(x))]
    if isinstance(obj, (pd.Period, pd.Timestamp)):
        return str(obj)
    # Basic scalars
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # Fallback: string representation
    return str(obj)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["pandas", "duckdb"], required=True)
    parser.add_argument(
        "--deal",
        choices=list(EXAMPLES.keys()),
        required=True,
    )
    parser.add_argument(
        "--outdir",
        default=None,
        help="Output directory (defaults to diagnostics/<deal>/<backend>)",
    )
    args = parser.parse_args()

    # Ensure project root on sys.path for importing examples
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    # Resolve output directory
    outdir = (
        Path(args.outdir)
        if args.outdir
        else Path("diagnostics") / args.deal / args.backend
    )
    ensure_dir(outdir)

    # Import core pieces lazily after deciding backend
    from performa.core.primitives import GlobalSettings, Timeline
    from performa.deal.api import analyze

    if args.backend == "duckdb":
        # Force alias to resolve to DuckDB for type compatibility
        os.environ["USE_DUCKDB_LEDGER"] = "true"
        from performa.core.ledger import Ledger as LedgerClass
    else:
        from performa.core.ledger.ledger_pandas import Ledger as LedgerClass

    # Load example creator
    module_path = EXAMPLES[args.deal]
    module = __import__(module_path, fromlist=["create_deal_via_composition"])
    create_deal = getattr(module, "create_deal_via_composition")

    # Baseline timeline
    start, end = load_baseline_timeline(args.deal)
    timeline = Timeline.from_dates(start, end)

    # Build deal and analyze
    deal = create_deal()
    ledger = LedgerClass()
    results = analyze(deal, timeline, GlobalSettings(), ledger=ledger)

    # Collect core metrics
    summary: Dict[str, float] = {
        "irr": results.levered_irr,
        "em": results.equity_multiple,
    }

    # Diagnostics: assumptions and configuration
    from performa.reporting import (
        analyze_cash_flow_timeline,
        analyze_configuration_intentionality,
        analyze_ledger_semantically,
        analyze_ledger_shape,
        generate_assumptions_report,
        validate_flow_reasonableness,
    )

    assumptions_md = generate_assumptions_report(
        deal, include_risk_assessment=True, include_defaults_detail=True
    )

    config_intent = analyze_configuration_intentionality(deal)
    ledger_semantic = analyze_ledger_semantically(ledger)
    ledger_shape = analyze_ledger_shape(results)

    # Archetype hint for validators
    archetype = results.archetype.lower()
    if "development" in archetype:
        deal_type = "development"
    elif "value" in archetype:
        deal_type = "value_add"
    else:
        deal_type = "stabilized"

    flow_check = validate_flow_reasonableness(results, deal_type=deal_type)
    timeline_check = analyze_cash_flow_timeline(results, deal_archetype=deal_type)

    # Reports: pro forma and pivot tables
    pro_forma_annual = results.reporting.pro_forma_summary(frequency="A")
    pro_forma_monthly = results.reporting.pro_forma_summary(frequency="M")
    pivot_monthly = results.reporting.pivot_table(frequency="M")
    pivot_annual = results.reporting.pivot_table(frequency="A")

    # Key series export
    series_map = {
        "noi": results.noi,
        "operational_cash_flow": results.operational_cash_flow,
        "project_cash_flow": results._queries.project_cash_flow(),
        "debt_service": results.debt_service,
        "equity_contributions": results._queries.equity_contributions(),
        "equity_partner_flows": results._queries.equity_partner_flows(),
        "capex": results._queries.capex(),
        "ti": results._queries.ti(),
        "lc": results._queries.lc(),
    }

    # Write outputs
    (outdir / "metrics.json").write_text(json.dumps(summary, indent=2))
    (outdir / "assumptions.md").write_text(assumptions_md)
    # Also include raw assumptions data from fluent interface
    assumptions_raw = results.reporting.assumptions_summary(formatted=False)

    (outdir / "config_intent.json").write_text(
        json.dumps(_to_jsonable(config_intent), indent=2)
    )
    (outdir / "ledger_semantic.json").write_text(
        json.dumps(_to_jsonable(ledger_semantic), indent=2)
    )
    (outdir / "ledger_shape.json").write_text(
        json.dumps(_to_jsonable(ledger_shape), indent=2)
    )
    (outdir / "flow_check.json").write_text(json.dumps(_to_jsonable(flow_check), indent=2))
    (outdir / "timeline_check.json").write_text(
        json.dumps(_to_jsonable(timeline_check), indent=2)
    )
    (outdir / "assumptions_raw.json").write_text(
        json.dumps(_to_jsonable(assumptions_raw), indent=2)
    )

    pro_forma_annual.to_csv(outdir / "pro_forma_annual.csv")
    pro_forma_monthly.to_csv(outdir / "pro_forma_monthly.csv")
    pivot_monthly.to_csv(outdir / "pivot_monthly.csv")
    pivot_annual.to_csv(outdir / "pivot_annual.csv")

    # Series CSVs
    for name, s in series_map.items():
        # Ensure PeriodIndex to_string for CSV
        df = pd.DataFrame({"period": s.index.astype(str), name: s.values})
        df.to_csv(outdir / f"series_{name}.csv", index=False)

    # Also dump ledger snapshot shape
    try:
        # Use direct ledger export if available
        if hasattr(ledger, "ledger_df"):
            ledger_df = ledger.ledger_df()
        else:
            # Fallback to queries property for older interfaces
            ledger_df = results.queries.ledger
        ledger_df.to_csv(outdir / "ledger_snapshot.csv", index=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()


