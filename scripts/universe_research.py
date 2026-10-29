"""Pair-by-pair native-proxy tests and matched-date Nasdaq controls. No orders."""
import argparse
import gzip
import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict
from datetime import date
from pathlib import Path
import pandas as pd
import exchange_calendars as xcals
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trade_lab.archive import SupabaseArchive, month_windows
from trade_lab.etf_universe import PAIRS, load_pair, save_pair, download_pair, aliases, match_control
from trade_lab.edge_research import extract_decisions, walk_forward_search, PRICE_FEATURES, predict_profit, choose_side, metrics
from trade_lab.window_quality import window_outcomes
from trade_lab.macro import fetch_fred_market_daily, append_previous_day_macro, MACRO_FEATURES
from scripts.automated_research import required_env, send_private_report

START, END = date(2019, 1, 1), date(2026, 9, 30)


def prepare(archive, name, session_closes):
    blocks, shadows, prior, excluded, seen = [], [], [], 0, 0
    quality = {'observed_windows':0, 'interpolated_only_windows':0, 'rejected_windows':0}
    for first, _ in month_windows(START, END):
        bars = load_pair(archive, name, first)
        if bars is None:
            raise ValueError(f'Missing universe month {name} {first:%Y-%m}')
        normalized = aliases(bars, PAIRS[name])
        seen += normalized.timestamp.dt.tz_convert('America/New_York').dt.date.nunique()
        features, prior, bad = extract_decisions(normalized, prior, session_closes=session_closes, require_full_pair=False)
        excluded += bad
        if not features.empty:
            primary, shadow, counts = window_outcomes(normalized, features)
            if not primary.empty:blocks.append(primary)
            if not shadow.empty:shadows.append(shadow)
            for k,v in counts.items():quality[k] += v
    return (pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame()), (pd.concat(shadows, ignore_index=True) if shadows else pd.DataFrame()), {'sessions_seen': seen, 'invalid_proxy_history_days': excluded, **quality}


def enough_data(frame):
    if frame.empty:
        return False
    years = pd.to_datetime(frame.date).dt.year
    counts = frame.assign(year=years).groupby('year').date.nunique()
    return all(counts.get(y, 0) >= 100 for y in range(2019, 2026)) and counts.get(2026, 0) >= 60


def eligible_policies(candidate, control):
    """Every tested timing/exit policy needs adequate observed data each year."""
    keys = ['decision_minute','horizon','exit_policy']
    accepted = [dict(zip(keys, key)) for key, sub in candidate.groupby(keys)
                if enough_data(sub) and int((pd.to_datetime(sub.date).dt.year < 2021).sum()) >= 252]
    if not accepted:return candidate.iloc[:0], control.iloc[:0]
    keep = pd.DataFrame(accepted)
    return candidate.merge(keep,on=keys,validate='many_to_one'), control.merge(keep,on=keys,validate='many_to_one')


def sensitivity_report(primary, shadow, selected, specs):
    if shadow.empty or selected is None:return {'status':'NO_ELIGIBLE_INTERPOLATED_WINDOWS'}
    keys = ['decision_minute','horizon','exit_policy']
    masks = lambda x: (x[keys] == pd.Series({k:selected[k] for k in keys})).all(axis=1)
    train = primary.loc[masks(primary) & (pd.to_datetime(primary.date).dt.year <= 2023)].sort_values('date').iloc[:-2]
    test = shadow.loc[masks(shadow) & (pd.to_datetime(shadow.date).dt.year >= 2024)].sort_values('date')
    if test.empty:return {'status':'NO_ELIGIBLE_INTERPOLATED_WINDOWS'}
    forecast = predict_profit(train,test,specs[selected['feature_set']],selected['model'])
    side = choose_side(forecast,selected['cushion_pct'])
    return {'status':'HINDSIGHT_INTERPOLATION_SENSITIVITY_ONLY','metrics':metrics(test,side),
            'stress_10bps':metrics(test,side,10),'filled_minutes':int(test.imputed_minutes.sum()),
            'note':'Different, previously excluded dates; not an improvement estimate on the observed cohort. Future-bracketed prices cannot establish executable fills or alpha.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pair', choices=list(PAIRS), required=True)
    p.add_argument('--mode', choices=['archive', 'evaluate'], required=True)
    args = p.parse_args()
    name = args.pair
    url, secret = required_env('SUPABASE_URL'), required_env('SUPABASE_SECRET_KEY')
    archive = SupabaseArchive(url, secret, os.getenv('SUPABASE_BUCKET', 'market-edge-history'))
    if args.mode == 'archive':
        for first, last in month_windows(START, END):
            if load_pair(archive, name, first) is None:
                bars = download_pair(required_env('ALPACA_KEY_ID'), required_env('ALPACA_SECRET_KEY'), PAIRS[name], first, last)
                save_pair(archive, name, first, bars)
            print(f'{name} {first:%Y-%m}: monthly archive ready', flush=True)
        return
    cal = xcals.get_calendar('XNYS', start=START, end=END)
    closes = {pd.Timestamp(day).date(): row['close'] for day, row in cal.schedule.iterrows()}
    data, shadow, coverage = prepare(archive, name, closes)
    control, control_shadow, _ = prepare(archive, 'nasdaq3', closes) if name != 'nasdaq3' else (data.copy(), shadow.copy(), coverage)
    macro = fetch_fred_market_daily()
    if not data.empty and not control.empty:
        data = append_previous_day_macro(data, macro).dropna(subset=list(MACRO_FEATURES))
        control = append_previous_day_macro(control, macro).dropna(subset=list(MACRO_FEATURES))
        data, control = match_control(data, control)
        data, control = eligible_policies(data, control)
    if not shadow.empty:shadow = append_previous_day_macro(shadow, macro).dropna(subset=list(MACRO_FEATURES))
    if not control_shadow.empty:control_shadow = append_previous_day_macro(control_shadow, macro).dropna(subset=list(MACRO_FEATURES))
    run_id = str(uuid.uuid4())
    pair = PAIRS[name]
    specs = {'price': {'columns': list(PRICE_FEATURES), 'macro_weight': 0.},
             'price_macro': {'columns': [*PRICE_FEATURES, *MACRO_FEATURES], 'macro_weight': 1.}}
    summary = {'model_type': 'leveraged_etf_universe_v2_observed_windows', 'pair': name,
               'instruments': asdict(pair), 'go_no_go': 'NO_VALIDATED_EDGE'}
    leaderboard = []
    snapshots = {}
    total = 0
    if enough_data(data) and enough_data(control):
        comparisons = [('candidate_native_proxy', data)]
        if name != 'nasdaq3':
            comparisons.append(('nasdaq3_matched_control', control))
        for label, frame in comparisons:
            result = walk_forward_search(frame, specs)
            rank = result.pop('ranking')
            shadow_frame = shadow if label == 'candidate_native_proxy' else control_shadow
            result['interpolation_sensitivity'] = sensitivity_report(frame, shadow_frame, result['selected'], specs)
            for report in result['reports'].values():
                for old, new in [('always_tqqq_same_window', 'always_bull_same_window'),
                                 ('always_sqqq_same_window', 'always_bear_same_window'),
                                 ('qqq_direction_accuracy_on_trades', 'proxy_direction_accuracy_on_trades')]:
                    if old in report:
                        report[new] = report.pop(old)
            total += len(rank)
            summary[label] = result
            leaderboard.extend(json.loads(rank.head(50).assign(comparison=label).to_json(orient='records')))
            for suffix, payload in [('features.csv.gz', gzip.compress(frame.to_csv(index=False).encode(), mtime=0)),
                                    ('interpolation-sensitivity.csv.gz', gzip.compress(shadow_frame.to_csv(index=False).encode(), mtime=0)),
                                    ('all-candidates.json.gz', gzip.compress(rank.to_json(orient='records').encode(), mtime=0))]:
                key = f'research/universe-v2/{run_id}/{label}/{suffix}'
                response = archive.session.post(archive._url(key), headers={**archive._headers(), 'Content-Type': 'application/gzip'}, data=payload, timeout=90)
                if not response.ok:
                    raise RuntimeError(f'Private universe snapshot HTTP {response.status_code}')
                snapshots[key] = hashlib.sha256(payload).hexdigest()
        summary['status'] = 'COMPLETED_HISTORICAL_DIAGNOSTIC'
    else:
        summary['status'] = 'INSUFFICIENT_COMPLETE_MINUTE_DATA'
    diagnostics = {'no_live_orders': True, 'allocation_percent': 10, 'slippage_bps_per_side': [5, 10],
        'coverage': coverage, 'matched_sessions': int(data.date.nunique()) if not data.empty else 0,
        'snapshots_sha256': snapshots, 'max_configurations_per_comparison': 288,
        'imputation_policy':'Primary observed windows only. Maximum 2 internal minutes per ETF interpolated for frozen-model sensitivity only. Entry/exit/features never interpolated.',
        'selection_budget':'Eight predeclared pairs; maximum 4320 fits/configurations including matched controls; future expansion requires a separately registered batch.',
        'minimum_sessions': '100 per year 2019-2025, 60 in 2026',
        'selection': '2021/2022/2023 expanding windows only; two-session embargo',
        'limitations': ['Different pairs have different coverage; compare each with its own matched-date Nasdaq control, not a cross-pair hindsight winner',
            'All 2024-2026 results are retrospective; future prospective testing required',
            'Same 10% capital allocation is not equal volatility risk across markets or leverage levels',
            'QQQ/TQQQ/SQQQ column names in internal snapshots are aliases for the explicit instrument mapping; every fill uses real pair prices',
            'Minute-bar target touches are hypothetical fills; quotes/liquidity checks still needed', pair.note]}
    body = {'run_id': run_id, 'code_sha': os.getenv('GITHUB_SHA', 'manual'), 'research_start': str(START), 'research_end': str(END),
            'candidate_count': max(1, total), 'summary': summary, 'leaderboard': leaderboard, 'diagnostics': {**diagnostics, 'actual_candidates_tested': total,
            'candidate_count_field_note': 'Database requires a positive count; insufficient-data reports use sentinel 1 with actual_candidates_tested=0'}}
    send_private_report(url, secret, json.loads(json.dumps(body, allow_nan=False, default=lambda x: x.item() if hasattr(x, 'item') else str(x))))
    print(f'{name}: universe report stored privately; no orders.', flush=True)


if __name__ == '__main__':
    main()
