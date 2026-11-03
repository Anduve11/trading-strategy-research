"""Fetch real Coinbase spot bars and run the locked 2017–2023 baseline.

This script is used by the isolated pull-request research workflow. It never
loads 2024+ data, reads account credentials, or submits orders.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

# Allow running this file directly from the repository root or another folder.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trade_lab.crypto_research import (
    DEVELOPMENT_START,
    GRANULARITIES,
    LOCKED_HOLDOUT_START,
    PRODUCTS,
    VALIDATION_END,
    WARMUP_START,
    audit_crypto_bars,
    fetch_coinbase_candles,
    run_candidate_suite,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--granularity", type=int, choices=tuple(GRANULARITIES), default=21600)
    parser.add_argument("--cost-scenarios", default="10,25,50", help="Combined bps per side; comma-separated.")
    parser.add_argument("--allocation", type=float, default=100.0)
    args = parser.parse_args()
    costs = [float(value) for value in args.cost_scenarios.split(",") if value.strip()]
    if not costs or any(value <= 0 or value >= 10000 for value in costs):
        raise SystemExit("Provide positive per-side cost scenarios below 10,000 bps.")

    print(
        f"Downloading Coinbase {GRANULARITIES[args.granularity]} candles for "
        f"{WARMUP_START} through {VALIDATION_END}; reported research starts {DEVELOPMENT_START}; "
        f"holdout from {LOCKED_HOLDOUT_START} is excluded."
    )
    all_bars = []
    for product in PRODUCTS:
        bars = fetch_coinbase_candles(
            product,
            WARMUP_START,
            VALIDATION_END,
            args.granularity,
            request_pause_seconds=0.12,
        )
        audit = audit_crypto_bars(bars, args.granularity, DEVELOPMENT_START, VALIDATION_END)
        coverage = float(audit.iloc[0]["coverage_pct"])
        max_gap = int(audit.iloc[0]["max_missing_streak_bars"])
        unexpected = int(audit.iloc[0]["unexpected_bars"])
        print(
            f"{product}: {len(bars):,} fetched bars; coverage {coverage:.2f}%; "
            f"longest missing run {max_gap} bars; off-grid bars {unexpected}"
        )
        if coverage < 95.0:
            raise SystemExit(f"Coverage for {product} is below 95%; do not interpret the backtest.")
        if unexpected:
            raise SystemExit(f"{product} has off-grid candle timestamps; do not interpret the backtest.")
        all_bars.append(bars)

    combined = pd.concat(all_bars, ignore_index=True)
    for cost in costs:
        results = run_candidate_suite(
            combined,
            args.granularity,
            cost_bps_each_side=cost,
            allocation_pct=args.allocation,
        )
        print(f"\n=== Combined cost: {cost:g} bps per side; allocation: {args.allocation:g}% ===")
        print(results.to_string(index=False, float_format=lambda value: f"{value:.2f}"))


if __name__ == "__main__":
    main()
