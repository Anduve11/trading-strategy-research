"""PREVIOUS-SESSION ONLY regime classification: avoids hindsight leakage.

These descriptors are experimental research features, not profitable signals.
"""
from __future__ import annotations
from collections.abc import Sequence
import numpy as np
import pandas as pd
from .data import ET


def classify_sessions(bars: pd.DataFrame, prior_closes: Sequence[float] = ()) -> tuple[pd.DataFrame, list[float]]:
    """Classify each trading date using only QQQ closes strictly BEFORE that date.

    - Trend compares prior day's close with trailing 50-day SMA (±1% neutral band).
    - Annualized 20-day realized volatility uses 20 returns from prior 21 closes.
    - Threshold 25% is predeclared, never selected using holdout performance.
    Returns a per-day table and the last 60 completed QQQ daily closes.
    """
    frame = bars.loc[bars['symbol'].eq('QQQ'), ['timestamp', 'close']].copy()
    frame['date'] = frame['timestamp'].dt.tz_convert(ET).dt.date
    daily = frame.sort_values('timestamp').groupby('date', sort=True)['close'].last()
    closes = [float(x) for x in prior_closes]
    rows=[]
    for day, day_close in daily.items():
        if len(closes) < 50:
            trend, volatility, vol_value, regime = 'Unknown', 'Unknown', float('nan'), 'Insufficient history'
        else:
            sma50 = float(np.mean(closes[-50:]))
            relative = closes[-1]/sma50 - 1
            trend = 'Uptrend' if relative > 0.01 else ('Downtrend' if relative < -0.01 else 'Sideways')
            returns = np.diff(np.log(np.array(closes[-21:], dtype=float)))
            vol_value = float(np.std(returns, ddof=1)*np.sqrt(252))
            volatility = 'High volatility' if vol_value >= .25 else 'Normal volatility'
            regime = trend + ' / ' + volatility
        rows.append({'date':day,'trend':trend,'volatility':volatility,'vol20_annualized':vol_value,'regime':regime})
        closes.append(float(day_close))
        closes = closes[-60:]
    return pd.DataFrame(rows), closes


def summarize_regime_trades(trades: pd.DataFrame) -> pd.DataFrame:
    cols=['candidate','period','regime','trades','win_rate','avg_trade_return_pct','pnl_dollars']
    if trades.empty:
        return pd.DataFrame(columns=cols)
    grouped = trades.groupby(['candidate','period','regime'], dropna=False, observed=True)
    rows = []
    for (candidate, period, regime), sub in grouped:
        rows.append({'candidate':candidate,'period':period,'regime':regime,'trades':len(sub),
                     'win_rate':100*float((sub['pnl_dollars']>0).mean()),
                     'avg_trade_return_pct':float(sub['net_return_pct'].mean()),
                     'pnl_dollars':float(sub['pnl_dollars'].sum())})
    return pd.DataFrame(rows, columns=cols).sort_values(['candidate','period','regime']).reset_index(drop=True)