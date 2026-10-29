"""Real-price leveraged ETF pairs. Aliases adapt the existing simulator only.

Never multiply QQQ returns to invent another ETF's performance. All persisted
raw bars retain real ticker identities. SOXX is a sector proxy, not the exact
current or historical index followed by SOXL/SOXS.
"""
from dataclasses import dataclass
from datetime import date
from io import BytesIO
import gzip
import time
import pandas as pd
from .data import validate_bars


@dataclass(frozen=True)
class Pair:
    proxy: str
    bull: str
    bear: str
    leverage: int
    note: str = ''


PAIRS = {
    'nasdaq3': Pair('QQQ', 'TQQQ', 'SQQQ', 3),
    'nasdaq2': Pair('QQQ', 'QLD', 'QID', 2),
    'sp500': Pair('SPY', 'UPRO', 'SPXU', 3),
    'smallcap': Pair('IWM', 'TNA', 'TZA', 3),
    'semiconductors': Pair('SOXX', 'SOXL', 'SOXS', 3,
        'SOXX is an imperfect sector proxy; fund and proxy benchmarks have changed historically.'),
    'technology': Pair('XLK', 'TECL', 'TECS', 3),
    'financials': Pair('XLF', 'FAS', 'FAZ', 3),
    'biotech': Pair('XBI', 'LABU', 'LABD', 3),
}


def aliases(bars, pair):
    symbols = {pair.proxy, pair.bull, pair.bear}
    if set(bars.symbol) != symbols:
        raise ValueError('Unexpected/missing ticker identity for pair')
    mapping = {pair.proxy: 'QQQ', pair.bull: 'TQQQ', pair.bear: 'SQQQ'}
    return validate_bars(bars.assign(symbol=bars.symbol.map(mapping)))


def validate_pair(bars, pair, month):
    normalized = aliases(bars, pair)
    days = normalized.timestamp.dt.tz_convert('America/New_York')
    if ((days.dt.year != month.year) | (days.dt.month != month.month)).any():
        raise ValueError('Pair data contains wrong month')
    inverse = {'QQQ': pair.proxy, 'TQQQ': pair.bull, 'SQQQ': pair.bear}
    return normalized.assign(symbol=normalized.symbol.map(inverse))


def cache_key(name, month):
    if name not in PAIRS:
        raise ValueError('Unknown pair')
    p = PAIRS[name]
    return f'alpaca/sip/split/1min/universe-v1/{name}/{p.proxy}-{p.bull}-{p.bear}/{month:%Y-%m}.csv.gz'


def load_pair(archive, name, month):
    if name == 'nasdaq3':
        return archive.load(month)
    response = archive.session.get(archive._url(cache_key(name, month)), headers=archive._headers(), timeout=45)
    if response.ok:
        if len(response.content) > 15_000_000:
            raise ValueError('Oversized universe archive')
        bars = pd.read_csv(BytesIO(gzip.decompress(response.content)))
        return validate_pair(bars, PAIRS[name], month)
    code, _ = archive._storage_error(response)
    if code == 'NoSuchKey':
        return None
    raise RuntimeError(f'Universe archive read HTTP {response.status_code}; code {code}')


def save_pair(archive, name, month, bars):
    checked = validate_pair(bars, PAIRS[name], month)
    payload = gzip.compress(checked.to_csv(index=False, float_format='%.10g').encode(), mtime=0)
    response = archive.session.post(archive._url(cache_key(name, month)),
        headers={**archive._headers(), 'Content-Type': 'application/gzip'}, data=payload, timeout=90)
    if not response.ok:
        code, _ = archive._storage_error(response)
        if code not in ('KeyAlreadyExists', 'ResourceAlreadyExists'):
            raise RuntimeError(f'Universe archive write HTTP {response.status_code}')


def download_pair(key, secret, pair, first, last, session=None, delay=.6):
    import requests
    session = session or requests.Session()
    start = pd.Timestamp(first).tz_localize('America/New_York').tz_convert('UTC')
    end = (pd.Timestamp(last) + pd.Timedelta(days=1)).tz_localize('America/New_York').tz_convert('UTC')
    params = {'symbols': ','.join((pair.proxy, pair.bull, pair.bear)), 'timeframe': '1Min',
              'start': start.isoformat(), 'end': end.isoformat(), 'feed': 'sip',
              'adjustment': 'split', 'sort': 'asc', 'limit': 10000}
    headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}
    rows, seen = [], set()
    for _ in range(60):
        for retry in range(5):
            response = session.get('https://data.alpaca.markets/v2/stocks/bars',
                                   params=params, headers=headers, timeout=60)
            if response.status_code not in (429, 500, 502, 503, 504):
                break
            time.sleep(min(20, 2 ** retry))
        if not response.ok:
            raise RuntimeError(f'Alpaca universe data HTTP {response.status_code}; no response body logged')
        payload = response.json()
        for symbol, bars in payload.get('bars', {}).items():
            for b in bars:
                rows.append({'timestamp': b['t'], 'symbol': symbol, 'open': b['o'],
                             'high': b['h'], 'low': b['l'], 'close': b['c'], 'volume': b['v']})
        token = payload.get('next_page_token')
        if not token:
            break
        if token in seen:
            raise RuntimeError('Repeated pagination token')
        seen.add(token)
        params['page_token'] = token
        time.sleep(delay)
    else:
        raise RuntimeError('Universe pagination safety limit reached')
    if not rows:
        raise ValueError('No historical bars for pair')
    return validate_pair(pd.DataFrame(rows), pair, first)


def match_control(candidate, control):
    """Keep exact common dates, decision clocks, horizons, exits, one-to-one."""
    keys = ['date', 'decision_minute', 'horizon', 'exit_policy']
    if candidate.duplicated(keys).any() or control.duplicated(keys).any():
        raise ValueError('Duplicate comparison keys')
    common = candidate[keys].merge(control[keys], on=keys, how='inner', validate='one_to_one')
    a = common.merge(candidate, on=keys, validate='one_to_one')
    b = common.merge(control, on=keys, validate='one_to_one')
    return a, b
