"""Private, fixed-budget expected-profit research. No brokerage orders."""
import os
import sys
import json
import uuid
import hashlib
import gzip
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import exchange_calendars as xcals

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive, month_windows
from trade_lab.edge_research import (extract_decisions, add_outcomes, fetch_option_history,
    append_option_features, feature_specs, walk_forward_search, PRICE_FEATURES, OPTION_FEATURES)
from trade_lab.cross_asset import fetch_cross_asset, append_cross_asset, covered_features
from trade_lab.macro import fetch_fred_market_daily, append_previous_day_macro, MACRO_FEATURES
from scripts.automated_research import required_env, send_private_report


def main():
    url, secret = required_env('SUPABASE_URL'), required_env('SUPABASE_SECRET_KEY')
    archive = SupabaseArchive(url, secret, os.getenv('SUPABASE_BUCKET', 'market-edge-history'))
    calendar = xcals.get_calendar('XNYS', start='2019-01-01', end='2026-09-30')
    session_closes = {pd.Timestamp(day).date(): row['close'] for day, row in calendar.schedule.iterrows()}
    parts, prior, excluded, price_hash = [], [], 0, hashlib.sha256()
    for first, _ in month_windows(date(2019, 1, 1), date(2026, 9, 30)):
        bars = archive.load(first)
        if bars is None:
            raise RuntimeError(f'Missing historical price month {first:%Y-%m}')
        price_hash.update(pd.util.hash_pandas_object(bars.sort_index(axis=1), index=False).values.tobytes())
        decisions, prior, bad = extract_decisions(bars, prior, session_closes=session_closes)
        excluded += bad
        if not decisions.empty:
            parts.append(add_outcomes(bars, decisions))
        if first.month == 12:
            print(f'Fixed-window features and costed outcomes prepared through {first.year}.', flush=True)
    data = pd.concat(parts, ignore_index=True)
    original_rows = len(data)
    # Distinct horizon/policy rows intentionally repeat dates; macro helper joins
    # many-to-one by date without making current-day observations available.
    market = fetch_fred_market_daily()
    data = append_previous_day_macro(data, market)
    optional_sources, source_errors = {}, {}
    options_available = False
    try:
        option_history, hashes = fetch_option_history()
        joined = append_option_features(data, option_history)
        if joined[list(OPTION_FEATURES)].notna().all(axis=1).mean() < .95:
            raise ValueError('Less than 95% Cboe feature coverage')
        data = joined
        options_available = True
        optional_sources['cboe'] = hashes
    except (RuntimeError, ValueError, OSError) as exc:
        source_errors['cboe'] = type(exc).__name__ + ': ' + str(exc)[:160]
        print('Optional Cboe source unavailable; reason saved privately.', flush=True)
    specs = feature_specs(MACRO_FEATURES, options_available)
    try:
        history, hashes = fetch_cross_asset()
        joined = append_cross_asset(data, history)
        cross_columns, excluded_sources = covered_features(joined)
        if excluded_sources:
            source_errors['cross_asset_coverage'] = excluded_sources
        if not cross_columns:
            raise ValueError('No cross-asset source meets the historical coverage requirement')
        data = joined
        columns = [*PRICE_FEATURES, *MACRO_FEATURES, *cross_columns]
        specs['price_macro_cross_asset'] = {'columns': columns, 'macro_weight': 1.}
        if options_available:
            specs['all_market_context'] = {'columns': [*columns, *OPTION_FEATURES], 'macro_weight': 1.}
        optional_sources['fred_cross_asset'] = hashes
    except (RuntimeError, ValueError, OSError) as exc:
        source_errors['fred_cross_asset'] = type(exc).__name__ + ': ' + str(exc)[:160]
        print('Optional cross-asset source unavailable; reason saved privately.', flush=True)
    all_columns = sorted(set(c for spec in specs.values() for c in spec['columns']))
    # Strict common sample makes every feature ablation directly comparable.
    data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=all_columns)
    if data.date.nunique() < 1500:
        raise RuntimeError(f'Too few common eligible research dates ({data.date.nunique()}); inspect calendar/history coverage')
    result = walk_forward_search(data, specs)
    ranking = result.pop('ranking')
    if len(ranking) > 1000:
        raise RuntimeError('Predeclared candidate budget exceeded')
    result['feature_group_development_leaders'] = json.loads(
        ranking.groupby('feature_set', sort=True).head(1).to_json(orient='records'))
    run_id = str(uuid.uuid4())
    snapshot = gzip.compress(data.to_csv(index=False).encode(), mtime=0)
    object_key = f'research/expected-profit-v1/{run_id}/features-and-outcomes.csv.gz'
    response = archive.session.post(archive._url(object_key), headers={**archive._headers(), 'Content-Type': 'application/gzip'},
                                    data=snapshot, timeout=90)
    if not response.ok:
        raise RuntimeError(f'Private experiment snapshot failed HTTP {response.status_code}')
    leaderboard_key = f'research/expected-profit-v1/{run_id}/all-candidates.json.gz'
    leaderboard_bytes = gzip.compress(ranking.to_json(orient='records').encode(), mtime=0)
    response = archive.session.post(archive._url(leaderboard_key), headers={**archive._headers(), 'Content-Type': 'application/gzip'},
                                    data=leaderboard_bytes, timeout=90)
    if not response.ok:
        raise RuntimeError(f'Private full leaderboard failed HTTP {response.status_code}')
    body = {'run_id': run_id, 'code_sha': os.getenv('GITHUB_SHA', 'manual'),
        'research_start': '2019-01-01', 'research_end': '2026-09-30', 'candidate_count': len(ranking),
        'summary': {'model_type': 'walk_forward_expected_net_profit_v1', **result},
        'leaderboard': json.loads(ranking.head(100).to_json(orient='records')),
        'diagnostics': {'no_live_orders': True, 'allocation_percent': 10,
            'predeclared_max_candidates': 1000, 'actual_candidates': len(ranking),
            'selection': 'Expanding-window 2021,2022,2023; minimum 75 trades and 10 per fold; two-session training embargo',
            'ranking': 'Mean fold return minus 0.75 fold volatility minus 0.5 pooled drawdown',
            'evaluation': 'ALL 2024-2026 history has been inspected at project level; no untouched holdout claim',
            'candidate_registration_sha': os.getenv('GITHUB_SHA', 'manual'),
            'trading_windows': '10:00,11:00,14:30 ET entries; 30/60 minute max holds',
            'exit_targets_pct': [None, .25, .5, .75], 'exit_stops_pct': [None, .25, .5, .5],
            'costs_bps_per_side': [5, 10], 'matched_rows': len(data), 'rows_before_source_alignment': original_rows,
            'excluded_incomplete_sessions': excluded, 'matched_sessions': int(data.date.nunique()),
            'session_calendar': 'exchange-calendars 4.13.2 XNYS; official half-day closes preserved in lag history',
            'price_data_sha256': price_hash.hexdigest(),
            'macro_data_sha256': hashlib.sha256(market.to_csv(index=False).encode()).hexdigest(),
            'optional_source_checksums': optional_sources, 'optional_source_errors': source_errors,
            'feature_sets': specs, 'snapshot_key': object_key,
            'full_leaderboard_key': leaderboard_key,
            'snapshot_sha256': hashlib.sha256(snapshot).hexdigest(),
            'sentiment_included': False, 'sec_financials_included': False,
            'limitations': ['Daily sources are latest history, not verified first-seen vintages',
                'Cboe indices primarily measure SPX volatility; usefulness for QQQ is a hypothesis',
                'Cross-asset observations delayed two business days; exact publication latency unverified',
                'Limit touches in minute bars do not establish executable fills; quote validation needed',
                'Confidence intervals do not correct for selection across many hypotheses',
                'No cash interest, taxes or commissions; 5/10bps slippage includes an assumed spread allowance',
                'No validated edge until genuinely new prospective predictions succeed']}}
    body = json.loads(json.dumps(body, allow_nan=False, default=lambda x: x.item() if hasattr(x, 'item') else str(x)))
    send_private_report(url, secret, body)
    print(f'Expected-profit research and reproducibility snapshot saved privately. Run {run_id}. No orders.', flush=True)


if __name__ == '__main__':
    main()
