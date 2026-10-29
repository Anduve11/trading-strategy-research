"""Conservatively lagged daily cross-asset market observations from FRED.

Credit spreads can be published after their observation date. We wait two
business days for ALL three sources. This is still not verified first-seen data.
"""
from io import StringIO
import hashlib
import numpy as np
import pandas as pd

SERIES = ('DEXUSEU', 'DCOILWTICO', 'BAMLH0A0HYM2')
CROSS_FEATURES = ('usd_eur_change5', 'oil_change5', 'credit_spread', 'credit_change5')


def covered_features(frame, minimum=.95):
    """Keep fully covered source groups without discarding unrelated sources."""
    if not 0 < minimum <= 1 or frame.empty:
        raise ValueError('Invalid coverage sample/threshold')
    groups = {'currency': ('usd_eur_change5',), 'oil': ('oil_change5',),
              'credit': ('credit_spread', 'credit_change5')}
    included, excluded = [], {}
    for name, columns in groups.items():
        coverage = float(frame[list(columns)].notna().all(axis=1).mean())
        if coverage >= minimum:
            included.extend(columns)
        else:
            excluded[name] = {'coverage': coverage, 'reason': 'Below predeclared 95% historical coverage requirement'}
    return included, excluded


def fetch_cross_asset(session=None):
    import requests
    session = session or requests.Session()
    result, checksums = None, {}
    for series in SERIES:
        response = session.get('https://fred.stlouisfed.org/graph/fredgraph.csv',
                               params={'id': series, 'cosd': '2018-01-01', 'coed': '2026-09-30'}, timeout=60)
        if not response.ok:
            raise RuntimeError(f'FRED cross-asset {series} HTTP {response.status_code}')
        if len(response.content) > 4_000_000:
            raise ValueError('Cross-asset CSV unexpectedly large')
        checksums[series] = hashlib.sha256(response.content).hexdigest()
        x = pd.read_csv(StringIO(response.text))
        date_col = 'observation_date' if 'observation_date' in x else 'DATE'
        if date_col not in x or series not in x:
            raise ValueError('Unexpected cross-asset CSV schema')
        x = x[[date_col, series]].rename(columns={date_col: 'date'})
        x['date'] = pd.to_datetime(x.date, errors='raise')
        x[series] = pd.to_numeric(x[series], errors='coerce')
        if x.date.duplicated().any():
            raise ValueError('Duplicate cross-asset dates')
        result = x if result is None else result.merge(x, on='date', how='outer', validate='one_to_one')
    return result.sort_values('date').reset_index(drop=True), checksums


def append_cross_asset(decisions, history):
    out = decisions.copy()
    out['_trade_date'] = pd.to_datetime(out.date)
    columns = {}
    # Each series gets its OWN observation clock, not a shared forward-fill date.
    for series in SERIES:
        source = history[['date', series]].dropna().sort_values('date').copy()
        source['date'] = pd.to_datetime(source.date)
        if source.date.duplicated().any():
            raise ValueError('Duplicate cross-asset observations')
        if series == 'DEXUSEU':
            source['usd_eur_change5'] = source[series] / source[series].shift(5) - 1
            features = ['usd_eur_change5']
        elif series == 'DCOILWTICO':
            # Oil futures/spot can reach zero or negative: use scaled differences,
            # not percent division by zero during the April 2020 dislocation.
            source['oil_change5'] = (source[series] - source[series].shift(5)) / source[series].shift(5).abs().clip(lower=10.)
            features = ['oil_change5']
        else:
            source['credit_spread'] = source[series]
            source['credit_change5'] = source[series] - source[series].shift(5)
            features = ['credit_spread', 'credit_change5']
        source['_observed'] = source.date
        source['_available'] = source.date + pd.offsets.BDay(2)
        out = pd.merge_asof(out.sort_values('_trade_date'), source[['_observed', '_available', *features]],
                            left_on='_trade_date', right_on='_available', direction='backward')
        age = (out._trade_date - out._observed).dt.days
        out.loc[age.isna() | (age > 14), features] = np.nan
        out = out.drop(columns=['_observed', '_available'])
        columns[series] = features
    return out.drop(columns='_trade_date')
