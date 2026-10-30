"""Lagged cross-market context and distinct daily/overnight outcomes.

No current/future session prices or volumes enter any predictor. Overnight
entry uses vendor close with features from the session BEFORE entry day.
"""
import numpy as np
import pandas as pd
from .daily_screen import build_daily,FEATURES,validate_daily

CONTEXT=('market_1','market_5','smallcap_relative_5','semis_relative_5',
         'tech_relative_5','bonds_5','gold_5','risk_disagreement')
BEHAVIOR=('prior_intraday','prior_overnight','prior_volume_shock','prior_close_location',
          'prior_efficiency20','prior_vol_ratio','prior_gap_reversal')


def context_features(proxy_bars,sessions):
    index=pd.Index([pd.Timestamp(x).date() for x in sessions],name='date')
    close=proxy_bars.pivot(index='date',columns='symbol',values='close').reindex(index)
    required=['QQQ','SPY','IWM','SOXX','TLT','GLD']
    if not set(required).issubset(close):raise ValueError('Missing cross-market proxy')
    r1=close.pct_change(1,fill_method=None).shift(1)
    r5=close.pct_change(5,fill_method=None).shift(1)
    result=pd.DataFrame(index=index)
    result['market_1']=r1.SPY;result['market_5']=r5.SPY
    result['smallcap_relative_5']=r5.IWM-r5.SPY
    result['semis_relative_5']=r5.SOXX-r5.QQQ
    result['tech_relative_5']=r5.QQQ-r5.SPY
    result['bonds_5']=r5.TLT;result['gold_5']=r5.GLD
    result['risk_disagreement']=np.sign(r1.IWM)*np.sign(r1.QQQ)
    return result.reset_index()


def build_experiment(raw,pair,sessions,context,interval):
    if interval not in ('day','overnight'):raise ValueError('Unknown interval')
    raw=validate_daily(raw,pair)
    base=build_daily(raw,pair,sessions)
    index=pd.Index([pd.Timestamp(d).date() for d in sessions],name='date')
    tables={s:x.set_index('date').reindex(index) for s,x in raw.groupby('symbol')}
    q=tables[pair.proxy];close=q.close
    additions=pd.DataFrame(index=index)
    additions['prior_intraday']=(q.close/q.open-1).shift(1)
    additions['prior_overnight']=(q.open/close.shift(1)-1).shift(1)
    additions['prior_volume_shock']=(q.volume/q.volume.rolling(20,min_periods=20).mean()-1).shift(1)
    additions['prior_close_location']=((q.close-q.low)/(q.high-q.low).replace(0,np.nan)).shift(1)
    returns=np.log(close/close.shift(1))
    additions['prior_efficiency20']=(np.log(close/close.shift(20))/returns.abs().rolling(20,min_periods=20).sum().replace(0,np.nan)).shift(1)
    additions['prior_vol_ratio']=(returns.rolling(5,min_periods=5).std()/returns.rolling(20,min_periods=20).std()).shift(1)
    additions['prior_gap_reversal']=((q.open/close.shift(1)-1)*(q.close/q.open-1)).shift(1)
    base=base.merge(additions.reset_index(),on='date',validate='one_to_one').merge(context,on='date',validate='one_to_one')
    if interval=='day':base['proxy_forward_return_pct']=base.qqq_forward_390m_pct
    else:
        labels=pd.DataFrame(index=index)
        labels['proxy_forward_return_pct']=100*(q.open.shift(-1)/q.close-1)
        for symbol,side in ((pair.bull,'tqqq'),(pair.bear,'sqqq')):
            p=tables[symbol]
            for cost in (5,10,20):labels[f'{side}_net_{cost}bps_pct']=100*(p.open.shift(-1)*(1-cost/10000)/(p.close*(1+cost/10000))-1)
        base=base.drop(columns=[c for c in labels if c in base]).merge(labels.reset_index(),on='date',validate='one_to_one')
    base['decision_minute']='PRIOR_SESSION_FEATURES'
    base['horizon']=1  # One interval, NOT one minute. Explicit label_column below.
    base['exit_policy']='vendor_daily_open_close' if interval=='day' else 'vendor_close_next_session_open'
    return base.replace([np.inf,-np.inf],np.nan).dropna().sort_values('date').reset_index(drop=True)
