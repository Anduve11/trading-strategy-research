"""Signals use QQQ bars completed at time t; trades enter next bar open."""
import numpy as np
import pandas as pd
from .data import ET

STRATEGIES = ['Momentum + VWAP', 'Opening range breakout', 'EMA trend', 'VWAP reversion']


def calculate_signals(bars: pd.DataFrame, strategy: str, momentum_threshold: float = 0.0015, deviation_threshold: float = 0.0025) -> pd.DataFrame:
    qqq = bars.loc[bars['symbol'].eq('QQQ')].sort_values('timestamp').copy()
    qqq['local_ts'] = qqq['timestamp'].dt.tz_convert(ET)
    qqq['day'] = qqq['local_ts'].dt.date
    qqq['hhmm'] = qqq['local_ts'].dt.strftime('%H:%M')
    g = qqq.groupby('day', sort=False)
    typical = (qqq['high'] + qqq['low'] + qqq['close'])/3
    qqq['_pv'] = typical * qqq['volume']
    qqq['vwap'] = qqq.groupby('day')['_pv'].cumsum() / qqq.groupby('day')['volume'].cumsum().replace(0, np.nan)
    qqq['ret_5'] = g['close'].pct_change(5, fill_method=None)
    qqq['prev_close'] = g['close'].shift(1)
    qqq['ema9'] = g['close'].transform(lambda s: s.ewm(span=9, adjust=False).mean())
    qqq['ema21'] = g['close'].transform(lambda s: s.ewm(span=21, adjust=False).mean())
    qqq['signal'] = 0
    allowed = (qqq['hhmm'] >= '09:50') & (qqq['hhmm'] <= '14:30')
    if strategy == 'Momentum + VWAP':
        buy = (qqq['ret_5'] > momentum_threshold) & (qqq['close'] > qqq['vwap'])
        sell = (qqq['ret_5'] < -momentum_threshold) & (qqq['close'] < qqq['vwap'])
    elif strategy == 'Opening range breakout':
        opening = qqq[qqq['hhmm'].between('09:30','09:44')]
        ranges = opening.groupby('day').agg(rhi=('high','max'), rlo=('low','min'), nbars=('close','size'))
        qqq = qqq.join(ranges, on='day')
        buy = (qqq['close'] > qqq['rhi']) & (qqq['nbars'] >= 15)
        sell = (qqq['close'] < qqq['rlo']) & (qqq['nbars'] >= 15)
    elif strategy == 'EMA trend':
        buy = (qqq['ema9'] > qqq['ema21']*1.0002) & (qqq['close'] > qqq['vwap'])
        sell = (qqq['ema9'] < qqq['ema21']*.9998) & (qqq['close'] < qqq['vwap'])
    elif strategy == 'VWAP reversion':
        offset = qqq['close']/qqq['vwap'] - 1
        buy = (offset < -deviation_threshold) & (qqq['close'] > qqq['prev_close'])
        sell = (offset > deviation_threshold) & (qqq['close'] < qqq['prev_close'])
    else:
        raise ValueError(f'Unknown strategy: {strategy}')
    qqq.loc[allowed & buy, 'signal'] = 1
    qqq.loc[allowed & sell, 'signal'] = -1
    return qqq[['timestamp', 'day', 'signal', 'close', 'vwap']].reset_index(drop=True)
