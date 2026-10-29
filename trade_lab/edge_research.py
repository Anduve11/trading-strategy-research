"""Bounded, cost-aware hypotheses; historical diagnostics, never live orders.

Select on expanding-window 2021/2022/2023 predictions only. All 2024+ data
is already inspected at project level. Features must be known before entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import hashlib
import numpy as np
import pandas as pd

from .data import ET

DECISION_MINUTES = ('09:59', '10:59', '14:29')
HORIZONS = (30, 60)
PRICE_FEATURES = (
    'gap', 'gap_scaled', 'return_so_far', 'return_5', 'return_15',
    'acceleration', 'range_so_far', 'range_position', 'vwap_gap',
    'path_efficiency', 'volume_ratio', 'gap_reversal',
    'prior_return_1', 'prior_return_5', 'prior_return_20',
    'prior_vol_20', 'prior_sma50_gap', 'prior_close_range_position',
)
OPTION_FEATURES = ('prior_vix9d_vix', 'prior_vvix', 'prior_vvix_change5',
                   'implied_realized_ratio')


@dataclass(frozen=True)
class ExitPolicy:
    name: str
    target_pct: float | None
    stop_pct: float | None


# Explicit research budget: no post-result additions to this batch.
EXITS = (
    ExitPolicy('time_only', None, None),
    ExitPolicy('tp025_sl025', .25, .25),
    ExitPolicy('tp050_sl050', .50, .50),
    ExitPolicy('tp075_sl050', .75, .50),
)


def complete_session(group: pd.DataFrame) -> bool:
    """Require exact matching minute grids, not just 390 rows per ETF."""
    if group.duplicated(['symbol', 'timestamp']).any():
        return False
    symbols = set(group.symbol)
    if not {'QQQ', 'TQQQ', 'SQQQ'}.issubset(symbols):
        return False
    day = group.timestamp.iloc[0].tz_convert(ET).normalize()
    expected = pd.date_range(day + pd.Timedelta(hours=9, minutes=30), periods=390,
                             freq='min').tz_convert('UTC')
    return all(pd.DatetimeIndex(group.loc[group.symbol.eq(s), 'timestamp']).sort_values().equals(expected)
               for s in ('QQQ', 'TQQQ', 'SQQQ'))


def extract_decisions(bars: pd.DataFrame, history: list[dict] | None = None, session_closes=None):
    """One row/day/decision, with completed-bar features and separate QQQ labels.

    A 09:59 bar completes at 10:00 ET; enter the 10:00 open. The 30-minute
    label ends at the 10:29 close. No post-entry prices enter PRICE_FEATURES.
    Known official session closes, including half-days, enter lag history even
    if a missing intraday bar makes that day ineligible for new trades.
    """
    prior = list(history or [])
    rows, excluded = [], 0
    days = bars.timestamp.dt.tz_convert(ET).dt.date
    for day, whole in bars.groupby(days, sort=True):
        q = whole.loc[whole.symbol.eq('QQQ')].sort_values('timestamp')
        qminutes = q.timestamp.dt.tz_convert(ET).dt.strftime('%H:%M')
        expected_close = ((pd.Timestamp(day).tz_localize(ET) + pd.Timedelta(hours=16)).tz_convert('UTC')
                          if session_closes is None else session_closes.get(day))
        last_minute = None if expected_close is None else pd.Timestamp(expected_close) - pd.Timedelta(minutes=1)
        close_known = last_minute is not None and not q.timestamp.duplicated().any() and last_minute in set(q.timestamp)
        if not close_known:
            prior = []
            excluded += 1
            continue
        q = q.reset_index(drop=True)
        grid_ok = complete_session(whole)
        excluded += int(not grid_ok)
        if grid_ok and len(prior) >= 51:
            closes = np.array([x['close'] for x in prior])
            rv = float(np.std(np.diff(np.log(closes[-21:])), ddof=1))
            for minute in DECISION_MINUTES:
                hh, mm = map(int, minute.split(':'))
                pos = hh * 60 + mm - (9 * 60 + 30)
                early = q.iloc[:pos + 1]
                close = float(early.iloc[-1].close)
                opening = float(q.iloc[0].open)
                volume = float(early.volume.sum())
                vhist = [x['volumes'][minute] for x in prior[-20:] if x['volumes'][minute] > 0]
                if len(vhist) < 15 or volume <= 0:
                    continue
                hi, lo = float(early.high.max()), float(early.low.min())
                vwap = float(((early.high + early.low + early.close) / 3 * early.volume).sum() / volume)
                log_path = np.r_[np.log(opening), np.log(early.close.to_numpy())]
                path = float(np.abs(np.diff(log_path)).sum())
                gap = opening / closes[-1] - 1
                ret5 = close / float(q.iloc[pos - 5].close) - 1
                before5 = float(q.iloc[pos - 5].close / q.iloc[pos - 10].close - 1)
                lag_hi = max(x['close'] for x in prior[-20:])
                lag_lo = min(x['close'] for x in prior[-20:])
                row = {'date': day, 'timestamp': q.iloc[pos].timestamp,
                       'decision_minute': minute, 'gap': gap,
                       'gap_scaled': gap / max(rv, 1e-6),
                       'return_so_far': close / opening - 1, 'return_5': ret5,
                       'return_15': close / float(q.iloc[pos - 15].close) - 1,
                       'acceleration': ret5 - before5, 'range_so_far': hi / lo - 1,
                       'range_position': (close - lo) / max(hi - lo, 1e-9),
                       'vwap_gap': close / vwap - 1,
                       'path_efficiency': float((np.log(close / opening)) / max(path, 1e-9)),
                       'volume_ratio': volume / np.mean(vhist) - 1,
                       'gap_reversal': gap * (close / opening - 1),
                       'prior_return_1': closes[-1] / closes[-2] - 1,
                       'prior_return_5': closes[-1] / closes[-6] - 1,
                       'prior_return_20': closes[-1] / closes[-21] - 1,
                       'prior_vol_20': rv * np.sqrt(252),
                       'prior_sma50_gap': closes[-1] / closes[-50:].mean() - 1,
                       'prior_close_range_position': (closes[-1] - lag_lo) / max(lag_hi - lag_lo, 1e-9)}
                for horizon in HORIZONS:
                    row[f'qqq_forward_{horizon}m_pct'] = float(
                        100 * (q.iloc[pos + horizon].close / q.iloc[pos + 1].open - 1))
                rows.append(row)
        prior.append({'close': float(q.loc[q.timestamp.eq(last_minute), 'close'].iloc[0]), 'high': float(q.high.max()),
                      'low': float(q.low.min()),
                      'volumes': {minute: (float(q.loc[qminutes.to_numpy() <= minute, 'volume'].sum())
                                           if int((qminutes <= minute).sum()) == (int(minute[:2]) * 60 + int(minute[3:]) - 570 + 1) else 0.)
                                  for minute in DECISION_MINUTES}})
        prior = prior[-65:]
    return pd.DataFrame(rows), prior, excluded


def simulate_window(prices: pd.DataFrame, entry_ts, horizon: int, policy: ExitPolicy,
                    slippage_bps=5.) -> tuple[float, bool]:
    """Long ETF return in percent. Stop-first ambiguity; gap-through-stop loss.

    End-of-window exit is a hypothetical market-on-time fill at last bar close.
    A touched target does not guarantee a real limit fill; cost stress is required.
    """
    if horizon <= 0 or slippage_bps < 0 or not np.isfinite(slippage_bps):
        raise ValueError('Invalid horizon/cost')
    if (policy.target_pct is None) != (policy.stop_pct is None):
        raise ValueError('Both target and stop must be set or absent')
    if policy.target_pct is not None and min(policy.target_pct, policy.stop_pct) <= 0:
        raise ValueError('Targets/stops must be positive')
    index = pd.date_range(pd.Timestamp(entry_ts), periods=horizon, freq='min')
    if not index.isin(prices.index).all() or prices.index.duplicated().any():
        raise ValueError('Incomplete execution window')
    x = prices.loc[index]
    slip = slippage_bps / 10000
    entry = float(x.iloc[0].open) * (1 + slip)
    exit_raw, ambiguous = float(x.iloc[-1].close), False
    if policy.target_pct is not None:
        stop, target = entry * (1 - policy.stop_pct / 100), entry * (1 + policy.target_pct / 100)
        stops = x.low.to_numpy() <= stop
        targets = x.high.to_numpy() >= target
        hits = np.flatnonzero(stops | targets)
        if len(hits):
            i = int(hits[0])
            if stops[i]:
                ambiguous = bool(targets[i])
                exit_raw = min(float(x.iloc[i].open), stop) if i else stop
            else:
                exit_raw = target
    return float(100 * (exit_raw * (1 - slip) / entry - 1)), ambiguous


def add_outcomes(bars: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """Cache both ETF outcomes for each predeclared horizon and exit policy."""
    if decisions.empty:
        return pd.DataFrame()
    prices = {s: x.set_index('timestamp').sort_index() for s, x in bars.groupby('symbol')}
    rows = []
    for _, decision in decisions.iterrows():
        entry = decision.timestamp + pd.Timedelta(minutes=1)
        for horizon in HORIZONS:
            for policy in EXITS:
                row = decision.to_dict()
                row.update(horizon=horizon, exit_policy=policy.name)
                for sym, side in (('TQQQ', 'tqqq'), ('SQQQ', 'sqqq')):
                    for cost in (5, 10):
                        value, ambiguous = simulate_window(prices[sym], entry, horizon, policy, cost)
                        row[f'{side}_net_{cost}bps_pct'] = value
                        if cost == 5:
                            row[f'{side}_ambiguous'] = int(ambiguous)
                rows.append(row)
    return pd.DataFrame(rows)


def fetch_option_history(session=None):
    """Official Cboe daily CSVs, latest history; not archived first-seen vintages."""
    import requests
    session = session or requests.Session()
    merged, checksums = None, {}
    for index in ('VIX', 'VIX9D', 'VVIX'):
        url = f'https://cdn-api.cboe.com/api/global/us_indices/daily_prices/{index}_History.csv'
        response = session.get(url, timeout=60)
        if not response.ok:
            raise RuntimeError(f'Cboe {index} source HTTP {response.status_code}')
        if len(response.content) > 4_000_000:
            raise ValueError('Cboe file unexpectedly large')
        checksums[index] = hashlib.sha256(response.content).hexdigest()
        frame = pd.read_csv(StringIO(response.text))
        frame.columns = frame.columns.str.strip().str.upper()
        value = 'CLOSE' if 'CLOSE' in frame else index
        if 'DATE' not in frame or value not in frame:
            raise ValueError(f'Unexpected Cboe {index} schema')
        frame = frame[['DATE', value]].rename(columns={'DATE': 'date', value: index})
        frame['date'] = pd.to_datetime(frame.date, format='%m/%d/%Y', errors='raise')
        frame[index] = pd.to_numeric(frame[index], errors='raise')
        if frame.date.duplicated().any() or (frame[index] <= 0).any():
            raise ValueError('Invalid Cboe observations')
        merged = frame if merged is None else merged.merge(frame, on='date', how='outer', validate='one_to_one')
    return merged.sort_values('date').reset_index(drop=True), checksums


def append_option_features(decisions, market, max_age_days=7):
    """Use last complete Cboe date strictly before trade date, with stale limit."""
    right = market.copy().sort_values('date').dropna(subset=['VIX', 'VIX9D', 'VVIX'])
    right['date'] = pd.to_datetime(right.date)
    if right.date.duplicated().any():
        raise ValueError('Duplicate option source date')
    right['prior_vix9d_vix'] = right.VIX9D / right.VIX
    right['prior_vvix'] = right.VVIX
    right['prior_vvix_change5'] = right.VVIX / right.VVIX.shift(5) - 1
    right = right.rename(columns={'date': '_option_date', 'VIX': '_option_vix'})
    left = decisions.copy()
    left['_trade_date'] = pd.to_datetime(left.date)
    out = pd.merge_asof(left.sort_values('_trade_date'),
                        right[['_option_date', '_option_vix', *OPTION_FEATURES[:3]]],
                        left_on='_trade_date', right_on='_option_date',
                        allow_exact_matches=False, direction='backward')
    out['implied_realized_ratio'] = out._option_vix / (100 * out.prior_vol_20.clip(lower=.01))
    age = (out._trade_date - out._option_date).dt.days
    out.loc[age.isna() | (age > max_age_days), list(OPTION_FEATURES)] = np.nan
    return out.drop(columns=['_trade_date', '_option_date', '_option_vix'])


def feature_specs(macro_columns, options_available=False):
    # Group scaling AFTER standardization changes ridge's relative shrinkage:
    # .5 gives macro a stronger penalty; 2 gives it a weaker penalty.
    specs = {'price': {'columns': list(PRICE_FEATURES), 'macro_weight': 0.}}
    for weight in (.5, 1., 2.):
        specs[f'price_macro_w{weight:g}'] = {
            'columns': [*PRICE_FEATURES, *macro_columns], 'macro_weight': weight}
    if options_available:
        specs['price_macro_options'] = {
            'columns': [*PRICE_FEATURES, *macro_columns, *OPTION_FEATURES], 'macro_weight': 1.}
    return specs


def make_model(name):
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import ExtraTreesRegressor
    if name == 'ridge':
        return Ridge(alpha=100.)
    if name == 'extra_trees':
        return ExtraTreesRegressor(n_estimators=60, max_depth=4, min_samples_leaf=35,
                                   max_features=.7, random_state=47, n_jobs=1)
    raise ValueError('Unknown model')


def predict_profit(train, test, spec, model_name):
    """Fit expected NET ETF returns, not accuracy on an unrelated label."""
    from sklearn.preprocessing import StandardScaler
    columns = spec['columns']
    if len(train) < 250 or train.date.max() >= test.date.min():
        raise ValueError('Insufficient or overlapping training/test dates')
    if not np.isfinite(train[columns].to_numpy(dtype=float)).all() or not np.isfinite(test[columns].to_numpy(dtype=float)).all():
        raise ValueError('Nonfinite features')
    scaler = StandardScaler().fit(train[columns])
    a, b = scaler.transform(train[columns]), scaler.transform(test[columns])
    weights = np.array([1. if c in PRICE_FEATURES else spec['macro_weight'] for c in columns])
    model = make_model(model_name)
    y = train[['tqqq_net_5bps_pct', 'sqqq_net_5bps_pct']].to_numpy()
    if not np.isfinite(y).all():
        raise ValueError('Nonfinite training outcomes')
    model.fit(a * weights, y)
    return model.predict(b * weights)


def choose_side(predictions, cushion_pct):
    """Trade only when predicted post-cost position return clears cushion."""
    p = np.asarray(predictions, dtype=float)
    if p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(p).all() or cushion_pct < 0:
        raise ValueError('Invalid profit forecasts/cushion')
    best = p.argmax(axis=1)
    # Ties abstain, rather than always resolving in favor of TQQQ.
    return np.where((p.max(axis=1) > cushion_pct) & (p[:, 0] != p[:, 1]),
                    np.where(best == 0, 1, -1), 0)


def account_daily(frame, sides, cost=5):
    sides = np.asarray(sides)
    if len(sides) != len(frame) or not set(sides).issubset({-1, 0, 1}):
        raise ValueError('Invalid directions')
    if frame.date.duplicated().any() or not frame.date.is_monotonic_increasing:
        raise ValueError('Require one chronological decision per session')
    values = np.where(sides == 1, frame[f'tqqq_net_{cost}bps_pct'],
                      np.where(sides == -1, frame[f'sqqq_net_{cost}bps_pct'], 0.))
    if not np.isfinite(values).all() or (values <= -100).any():
        raise ValueError('Invalid realized return')
    # 10% account allocation; returns below are decimal account returns.
    return values * .001


def metrics(frame, sides, cost=5):
    r = account_daily(frame, sides, cost)
    equity = np.r_[1., np.cumprod(1 + r)]
    traded = np.asarray(sides) != 0
    return {'return_pct': float(100 * (equity[-1] - 1)),
            'max_drawdown_pct': float(100 * np.min(equity / np.maximum.accumulate(equity) - 1)),
            'trades': int(traded.sum()), 'sessions': len(frame),
            'win_rate_pct': float(100 * np.mean(r[traded] > 0)) if traded.any() else 0.,
            'mean_position_net_pct': float(1000 * np.mean(r[traded])) if traded.any() else 0.,
            'exposure_session_pct': float(100 * traded.mean()) if len(traded) else 0.}


def block_bootstrap_interval(daily, repetitions=1000, block_size=5):
    """Unadjusted 95% interval for mean daily account return, percentage points.

    Includes cash days; not adjusted for selecting the best of many tests.
    """
    x = np.asarray(daily, dtype=float)
    if len(x) < 20:
        return None
    rng = np.random.default_rng(47)
    starts = rng.integers(0, len(x), size=(repetitions, int(np.ceil(len(x) / block_size))))
    indexes = ((starts[:, :, None] + np.arange(block_size)) % len(x)).reshape(repetitions, -1)[:, :len(x)]
    lo, hi = np.quantile(100 * x[indexes].mean(axis=1), [.025, .975])
    return [float(lo), float(hi)]


def walk_forward_search(data, specs, model_names=('ridge', 'extra_trees'),
                        cushions=(0., .05, .10), min_trades=75):
    """No 2024+ observation affects ranking, scaling, fitting or selection."""
    results, predictions = [], {}
    for policy, raw in data.groupby(['decision_minute', 'horizon', 'exit_policy'], sort=True):
        raw = raw.sort_values('date').reset_index(drop=True)
        for spec_name, spec in specs.items():
            columns = spec['columns']
            # All specs must be compared on the SAME dates by the caller.
            if raw[columns].isna().any().any():
                raise ValueError('Feature groups must use matched, nonmissing sessions')
            for model_name in model_names:
                # Scaling features has no effect on a tree's splits: don't
                # count macro reweightings as three distinct tree hypotheses.
                if model_name == 'extra_trees' and spec_name in ('price_macro_w0.5', 'price_macro_w2'):
                    continue
                pieces, forecasts = [], []
                for year in (2021, 2022, 2023):
                    years = pd.to_datetime(raw.date).dt.year
                    train = raw.loc[years < year]
                    test = raw.loc[years == year]
                    # Remove last two TRAIN sessions as a conservative embargo.
                    train = train.iloc[:-2]
                    if len(test) < 100:
                        raise ValueError(f'Too few evaluation sessions in {year}')
                    pp = predict_profit(train, test, spec, model_name)
                    pieces.append(test)
                    forecasts.append(pp)
                dev = pd.concat(pieces, ignore_index=True)
                pp = np.concatenate(forecasts)
                key = (policy, spec_name, model_name)
                predictions[key] = (dev, pp)
                for cushion in cushions:
                    sides = choose_side(pp, cushion)
                    base = metrics(dev, sides)
                    stress = metrics(dev, sides, cost=10)
                    year_returns = [metrics(dev.loc[pd.to_datetime(dev.date).dt.year.eq(y)],
                                            sides[pd.to_datetime(dev.date).dt.year.eq(y)])['return_pct']
                                    for y in (2021, 2022, 2023)]
                    per_year_trades = [int(np.count_nonzero(sides[pd.to_datetime(dev.date).dt.year.eq(y)]))
                                       for y in (2021, 2022, 2023)]
                    eligible = base['trades'] >= min_trades and min(per_year_trades) >= 10
                    score = float(np.mean(year_returns) - .75 * np.std(year_returns)
                                  - .5 * abs(base['max_drawdown_pct'])) if eligible else -1e6
                    results.append({'decision_minute': policy[0], 'horizon': int(policy[1]),
                                    'exit_policy': policy[2], 'feature_set': spec_name,
                                    'model': model_name, 'cushion_pct': cushion,
                                    'eligible': bool(eligible), 'score': score,
                                    'dev_return_pct': base['return_pct'],
                                    'dev_max_drawdown_pct': base['max_drawdown_pct'],
                                    'dev_trades': base['trades'], 'dev_stress_return_pct': stress['return_pct'],
                                    'fold_returns_pct': year_returns, 'fold_trades': per_year_trades})
    ranking = pd.DataFrame(results).sort_values(['score', 'dev_return_pct'], ascending=False).reset_index(drop=True)
    if ranking.empty:
        raise ValueError('No research candidates')
    qualified = ranking.loc[ranking.eligible]
    if qualified.empty:
        return {'selected': None, 'ranking': ranking, 'reports': {}, 'go_no_go': 'NO_VALIDATED_EDGE'}
    leader = qualified.iloc[0]
    policy = (str(leader.decision_minute), int(leader.horizon), str(leader.exit_policy))
    selected = {k: leader[k] for k in ('decision_minute', 'horizon', 'exit_policy', 'feature_set', 'model', 'cushion_pct')}
    raw = data.loc[(data.decision_minute == policy[0]) & (data.horizon == policy[1]) & (data.exit_policy == policy[2])].sort_values('date')
    dev, pp = predictions[(policy, str(leader.feature_set), str(leader.model))]
    reports = {'development_walk_forward_2021_2023': metrics(dev, choose_side(pp, leader.cushion_pct))}
    train = raw.loc[pd.to_datetime(raw.date).dt.year <= 2023].iloc[:-2]
    for name, years in (('inspected_2024', (2024,)), ('inspected_2025_2026', (2025, 2026))):
        test = raw.loc[pd.to_datetime(raw.date).dt.year.isin(years)]
        if test.empty:
            continue
        forecasts = predict_profit(train, test, specs[str(leader.feature_set)], str(leader.model))
        sides = choose_side(forecasts, float(leader.cushion_pct))
        base = metrics(test, sides)
        reports[name] = {**base, 'stress_10bps': metrics(test, sides, cost=10),
                         'always_tqqq_same_window': metrics(test, np.ones(len(test), dtype=int)),
                         'always_sqqq_same_window': metrics(test, -np.ones(len(test), dtype=int)),
                         'cash_return_pct': 0.,
                         'mean_daily_account_return_95pct_unadjusted': block_bootstrap_interval(account_daily(test, sides)),
                         'qqq_direction_accuracy_on_trades': float(np.mean(
                             np.sign(test[f'qqq_forward_{policy[1]}m_pct'].to_numpy())[sides != 0] == sides[sides != 0])) if (sides != 0).any() else None,
                         'annual': {str(y): metrics(test.loc[pd.to_datetime(test.date).dt.year.eq(y)],
                                                   sides[pd.to_datetime(test.date).dt.year.eq(y)])
                                    for y in years}}
    return {'selected': selected, 'ranking': ranking, 'reports': reports,
            'go_no_go': 'NO_VALIDATED_EDGE'}
