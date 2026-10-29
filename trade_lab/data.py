"""Timestamp-aware bar import and explicitly synthetic demo data."""
import numpy as np
import pandas as pd

REQUIRED = {'timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume'}
ET = 'America/New_York'


def validate_bars(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = [str(x).strip().lower() for x in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}')
    df = df[list(REQUIRED)].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
    if df['timestamp'].isna().any():
        raise ValueError('Invalid timestamp; use ISO timestamps with UTC offsets.')
    df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
    for col in ['open','high','low','close','volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    if df[['open','high','low','close','volume']].isna().any().any():
        raise ValueError('Invalid price or volume value.')
    if not set(['QQQ','TQQQ','SQQQ']).issubset(set(df['symbol'])):
        raise ValueError('Input must include QQQ, TQQQ, and SQQQ. Individual ETF fills are not approximated from QQQ.')
    if (df[['open','high','low','close']] <= 0).any().any() or (df['volume'] < 0).any():
        raise ValueError('Prices must be positive and volume nonnegative.')
    if (df['high'] < df[['open','low','close']].max(axis=1)).any() or (df['low'] > df[['open','high','close']].min(axis=1)).any():
        raise ValueError('OHLC values are inconsistent (high/low bounds).')
    if df.duplicated(['timestamp','symbol']).any():
        raise ValueError('Duplicate timestamp/symbol rows found.')
    local = df['timestamp'].dt.tz_convert(ET)
    t = local.dt.time
    df = df.loc[(t >= pd.Timestamp('09:30').time()) & (t < pd.Timestamp('16:00').time())].copy()
    df = df.sort_values(['timestamp','symbol']).reset_index(drop=True)
    if df.empty:
        raise ValueError('No regular-hours data (9:30 AM to 4:00 PM Eastern).')
    return df


def generate_synthetic(days: int = 65, seed: int = 73) -> pd.DataFrame:
    """Deterministic FAKE three-symbol bars for functional testing ONLY.

    NOT calibrated to real returns, execution, fees, or market patterns.
    """
    if not 2 <= days <= 200:
        raise ValueError('days must be between 2 and 200')
    rng = np.random.default_rng(seed)
    sessions = pd.bdate_range('2026-03-02', periods=days, tz=ET)
    rows = []
    prices = {'QQQ': 500., 'TQQQ': 60., 'SQQQ': 35.}
    for d in sessions:
        drift = rng.normal(0, 0.000045)
        vol = rng.uniform(0.00025, 0.0009)
        for i in range(390):
            ts = d + pd.Timedelta(hours=9, minutes=30+i)
            shock = rng.normal(drift, vol)
            for sym, mult in [('QQQ',1),('TQQQ',3),('SQQQ',-3)]:
                op = prices[sym]
                noise = rng.normal(0, vol*0.18) if sym != 'QQQ' else 0
                close = max(.01, op*(1 + mult*shock + noise))
                wiggle = abs(rng.normal(0, vol*abs(mult)*0.32))
                high = max(op, close)*(1+wiggle)
                low = min(op, close)*(1-wiggle)
                rows.append((ts.tz_convert('UTC'), sym, op, high, low, close, int(rng.integers(500,4500))))
                prices[sym] = close
    return validate_bars(pd.DataFrame(rows, columns=['timestamp','symbol','open','high','low','close','volume']))
