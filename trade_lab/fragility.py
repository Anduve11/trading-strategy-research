"""Predeclared falsification diagnostics, never selection or new alpha claims."""
import numpy as np
import pandas as pd
from .sizing_research import size_metrics
from .edge_research import block_bootstrap_interval


def position_returns(frame,sides,cost=10):
    sides=np.asarray(sides)
    return np.where(sides==1,frame[f'tqqq_net_{cost}bps_pct'],np.where(sides==-1,frame[f'sqqq_net_{cost}bps_pct'],0.))/100


def diagnostics(frame,sides,allocation,repetitions=1000):
    sides=np.asarray(sides,dtype=int)
    baseline=size_metrics(frame,sides,allocation,10)
    r=position_returns(frame,sides)
    positive=np.flatnonzero((sides!=0)&(r>0))
    ordered=positive[np.argsort(-r[positive])]
    removed={}
    for n in (1,3,5):
        altered=sides.copy();altered[ordered[:n]]=0
        removed[str(n)]={'removed_winners':min(n,len(ordered)),**size_metrics(frame,altered,allocation,10)}
    delayed={}
    for n in (1,2):
        altered=np.r_[np.zeros(min(n,len(sides)),dtype=int),sides[:-n]] if len(sides)>n else np.zeros(len(sides),dtype=int)
        delayed[str(n)]=size_metrics(frame,altered,allocation,10)
    rng=np.random.default_rng(71)
    missing={}
    for fraction in (.10,.25):
        keep=rng.random((repetitions,len(sides)))>=fraction
        trials=np.prod(1+allocation*r[None,:]*keep,axis=1)-1
        q=np.quantile(100*trials,[.05,.5,.95])
        missing[str(fraction)]={'return_pct_p05_median_p95':q.tolist(),'probability_negative_return':float(np.mean(trials<0))}
    placebo=None
    if len(frame)>20:
        offsets=rng.integers(1,len(sides),size=repetitions)
        rotated=np.stack([np.roll(sides,int(k)) for k in offsets])
        bull=frame.tqqq_net_10bps_pct.to_numpy()/100;bear=frame.sqqq_net_10bps_pct.to_numpy()/100
        hypothetical=np.where(rotated==1,bull[None,:],np.where(rotated==-1,bear[None,:],0.))
        returns=100*(np.prod(1+allocation*hypothetical,axis=1)-1)
        placebo={'return_pct_p05_median_p95':np.quantile(returns,[.05,.5,.95]).tolist(),
          'fraction_at_least_observed':float(np.mean(returns>=baseline['return_pct'])),
          'note':'Descriptive circular-shift comparison, not a valid post-selection significance test.'}
    quarters=pd.to_datetime(frame.date).dt.to_period('Q')
    return {'baseline_10bps':baseline,'stress_20bps':size_metrics(frame,sides,allocation,20),
      'skip_best_winning_sessions':removed,'signal_delay_eligible_observations':delayed,
      'random_missing_trades':missing,'circular_shift_placebo':placebo,
      'top3_share_of_positive_position_returns':float(r[ordered[:3]].sum()/r[positive].sum()) if len(positive) else None,
      'long_only':size_metrics(frame,np.where(sides==1,1,0),allocation,10),
      'inverse_only':size_metrics(frame,np.where(sides==-1,-1,0),allocation,10),
      'mean_daily_account_return_95pct_unadjusted':block_bootstrap_interval(allocation*r),
      'quarters':{str(q):size_metrics(frame.loc[quarters==q],sides[quarters==q],allocation,10) for q in sorted(quarters.unique())}}


def run_fragility(frame,strategies):
    years=pd.to_datetime(frame.date).dt.year
    reports={}
    for name,sides in strategies.items():
        reports[name]={}
        for period,mask in [('inspected_2024',years==2024),('inspected_2025_2026',years>=2025)]:
            reports[name][period]={}
            for size in (.1,.5,1.):
                reports[name][period][str(size)]=diagnostics(frame.loc[mask],np.asarray(sides)[mask],size)
    return reports
