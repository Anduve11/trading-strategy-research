"""Pre-entry signal records for a frozen, unvalidated paper-only candidate."""
import numpy as np
import pandas as pd
from .research_factory import stable_hash

MANIFEST={'strategy_version':'volume_reversal_forward_v1','threshold':.75,'volume_shock_min':.25,
    'range_split':.5,'daily_vol_floor':.001,'allocation':1.,'entry_delays_minutes':[0,5],
    'exit':'last regular-session minute close','cost_bps_per_side':[10,20,50],
    'deadline_minutes_before_open':5,'vendor_daily_finality_buffer_minutes':90,
    'pairs':['semiconductors','semiconductors2','smallcap','nasdaq3'],
    'status':'UNVALIDATED_PAPER_CANDIDATE_NO_ORDERS'}


def target_session(schedule,now):
    now=pd.Timestamp(now)
    if now.tzinfo is None:raise ValueError('Aware creation timestamp required')
    eligible=schedule.loc[schedule.open>now+pd.Timedelta(minutes=5)]
    if eligible.empty:raise ValueError('No upcoming session in schedule')
    target=eligible.index[0];pos=schedule.index.get_loc(target)
    if pos<60:raise ValueError('Insufficient scheduled history')
    prior=schedule.index[pos-1]
    # A retrospective vendor daily bar may include trades beyond the regular
    # close. Wait until the full prior NY date plus a finality buffer has passed.
    prior_date=pd.Timestamp(prior).date()
    final_after=(pd.Timestamp(prior_date).tz_localize('America/New_York')+
                 pd.DateOffset(days=1)+pd.Timedelta(minutes=90)).tz_convert('UTC')
    return target,prior,schedule.index[pos-60:pos],final_after


def validate_proxy(raw,symbol,expected_dates):
    if raw.empty:raise ValueError('No proxy history')
    x=raw.copy();x['timestamp']=pd.to_datetime(x.timestamp,utc=True,errors='raise')
    x['date']=x.timestamp.dt.tz_convert('America/New_York').dt.date
    if set(x.symbol)!={symbol} or x.date.duplicated().any():raise ValueError('Proxy identity/duplicates')
    if set(x.date)!=set(expected_dates):raise ValueError('Proxy must contain every required completed session, and no others')
    columns=['open','high','low','close','volume'];x[columns]=x[columns].apply(pd.to_numeric,errors='raise')
    if not np.isfinite(x[columns].to_numpy()).all() or (x[['open','high','low','close']]<=0).any().any() or (x.volume<0).any():
        raise ValueError('Invalid proxy values')
    if (x.high<x[['open','low','close']].max(axis=1)).any() or (x.low>x[['open','high','close']].min(axis=1)).any():
        raise ValueError('Invalid proxy OHLC')
    return x.sort_values('date').reset_index(drop=True)


def freeze_signal(raw,pair_name,pair,schedule,now,code_sha):
    now=pd.Timestamp(now);target,prior,history,final_after=target_session(schedule,now)
    if now<final_after:raise ValueError('Prior vendor daily bar is not yet eligible as finalized')
    opening=schedule.loc[target,'open'];closing=schedule.loc[target,'close']
    expected=[pd.Timestamp(d).date() for d in history]
    x=validate_proxy(raw,pair.proxy,expected)
    close=x.close;volume=x.volume
    daily_return=float(close.iloc[-1]/close.iloc[-2]-1)
    daily_vol=float(np.log(close/close.shift(1)).tail(20).std(ddof=1))
    scale=max(.001,daily_vol)
    shock=float(volume.iloc[-1]/volume.tail(20).mean()-1) if volume.tail(20).mean()>0 else None
    width=float(close.tail(20).max()-close.tail(20).min())
    location=float((close.iloc[-1]-close.tail(20).min())/width) if width>0 else None
    side=0
    if shock is not None and location is not None and shock>.25:
        if daily_return<-.75*scale and location<.5:side=1
        elif daily_return>.75*scale and location>.5:side=-1
    identity={'strategy_version':MANIFEST['strategy_version'],'pair':pair_name,'target_session':str(pd.Timestamp(target).date())}
    return {'prediction_id':stable_hash(identity),**identity,'created_at':now.tz_convert('UTC').isoformat(),
      'code_sha':code_sha,'manifest':MANIFEST,'manifest_sha256':stable_hash(MANIFEST),
      'target_open':opening.isoformat(),'target_close':closing.isoformat(),
      'source_last_session':str(pd.Timestamp(prior).date()),'source_final_after':final_after.isoformat(),
      'side':side,'symbol':pair.bull if side==1 else pair.bear if side==-1 else None,
      'lagged_features':{'prior_return_1':daily_return,'prior_daily_vol20':daily_vol,
                         'prior_volume_shock':shock,'prior_close_range_position':location},
      'allocation_fraction':1. if side else 0.,'signal_status':'SIGNAL' if side else 'CASH',
      'no_live_orders':True,'no_capital_moved':True,
      'note':'Frozen before entry. A future observed-bar return is a hypothetical fill, not an executed trade.'}


def reconcile_signal(record,raw):
    from .execution_refinement import validate_minutes
    opening,closing=pd.Timestamp(record['target_open']),pd.Timestamp(record['target_close'])
    created=pd.Timestamp(record['created_at'])
    if created>=opening-pd.Timedelta(minutes=5):raise ValueError('Prediction was not recorded before its deadline')
    if record['manifest_sha256']!=stable_hash(record['manifest']):raise ValueError('Signal manifest checksum mismatch')
    if not record['side']:return {'status':'CASH','prediction_id':record['prediction_id'],'returns':{},'no_live_orders':True}
    bars=validate_minutes(raw,{record['symbol']},opening,closing).set_index('timestamp')
    last=closing-pd.Timedelta(minutes=1)
    required=[opening+pd.Timedelta(minutes=d) for d in record['manifest']['entry_delays_minutes']]+[last]
    if not set(required).issubset(bars.index):
        return {'status':'MISSING_EXACT_ENDPOINTS','prediction_id':record['prediction_id'],
                'missing':[t.isoformat() for t in required if t not in bars.index],'no_live_orders':True}
    returns={}
    for delay in record['manifest']['entry_delays_minutes']:
        entry=opening+pd.Timedelta(minutes=delay)
        returns[str(delay)]={str(cost):float(100*(bars.loc[last,'close']*(1-cost/10000)/
              (bars.loc[entry,'open']*(1+cost/10000))-1)) for cost in record['manifest']['cost_bps_per_side']}
    return {'status':'OBSERVED_ENDPOINTS_HYPOTHETICAL_FILL','prediction_id':record['prediction_id'],
            'returns':returns,'no_live_orders':True,'note':'Same-vendor minute endpoints, unverified quotes and size impact.'}
