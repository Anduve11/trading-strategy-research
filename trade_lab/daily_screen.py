"""Predeclared daily-bar screen. All predictors lagged; no invented prices.

Vendor daily open/close are hypothetical fills, not verified auction prices.
This experiment does not infer intraday stop or target paths from daily OHLC.
"""
import time
import numpy as np
import pandas as pd
from .etf_universe import PAIRS, Pair

UNIVERSE = {**PAIRS,
    'sp500_2':Pair('SPY','SSO','SDS',2),
    'dow2':Pair('DIA','DDM','DXD',2),
    'dow3':Pair('DIA','UDOW','SDOW',3),
    'smallcap2':Pair('IWM','UWM','TWM',2),
    'financials2':Pair('XLF','UYG','SKF',2,'XLF is a sector proxy, not asserted to track the exact fund benchmark.'),
    'realestate2':Pair('IYR','URE','SRS',2),
    'semiconductors2':Pair('SOXX','USD','SSG',2,'SOXX is an imperfect semiconductor sector proxy.'),
    'gold2':Pair('GLD','UGL','GLL',2,'GLD spot-backed proxy differs from futures-based fund exposure.'),
    'treasury2':Pair('TLT','UBT','TBT',2),
    'treasury3':Pair('TLT','TMF','TMV',3),
}
FEATURES = ('prior_return_1','prior_return_5','prior_return_20','prior_vol_20',
            'prior_sma50_gap','prior_close_range_position')


def validate_daily(raw,pair):
    x=raw.copy()
    expected={pair.proxy,pair.bull,pair.bear}
    if x.empty or set(x.symbol)!=expected:raise ValueError('Missing/unexpected daily tickers')
    x['timestamp']=pd.to_datetime(x.timestamp,utc=True,errors='raise')
    x['date']=x.timestamp.dt.tz_convert('America/New_York').dt.date
    cols=['open','high','low','close','volume']
    x[cols]=x[cols].apply(pd.to_numeric,errors='raise')
    if not np.isfinite(x[cols].to_numpy()).all():raise ValueError('Nonfinite daily data')
    if (x[['open','high','low','close']]<=0).any().any() or (x.volume<0).any():raise ValueError('Invalid daily values')
    if (x.high<x[['open','low','close']].max(axis=1)).any() or (x.low>x[['open','high','close']].min(axis=1)).any():raise ValueError('Invalid daily OHLC')
    if x.duplicated(['symbol','date']).any():raise ValueError('Duplicate daily ticker/date')
    if x.date.min()<pd.Timestamp('2018-01-01').date() or x.date.max()>pd.Timestamp('2026-09-30').date():raise ValueError('Daily dates outside frozen period')
    return x.sort_values(['date','symbol']).reset_index(drop=True)


def download_daily(pair,key,secret,session=None):
    import requests
    session=session or requests.Session()
    params={'symbols':','.join((pair.proxy,pair.bull,pair.bear)),'timeframe':'1Day',
      'start':'2018-01-01T05:00:00Z','end':'2026-10-01T04:00:00Z','feed':'sip','adjustment':'split','limit':10000,'sort':'asc'}
    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
    rows=[];seen=set()
    for _ in range(10):
        for retry in range(5):
            response=session.get('https://data.alpaca.markets/v2/stocks/bars',params=params,headers=headers,timeout=60)
            if response.status_code not in (429,500,502,503,504):break
            time.sleep(min(20,2**retry))
        if not response.ok:raise RuntimeError(f'Daily data HTTP {response.status_code}')
        payload=response.json()
        for symbol,bars in payload.get('bars',{}).items():
            for b in bars:rows.append(dict(timestamp=b['t'],symbol=symbol,open=b['o'],high=b['h'],low=b['l'],close=b['c'],volume=b['v']))
        token=payload.get('next_page_token')
        if not token:break
        if token in seen:raise ValueError('Repeated daily pagination token')
        seen.add(token);params['page_token']=token;time.sleep(.6)
    else:raise ValueError('Daily pagination safety limit')
    return validate_daily(pd.DataFrame(rows),pair)


def build_daily(raw,pair,sessions):
    raw=validate_daily(raw,pair)
    index=pd.Index([pd.Timestamp(d).date() for d in sessions],name='date')
    tables={s:x.set_index('date').reindex(index) for s,x in raw.groupby('symbol')}
    q=tables[pair.proxy]
    close=q.close
    lag=close.shift(1)
    out=pd.DataFrame(index=index)
    for n in (1,5,20):out[f'prior_return_{n}']=close.pct_change(n,fill_method=None).shift(1)
    out['prior_vol_20']=np.log(close/close.shift(1)).rolling(20,min_periods=20).std().shift(1)*np.sqrt(252)
    out['prior_sma50_gap']=lag/close.rolling(50,min_periods=50).mean().shift(1)-1
    hi=close.rolling(20,min_periods=20).max().shift(1)
    lo=close.rolling(20,min_periods=20).min().shift(1)
    out['prior_close_range_position']=(lag-lo)/(hi-lo).replace(0,np.nan)
    out['qqq_forward_390m_pct']=100*(q.close/q.open-1)
    for sym,side in ((pair.bull,'tqqq'),(pair.bear,'sqqq')):
        p=tables[sym]
        for cost in (5,10,20):out[f'{side}_net_{cost}bps_pct']=100*(p.close*(1-cost/10000)/(p.open*(1+cost/10000))-1)
    out=out.replace([np.inf,-np.inf],np.nan).dropna().reset_index()
    out=out.loc[(pd.to_datetime(out.date).dt.year>=2019)].copy()
    out['decision_minute']='09:29';out['horizon']=390;out['exit_policy']='vendor_daily_open_close'
    return out
