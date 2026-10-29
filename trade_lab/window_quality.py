"""Observed execution windows plus explicitly hindsight-based gap sensitivity.

Interpolation is never used for features, training, selection or primary
returns. Future-bracketed interpolated OHLC points are NOT tradable evidence.
"""
import numpy as np
import pandas as pd
from .edge_research import HORIZONS, EXITS, simulate_window


def execution_window(prices, entry, horizon, interpolate=False):
    index = pd.date_range(entry, periods=horizon, freq='min')
    if index[0].tz_convert('America/New_York').date() != index[-1].tz_convert('America/New_York').date():
        raise ValueError('Cross-session execution window')
    if prices.index.duplicated().any():
        raise ValueError('Duplicate execution timestamps')
    x = prices.reindex(index).copy()
    columns = ['open','high','low','close','volume']
    missing = x[columns].isna().any(axis=1)
    count = int(missing.sum())
    if not count:
        return x, 0
    # Only small bounded gaps, no imputed entry, exit, entire session or
    # bridging overnight. Missing high/low on existing rows is also rejected.
    if not interpolate or count > 2 or missing.iloc[0] or missing.iloc[-1]:
        return None, count
    if x.loc[missing, columns].notna().any().any():
        return None, count
    filled = x.close.interpolate(method='linear', limit_area='inside')
    for col in ('open','high','low','close'):
        x.loc[missing, col] = filled.loc[missing]
    x.loc[missing, 'volume'] = 0
    return x, count


def window_outcomes(bars, decisions):
    """Return primary observed rows and separate interpolated-only rows."""
    prices = {s: x.set_index('timestamp').sort_index() for s, x in bars.groupby('symbol')}
    observed, shadow = [], []
    counts = {'observed_windows': 0, 'interpolated_only_windows': 0, 'rejected_windows': 0}
    for _, decision in decisions.iterrows():
        entry = decision.timestamp + pd.Timedelta(minutes=1)
        for horizon in HORIZONS:
            windows = {}; imputed = 0
            for sym in ('TQQQ','SQQQ'):
                x, n = execution_window(prices[sym], entry, horizon, interpolate=True)
                if x is None:
                    windows = {}; break
                windows[sym] = x
                imputed += n
            if not windows:
                counts['rejected_windows'] += 1
                continue
            key = 'interpolated_only_windows' if imputed else 'observed_windows'
            counts[key] += 1
            for policy in EXITS:
                row = decision.to_dict()
                row.update(horizon=horizon, exit_policy=policy.name, imputed_minutes=imputed,
                           data_quality='INTERPOLATION_SENSITIVITY_ONLY' if imputed else 'OBSERVED')
                for sym, side in (('TQQQ','tqqq'), ('SQQQ','sqqq')):
                    for cost in (5,10):
                        value, ambiguous = simulate_window(windows[sym], entry, horizon, policy, cost)
                        row[f'{side}_net_{cost}bps_pct'] = value
                        if cost == 5:row[f'{side}_ambiguous'] = int(ambiguous)
                (shadow if imputed else observed).append(row)
    return pd.DataFrame(observed), pd.DataFrame(shadow), counts
