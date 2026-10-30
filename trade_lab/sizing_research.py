"""Hypothetical capital sizing and predeclared simple-rule challengers."""
import numpy as np
import pandas as pd


def rule_sides(data):
    trend=(data.prior_return_20>0)&(data.prior_sma50_gap>0)
    down=(data.prior_return_20<0)&(data.prior_sma50_gap<0)
    momentum=np.where(trend,1,np.where(down,-1,0))
    sd=(data.prior_vol_20/np.sqrt(252)).clip(lower=.001)
    reversal=np.where(data.prior_return_1 < -sd,1,np.where(data.prior_return_1 > sd,-1,0))
    breakout=np.where(data.prior_close_range_position>=.95,1,np.where(data.prior_close_range_position<=.05,-1,0))
    regime=np.where(data.prior_efficiency20.abs()>=.3,momentum,reversal)
    return {'trend_bull_cash':np.where(trend,1,0),'two_way_momentum':momentum,
            'one_sigma_reversal':reversal,'close_range_breakout':breakout,'regime_switch':regime}


def size_metrics(data,sides,allocation,cost=10):
    sides=np.asarray(sides)
    allocation=np.broadcast_to(np.asarray(allocation,dtype=float),(len(data),))
    if len(sides)!=len(data) or not set(sides).issubset({-1,0,1}):raise ValueError('Invalid directions')
    if not np.isfinite(allocation).all() or (allocation<0).any() or (allocation>1).any():raise ValueError('Allocation must be in [0,1]')
    if data.date.duplicated().any() or not data.date.is_monotonic_increasing:raise ValueError('Require chronological unique dates')
    r=np.where(sides==1,data[f'tqqq_net_{cost}bps_pct'],np.where(sides==-1,data[f'sqqq_net_{cost}bps_pct'],0.))/100
    if not np.isfinite(r).all() or (r<=-1).any():raise ValueError('Invalid position returns')
    daily=r*allocation
    equity=np.r_[1.,np.cumprod(1+daily)]
    dd=equity/np.maximum.accumulate(equity)-1
    years=(pd.Timestamp(data.date.iloc[-1])-pd.Timestamp(data.date.iloc[0])).days/365.25 if len(data)>1 else 0
    return {'return_pct':float(100*(equity[-1]-1)),'cagr_pct':float(100*(equity[-1]**(1/years)-1)) if years>0 else None,
      'max_close_to_close_drawdown_pct':float(100*dd.min()),'active_sessions':int(((sides!=0)&(allocation>0)).sum()),
      'mean_capital_deployed_pct':float(100*np.mean(allocation*(sides!=0))) if len(data) else 0.,
      'ending_10000':float(10000*equity[-1]),'ending_100000':float(100000*equity[-1])}


def compare_sizing(data,incumbent_sides,leverage):
    rules=rule_sides(data);years=pd.to_datetime(data.date).dt.year
    rows=[]
    for name,sides in rules.items():
        folds=[];counts=[]
        for y in (2021,2022,2023):
            mask=years.eq(y);m=size_metrics(data.loc[mask],sides[mask],.1)
            folds.append(m['return_pct']);counts.append(m['active_sessions'])
        devmask=years.le(2023);dev=size_metrics(data.loc[devmask],sides[devmask],.1)
        eligible=sum(counts)>=75 and min(counts)>=10
        score=np.mean(folds)-.75*np.std(folds)-.5*abs(dev['max_close_to_close_drawdown_pct']) if eligible else -1e6
        rows.append({'rule':name,'score':float(score),'eligible':bool(eligible),'dev_return_pct':dev['return_pct'],'fold_returns':folds,'fold_active_sessions':counts})
    ranking=pd.DataFrame(rows).sort_values('score',ascending=False).reset_index(drop=True)
    eligible=ranking.loc[ranking.eligible]
    selected=str(eligible.iloc[0].rule) if len(eligible) else None
    strategies={'frozen_adaptive_incumbent':np.asarray(incumbent_sides),'always_bull':np.ones(len(data),dtype=int)}
    if selected:strategies['development_selected_rule']=rules[selected]
    allocations={'10_percent':.1,'25_percent':.25,'50_percent':.5,'100_percent':1.,
      'volatility_target_10pct_capped':np.minimum(1.,.10/(data.prior_vol_20.to_numpy()*leverage).clip(min=.05))}
    reports={}
    for period,mask in [('development_2021_2023',years.le(2023)),('inspected_2024',years.eq(2024)),('inspected_2025_2026',years.ge(2025))]:
        reports[period]={}
        for name,sides in strategies.items():
            reports[period][name]={}
            for label,allocation in allocations.items():
                alloc=allocation if np.isscalar(allocation) else allocation[mask]
                reports[period][name][label]={'primary_10bps':size_metrics(data.loc[mask],sides[mask],alloc,10),
                                             'stress_20bps':size_metrics(data.loc[mask],sides[mask],alloc,20)}
    return {'selected_rule':selected,'reports':reports,'ranking':ranking,'go_no_go':'NO_VALIDATED_EDGE'}
