#!/usr/bin/env python3
# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Isolated Pandas Runner
- Uses explicit pandas ledger class
- Uses baseline timeline from baselines/<deal>/metrics.json
- Outputs structured results
"""

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path to import example modules
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Explicit imports - avoid env vars
from performa.core.ledger.ledger_pandas import Ledger as PandasLedger
from performa.core.primitives import GlobalSettings, Timeline
from performa.deal.api import analyze

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


def main():
    deal_key = sys.argv[1] if len(sys.argv) > 1 else "office_development"
    module_path = EXAMPLES[deal_key]

    # Import example creator
    module = __import__(module_path, fromlist=["create_deal_via_composition"])
    create_deal = getattr(module, "create_deal_via_composition")

    # Timeline from baseline
    start, end = load_baseline_timeline(deal_key)
    timeline = Timeline.from_dates(start, end)

    # Explicit pandas ledger
    ledger = PandasLedger()

    results = analyze(create_deal(), timeline, GlobalSettings(), ledger=ledger)

    irr = results.levered_irr
    em = results.equity_multiple
    try:
        equity = abs(results.queries.equity_contributions().sum())
    except Exception:
        equity = None

    print(json.dumps({
        "backend": "pandas",
        "deal": deal_key,
        "timeline": {"start": start, "end": end},
        "irr": irr,
        "em": em,
        "equity": equity,
    }))


if __name__ == "__main__":
    main()
