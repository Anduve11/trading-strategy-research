"""Historical daily market-condition observations, not revised economic releases.

Models use ONLY last available OBSERVATION dated before the trade day.
FRED CSV values are a retrospective convenience, NOT a point-in-time
vintage archive. Never treat revised CPI/NFP releases as real-time features.
"""
from __future__ import annotations
from datetime import date
from io import StringIO
import pandas as pd
import numpy as np
import requests

SERIES=('VIXCLS','DGS10','DGS2')
MACRO_FEATURES=('prior_vix','prior_vix_change5','prior_10y_yield','prior_2y_yield','prior_10y_2y_spread','prior_10y_change5')


def fetch_fred_market_daily(start='2018-01-01',end='2026-09-30',session=None)->pd.DataFrame:
    """Public FRED graph CSV (not a guaranteed stable authenticated API)."""
    sess=session or requests.Session()
    tables=[]
    for series in SERIES:
        response=sess.get('https://fred.stlouisfed.org/graph/fredgraph.csv',
                          params={'id':series,'cosd':start,'coed':end},timeout=40)
        if not response.ok:raise RuntimeError(f'FRED {series} history failed HTTP {response.status_code}')
        if len(response.content)>4_000_000:raise RuntimeError('Unexpectedly large FRED CSV')
        df=pd.read_csv(StringIO(response.text))
        date_col='observation_date' if 'observation_date' in df.columns else 'DATE'
        if date_col not in df or series not in df:raise ValueError(f'FRED data missing {series}')
        df=df[[date_col,series]].rename(columns={date_col:'date'})
        df['date']=pd.to_datetime(df.date,errors='raise').dt.date
        df[series]=pd.to_numeric(df[series],errors='coerce')
        tables.append(df)
    base=tables[0]
    for table in tables[1:]:base=base.merge(table,on='date',how='outer',validate='one_to_one')
    base=base.sort_values('date').reset_index(drop=True)
    if base['date'].duplicated().any():raise ValueError('Duplicate FRED observations')
    if base['VIXCLS'].notna().sum()<500:raise ValueError('Too few daily VIX observations')
    return base


def append_previous_day_macro(decisions:pd.DataFrame,market:pd.DataFrame,max_staleness_days=7)->pd.DataFrame:
    """Strictly backward as-of join: current-day data is NEVER exposed.

    Uses the last non-null market observation dated earlier than trade day.
    Daily market-close observations are not inflation/CPI employment releases.
    """
    if not 1<=max_staleness_days<=14:raise ValueError('Invalid maximum staleness')
    x=market.copy()
    if not {'date',*SERIES}.issubset(x.columns):raise ValueError('Missing market macro series')
    x['date']=pd.to_datetime(x.date).dt.date
    x=x.sort_values('date').drop_duplicates('date')
    x[list(SERIES)]=x[list(SERIES)].apply(pd.to_numeric,errors='coerce').ffill(limit=5)
    # Five prior non-NaN trading observations for each series.
    x['vix_change5']=x['VIXCLS']/x['VIXCLS'].ffill().shift(5)-1
    x['10y_change5']=x['DGS10']-x['DGS10'].ffill().shift(5)
    # At any given decision, only measurements strictly BEFORE that date count.
    daily=x[['date',*SERIES,'vix_change5','10y_change5']].copy()
    d=decisions.copy()
    d['_trade_date']=pd.to_datetime(d.date)
    daily['_obs_date']=pd.to_datetime(daily.date)
    daily=daily.sort_values('_obs_date').drop(columns='date')
    d=d.sort_values('_trade_date')
    joined=pd.merge_asof(d,daily,left_on='_trade_date',right_on='_obs_date',
                         direction='backward',allow_exact_matches=False)
    age=(joined._trade_date-joined._obs_date).dt.days
    stale=age.isna()|(age>max_staleness_days)
    out=joined.drop(columns=['_trade_date','_obs_date']).copy()
    out['prior_vix']=out.pop('VIXCLS')
    out['prior_vix_change5']=out.pop('vix_change5')
    out['prior_10y_yield']=out.pop('DGS10')
    out['prior_2y_yield']=out.pop('DGS2')
    out['prior_10y_2y_spread']=out.prior_10y_yield-out.prior_2y_yield
    out['prior_10y_change5']=out.pop('10y_change5')
    out.loc[stale,list(MACRO_FEATURES)]=np.nan
    return out