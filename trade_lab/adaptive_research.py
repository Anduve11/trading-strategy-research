"""Quarterly causal refits and cost-aware model agreement; no orders."""
import numpy as np
import pandas as pd
from .edge_research import predict_profit,choose_side,metrics,account_daily,block_bootstrap_interval

CALENDAR=('weekday_known','month_end_distance','quarter_end_distance')


def append_calendar(frame,sessions):
    dates=pd.DatetimeIndex(sessions).tz_localize(None).normalize()
    daily=pd.DataFrame({'date':dates})
    daily['month_last']=daily.date.groupby(daily.date.dt.to_period('M')).transform('max')
    daily['quarter_last']=daily.date.groupby(daily.date.dt.to_period('Q')).transform('max')
    # Dates of scheduled closes are known ahead; no realized prices are used.
    daily['weekday_known']=daily.date.dt.weekday
    daily['month_end_distance']=(daily.month_last-daily.date).dt.days
    daily['quarter_end_distance']=(daily.quarter_last-daily.date).dt.days
    daily['date']=daily.date.dt.date
    return frame.merge(daily[['date',*CALENDAR]],on='date',validate='one_to_one')


def quarterly_forecasts(data,spec,window):
    """Train through quarter boundary minus two sessions, targeting 10bps costs.

    Returns both independently fitted model forecasts; no evaluation-quarter
    labels enter fitting, scaling, clipping or selection.
    """
    if window not in ('expanding','rolling504'):raise ValueError('Unknown fit window')
    data=data.sort_values('date').reset_index(drop=True)
    periods=pd.to_datetime(data.date).dt.to_period('Q')
    pieces=[];forecasts=[]
    for quarter in sorted(periods.unique()):
        if quarter.year<2021:continue
        test=data.loc[periods==quarter]
        train=data.loc[data.date<test.date.min()].iloc[:-2].copy()
        if window=='rolling504':train=train.tail(504)
        if len(train)<250:continue
        # Existing predictor reads *_5bps targets: replace TRAIN targets only
        # with actual 10bps outcomes; retain original test outcomes for reports.
        for side in ('tqqq','sqqq'):
            y=train[f'{side}_net_10bps_pct']
            train[f'{side}_net_5bps_pct']=y.clip(y.quantile(.01),y.quantile(.99))
        ridge=predict_profit(train,test,spec,'ridge')
        trees=predict_profit(train,test,spec,'extra_trees')
        pieces.append(test);forecasts.append(np.stack([ridge,trees],axis=1))
    if not pieces:raise ValueError('No eligible quarterly forecasts')
    return pd.concat(pieces,ignore_index=True),np.concatenate(forecasts)


def select_sides(forecasts,cushion,mode):
    if mode=='ensemble':return choose_side(forecasts.mean(axis=1),cushion)
    if mode=='agreement':
        a=choose_side(forecasts[:,0],cushion);b=choose_side(forecasts[:,1],cushion)
        return np.where(a==b,a,0)
    raise ValueError('Unknown agreement mode')


def adaptive_search(data,specs):
    rankings=[];saved={}
    for feature_set,spec in specs.items():
        for window in ('expanding','rolling504'):
            frame,forecasts=quarterly_forecasts(data,spec,window)
            years=pd.to_datetime(frame.date).dt.year
            dev=frame.loc[years<=2023]
            for mode in ('ensemble','agreement'):
                for cushion in (0.,.10,.20):
                    sides=select_sides(forecasts,cushion,mode)
                    dev_side=sides[years<=2023]
                    m=metrics(dev,dev_side,10)
                    folds=[];counts=[]
                    for year in (2021,2022,2023):
                        mask=pd.to_datetime(dev.date).dt.year.eq(year)
                        met=metrics(dev.loc[mask],dev_side[mask],10)
                        folds.append(met['return_pct']);counts.append(met['trades'])
                    eligible=m['trades']>=75 and min(counts)>=10
                    score=float(np.mean(folds)-.75*np.std(folds)-.5*abs(m['max_drawdown_pct'])) if eligible else -1e6
                    key=(feature_set,window,mode,cushion)
                    saved[key]=(frame,sides)
                    rankings.append(dict(feature_set=feature_set,window=window,mode=mode,cushion=cushion,
                        eligible=bool(eligible),score=score,dev_return_10bps_pct=m['return_pct'],
                        dev_trades=m['trades'],fold_returns=folds,fold_trades=counts))
    ranking=pd.DataFrame(rankings).sort_values(['score','dev_return_10bps_pct'],ascending=False).reset_index(drop=True)
    eligible=ranking.loc[ranking.eligible]
    if eligible.empty:return {'selected':None,'reports':{},'ranking':ranking,'go_no_go':'NO_VALIDATED_EDGE'}
    leader=eligible.iloc[0]
    selected={k:leader[k] for k in ('feature_set','window','mode','cushion')}
    frame,sides=saved[(leader.feature_set,leader.window,leader['mode'],leader.cushion)]
    years=pd.to_datetime(frame.date).dt.year
    reports={}
    for name,mask in [('development_2021_2023',years<=2023),('inspected_2024',years==2024),('inspected_2025_2026',years>=2025)]:
        part=frame.loc[mask];choices=sides[mask]
        reports[name]={'primary_10bps':metrics(part,choices,10),'stress_20bps':metrics(part,choices,20),
          'always_bull_10bps':metrics(part,np.ones(len(part),dtype=int),10),
          'always_bear_10bps':metrics(part,-np.ones(len(part),dtype=int),10),
          'cash_return_pct':0.,'mean_daily_account_return_95pct_unadjusted':block_bootstrap_interval(account_daily(part,choices,10))}
    return {'selected':selected,'reports':reports,'ranking':ranking,'go_no_go':'NO_VALIDATED_EDGE'}
