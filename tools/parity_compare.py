#!/usr/bin/env python3
# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Parity Comparison Runner

Compares diagnostics for pandas vs duckdb and against baseline fixtures.

Checks per deal:
- Metrics: IRR, EM, Equity (sum of equity contributions)
- Ledger: transaction count
- Series parity: NOI, OCF, PCF, Debt Service, Equity Contributions, Equity Partner Flows, CapEx, TI, LC

Outputs a markdown summary to PARITY_SUMMARY.md and prints a concise JSON.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

DEALS = [
    "office_development",
    "residential_development",
    "stabilized_acquisition",
    "value_add",
]

SERIES_NAMES = [
    "noi",
    "operational_cash_flow",
    "project_cash_flow",
    "debt_service",
    "equity_contributions",
    "equity_partner_flows",
    "capex",
    "ti",
    "lc",
]


@dataclass
class MetricSet:
    irr: float
    em: float
    equity: float
    tx_count: int


@dataclass
class DealParityResult:
    deal: str
    pandas_vs_baseline: Dict[str, bool]
    duckdb_vs_pandas: Dict[str, bool]
    duckdb_vs_baseline: Dict[str, bool]
    series_pass: bool
    series_mismatch_counts: Dict[str, int]
    series_max_abs_diff: Dict[str, float]


def load_backend_metrics(deal: str, backend: str) -> MetricSet:
    diag = Path("diagnostics") / deal / backend
    metrics = json.loads((diag / "metrics.json").read_text())

    # Equity: sum equity contributions
    eq_df = pd.read_csv(diag / "series_equity_contributions.csv")
    equity_sum = float(abs(eq_df["equity_contributions"].sum()))

    # Ledger tx count
    ledger_df = pd.read_csv(diag / "ledger_snapshot.csv")
    tx_count = int(len(ledger_df))

    return MetricSet(
        irr=float(metrics["irr"]),
        em=float(metrics["em"]),
        equity=equity_sum,
        tx_count=tx_count,
    )


def load_baseline_metrics(deal: str) -> Tuple[float, float, float, int]:
    data = json.loads((Path("baselines") / deal / "metrics.json").read_text())
    core = data["core_metrics"]
    ledger_stats = data["ledger_stats"]
    return (
        float(core["irr"]),
        float(core["em"]),
        float(core["equity"]),
        int(ledger_stats["transaction_count"]),
    )


def nearly_equal(a: float, b: float, tol: float = 1e-12) -> bool:
    return abs(a - b) <= tol


def compare_series(deal: str) -> Tuple[bool, Dict[str, int], Dict[str, float]]:
    base = Path("diagnostics") / deal
    mismatches: Dict[str, int] = {}
    max_abs_diff: Dict[str, float] = {}
    all_pass = True

    for name in SERIES_NAMES:
        p = pd.read_csv(base / "pandas" / f"series_{name}.csv")
        d = pd.read_csv(base / "duckdb" / f"series_{name}.csv")
        # Join on period
        m = p.merge(d, on="period", how="outer", suffixes=("_pandas", "_duckdb")).fillna(0.0)
        col_p = f"{name}_pandas"
        col_d = f"{name}_duckdb"
        diff = (m[col_p] - m[col_d]).abs()
        mismatches[name] = int((diff > 1e-9).sum())
        max_abs_diff[name] = float(diff.max() if len(diff) else 0.0)
        if mismatches[name] != 0:
            all_pass = False

    return all_pass, mismatches, max_abs_diff


def main() -> None:
    summary_md: List[str] = []
    results: List[DealParityResult] = []

    for deal in DEALS:
        # Load
        p = load_backend_metrics(deal, "pandas")
        d = load_backend_metrics(deal, "duckdb")
        b_irr, b_em, b_equity, b_tx = load_baseline_metrics(deal)

        # Parity checks (strict)
        p_vs_b = {
            "irr": nearly_equal(p.irr, b_irr),
            "em": nearly_equal(p.em, b_em),
            "equity": nearly_equal(p.equity, b_equity, tol=1e-6),
            "tx_count": p.tx_count == b_tx,
        }

        d_vs_p = {
            "irr": nearly_equal(d.irr, p.irr),
            "em": nearly_equal(d.em, p.em),
            "equity": nearly_equal(d.equity, p.equity, tol=1e-6),
            "tx_count": d.tx_count == p.tx_count,
        }

        d_vs_b = {
            "irr": nearly_equal(d.irr, b_irr),
            "em": nearly_equal(d.em, b_em),
            "equity": nearly_equal(d.equity, b_equity, tol=1e-6),
            "tx_count": d.tx_count == b_tx,
        }

        series_pass, mismatches, maxdiff = compare_series(deal)

        results.append(
            DealParityResult(
                deal=deal,
                pandas_vs_baseline=p_vs_b,
                duckdb_vs_pandas=d_vs_p,
                duckdb_vs_baseline=d_vs_b,
                series_pass=series_pass,
                series_mismatch_counts=mismatches,
                series_max_abs_diff=maxdiff,
            )
        )

    # Build markdown
    summary_md.append("## Parity Summary")
    for r in results:
        all_pass = (
            all(r.pandas_vs_baseline.values())
            and all(r.duckdb_vs_pandas.values())
            and all(r.duckdb_vs_baseline.values())
            and r.series_pass
        )
        summary_md.append(f"\n### {r.deal}")
        summary_md.append(f"- PASS: {'YES' if all_pass else 'NO'}")
        summary_md.append("- pandas vs baseline: " + ("PASS" if all(r.pandas_vs_baseline.values()) else "FAIL"))
        summary_md.append("- duckdb vs pandas: " + ("PASS" if all(r.duckdb_vs_pandas.values()) else "FAIL"))
        summary_md.append("- duckdb vs baseline: " + ("PASS" if all(r.duckdb_vs_baseline.values()) else "FAIL"))
        summary_md.append(f"- series parity: {'PASS' if r.series_pass else 'FAIL'}")
        summary_md.append("  - mismatches: " + json.dumps(r.series_mismatch_counts))
        summary_md.append("  - max_abs_diff: " + json.dumps(r.series_max_abs_diff))

    Path("PARITY_SUMMARY.md").write_text("\n".join(summary_md))

    # Print concise machine-readable summary
    print(json.dumps([asdict(r) for r in results]))


if __name__ == "__main__":
    main()


