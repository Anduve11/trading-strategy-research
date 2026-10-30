"""Declared families and causal policy comparisons on immutable paper data."""
import hashlib
import json
import numpy as np
import pandas as pd
from .sizing_research import size_metrics

FAMILIES=('five_day_reversal','volume_reversal','market_relative_reversal',
          'trend_continuation','compression_breakout','cross_asset_confirmation')
REQUIRED=('prior_return_1','prior_return_5','prior_return_20','prior_vol_20',
          'prior_sma50_gap','prior_close_range_position','prior_volume_shock',
          'prior_efficiency20','prior_vol_ratio','market_5','bonds_5','gold_5')
MANIFEST={'version':'family_factory_v1','families':list(FAMILIES),
          'multipliers':[.75,1.,1.25],'directions':['both','bull_only'],
          'allocation':.1,'cost_bps_per_side':[10,20],
          'frozen_development_years':[2021,2022,2023],
          'rolling_window_observations':504,'rolling_embargo_observations':2,
          'rolling_min_train':250,'policies':['frozen_family_ensemble','quarterly_selector'],
          'score':'worst_fold_return + .25*mean_fold_return - .5*worst_fold_drawdown_magnitude',
          'positive_score_required_for_policy_entry':True,
          'hypotheses_per_pair':36,'policy_comparisons_per_pair':2,
          'historical_status':'All evaluation years already inspected; no fresh holdout'}


def stable_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def candidates(data):
    if data.empty or data.date.duplicated().any() or not data.date.is_monotonic_increasing:
        raise ValueError('Require nonempty chronological unique dates')
    if not np.isfinite(data[list(REQUIRED)].to_numpy(dtype=float)).all():
        raise ValueError('Require finite lagged predictors')
    if (data.prior_vol_20<0).any():raise ValueError('Negative volatility')
    sd=(data.prior_vol_20/np.sqrt(252)).clip(lower=.001)
    z1=data.prior_return_1/sd
    z5=data.prior_return_5/(sd*np.sqrt(5))
    relative=(data.prior_return_5-data.market_5)/(sd*np.sqrt(5))
    z20=data.prior_return_20/(sd*np.sqrt(20))
    defensive=.5*(data.bonds_5+data.gold_5)
    result={}
    for multiplier in MANIFEST['multipliers']:
        t=multiplier
        predicates={
          'five_day_reversal':(z5 < -t,z5 > t),
          'volume_reversal':((z1 < -t)&(data.prior_volume_shock>.25)&(data.prior_close_range_position<.5),
                             (z1 > t)&(data.prior_volume_shock>.25)&(data.prior_close_range_position>.5)),
          'market_relative_reversal':(relative < -t,relative > t),
          'trend_continuation':((z20 > t)&(data.prior_sma50_gap>0),
                                (z20 < -t)&(data.prior_sma50_gap<0)),
          'compression_breakout':((data.prior_vol_ratio<.8)&(data.prior_close_range_position>=.5+.2*t)&(data.prior_return_5>0),
                                  (data.prior_vol_ratio<.8)&(data.prior_close_range_position<=.5-.2*t)&(data.prior_return_5<0)),
          'cross_asset_confirmation':((z5 > t)&(data.market_5>0)&(defensive<=0),
                                       (z5 < -t)&(data.market_5<0)&(defensive>0))}
        for family,(bull,bear) in predicates.items():
            if np.any(bull&bear):raise ValueError('Ambiguous rule')
            for direction in MANIFEST['directions']:
                sides=np.where(bull,1,np.where(bear,-1,0))
                if direction=='bull_only':sides=np.where(sides==1,1,0)
                key=f'{family}__{t:g}__{direction}'
                result[key]={'family':family,'multiplier':t,'direction':direction,'sides':sides}
    return result


def rank_candidates(data,grid,indices,folds,min_total,min_fold):
    rows=[]
    for key,candidate in grid.items():
        fold_metrics=[size_metrics(data.iloc[idx],candidate['sides'][idx],.1,20) for idx in folds]
        returns=[m['return_pct'] for m in fold_metrics]
        counts=[m['active_sessions'] for m in fold_metrics]
        eligible=sum(counts)>=min_total and min(counts)>=min_fold
        score=min(returns)+.25*np.mean(returns)-.5*max(abs(m['max_close_to_close_drawdown_pct']) for m in fold_metrics)
        rows.append({'candidate':key,'family':candidate['family'],'eligible':bool(eligible),
                     'score':float(score),'fold_returns_20bps':returns,'fold_trades':counts,
                     'train_first_date':str(data.iloc[indices[0]].date),
                     'train_last_date':str(data.iloc[indices[-1]].date)})
    return sorted(rows,key=lambda x:(not x['eligible'],-x['score'],x['candidate']))


def positive_choice(ranking,family=None):
    return next((r['candidate'] for r in ranking if r['eligible'] and r['score']>0
                 and (family is None or r['family']==family)),None)


def policy_returns(data,slots,cost):
    slots=np.asarray(slots)
    if slots.ndim!=2 or slots.shape[0]!=len(data) or slots.shape[1]==0:
        raise ValueError('Invalid policy slots')
    if not np.isin(slots,[-1,0,1]).all():raise ValueError('Invalid policy directions')
    bull=data[f'tqqq_net_{cost}bps_pct'].to_numpy()[:,None]
    bear=data[f'sqqq_net_{cost}bps_pct'].to_numpy()[:,None]
    # Fixed slots share a single 10% budget. Idle slots remain cash.
    return np.where(slots==1,bull,np.where(slots==-1,bear,0.)).mean(axis=1)


def policy_report(data,slots):
    frame=data[['date']].copy()
    for cost in (10,20):frame[f'tqqq_net_{cost}bps_pct']=policy_returns(data,slots,cost);frame[f'sqqq_net_{cost}bps_pct']=0.
    active=(np.asarray(slots)!=0).any(axis=1).astype(int)
    reports={}
    for cost in (10,20):
        m=size_metrics(frame,active,.1,cost)
        m['mean_capital_deployed_pct']=float(10*np.mean(np.asarray(slots)!=0))
        reports[f'cost_{cost}bps']=m
    # Diagnostic removes whole winning sessions with hindsight, never a policy.
    daily=policy_returns(data,slots,10)
    winners=np.flatnonzero((active!=0)&(daily>0))
    best=winners[np.argsort(-daily[winners])[:5]]
    altered=active.copy();altered[best]=0
    skipped=size_metrics(frame,altered,.1,10)
    skipped['mean_capital_deployed_pct']=float(10*np.mean((np.asarray(slots)!=0)*altered[:,None]))
    reports['skip_best_5_sessions']={'removed_winners':len(best),**skipped}
    periods=pd.to_datetime(data.date).dt.to_period('Q')
    reports['quarters_10bps']={}
    for q in sorted(periods.unique()):
        mask=periods==q
        m=size_metrics(frame.loc[mask],active[mask],.1,10)
        m['mean_capital_deployed_pct']=float(10*np.mean(np.asarray(slots)[mask]!=0))
        reports['quarters_10bps'][str(q)]=m
    return reports


def run_factory(data):
    grid=candidates(data);years=pd.to_datetime(data.date).dt.year
    dev=np.flatnonzero(years.between(2021,2023))
    folds=[np.flatnonzero(years.eq(y)) for y in (2021,2022,2023)]
    if any(len(x)==0 for x in folds):raise ValueError('Missing development fold')
    ranking=rank_candidates(data,grid,dev,folds,75,10)
    chosen={family:positive_choice(ranking,family) for family in FAMILIES}
    frozen=np.column_stack([grid[k]['sides'] if k else np.zeros(len(data),dtype=int) for k in chosen.values()])
    rolling=np.zeros((len(data),1),dtype=int);decisions=[]
    quarters=pd.to_datetime(data.date).dt.to_period('Q')
    for quarter in sorted(quarters.unique()):
        if quarter.year<2024:continue
        test=np.flatnonzero(quarters==quarter)
        # Embargo two eligible observations before the evaluation quarter.
        train=np.arange(max(0,test[0]-2))[-504:]
        if len(train)<250:
            decisions.append({'quarter':str(quarter),'selected':None,'status':'INSUFFICIENT_TRAINING'})
            continue
        rank=rank_candidates(data,grid,train,np.array_split(train,4),40,5)
        selected=positive_choice(rank)
        if selected:rolling[test,0]=grid[selected]['sides'][test]
        decisions.append({'quarter':str(quarter),'selected':selected,'ranking':rank})
    policies={'frozen_family_ensemble':frozen,'quarterly_selector':rolling}
    reports={};individual={}
    for period,mask in [('inspected_2024',years.eq(2024)),('inspected_2025_2026',years.ge(2025))]:
        reports[period]={name:policy_report(data.loc[mask],sides[mask]) for name,sides in policies.items()}
        individual[period]={key:{f'cost_{cost}bps':size_metrics(data.loc[mask],c['sides'][mask],.1,cost)
                                for cost in (10,20)} for key,c in grid.items()}
        reports[period]['always_bull']={f'cost_{cost}bps':size_metrics(data.loc[mask],np.ones(mask.sum(),dtype=int),.1,cost)
                                      for cost in (10,20)}
    replay=data[['date']].copy()
    for name,slots in policies.items():
        for cost in (10,20):replay[f'{name}_net_{cost}bps_pct']=policy_returns(data,slots,cost)
        replay[f'{name}_capital_fraction_of_budget']=(slots!=0).mean(axis=1)
    return {'manifest':MANIFEST,'manifest_sha256':stable_hash(MANIFEST),'ranking':ranking,
            'selected_by_family':chosen,'quarterly_decisions':decisions,'policy_reports':reports,
            'individual_reports':individual,'go_no_go':'NO_VALIDATED_EDGE'},replay


def audit_existing_reversals(data):
    """Sensitivity checks on the previous grid, without choosing another winner."""
    from .reversal_research import reversal_sides
    years=pd.to_datetime(data.date).dt.year
    return {key:{period:policy_report(data.loc[mask],sides[mask,None])
                 for period,mask in [('inspected_2024',years.eq(2024)),
                                     ('inspected_2025_2026',years.ge(2025))]}
            for key,sides in reversal_sides(data).items()}
