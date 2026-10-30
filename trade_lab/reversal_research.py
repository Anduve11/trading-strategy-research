"""Small, declared reversal grid; development-only selection at stressed costs."""
import numpy as np
import pandas as pd
from .sizing_research import size_metrics


def reversal_sides(data):
    columns=['prior_return_1','prior_vol_20','prior_return_20',
             'prior_sma50_gap','prior_efficiency20']
    if not np.isfinite(data[columns].to_numpy(dtype=float)).all():
        raise ValueError('Require finite lagged predictors')
    if (data.prior_vol_20 < 0).any():
        raise ValueError('Negative volatility')
    sd=(data.prior_vol_20/np.sqrt(252)).clip(lower=.001)
    up=(data.prior_return_20>0)&(data.prior_sma50_gap>0)
    down=(data.prior_return_20<0)&(data.prior_sma50_gap<0)
    result={}
    for threshold in (.75,1.,1.25):
        base=np.where(data.prior_return_1 < -threshold*sd,1,
                      np.where(data.prior_return_1 > threshold*sd,-1,0))
        modes={'both':base,'bull_only':np.where(base==1,1,0),
               'trend_aligned':np.where(((base==1)&up)|((base==-1)&down),base,0),
               'low_directionality':np.where(data.prior_efficiency20.abs()<.3,base,0)}
        for mode,sides in modes.items():result[f'sigma_{threshold:g}_{mode}']=sides
    return result


def run_reversals(data):
    years=pd.to_datetime(data.date).dt.year
    strategies=reversal_sides(data)
    rows=[]
    # No outcome from 2024 onward can affect ranking, eligibility or selection.
    for name,sides in strategies.items():
        folds=[size_metrics(data.loc[years.eq(y)],sides[years.eq(y)],.1,20)
               for y in (2021,2022,2023)]
        returns=[m['return_pct'] for m in folds]
        counts=[m['active_sessions'] for m in folds]
        eligible=sum(counts)>=75 and min(counts)>=10
        score=min(returns)+.25*np.mean(returns)-.5*max(
            abs(m['max_close_to_close_drawdown_pct']) for m in folds)
        rows.append({'strategy':name,'eligible':bool(eligible),
                     'score':float(score),'fold_returns_20bps':returns,
                     'fold_active_sessions':counts})
    rows=sorted(rows,key=lambda x:(not x['eligible'],-x['score'],x['strategy']))
    selected=next((r['strategy'] for r in rows if r['eligible']),None)
    reports={}
    for period,mask in [('development_2021_2023',years.between(2021,2023)),
                        ('inspected_2024',years.eq(2024)),
                        ('inspected_2025_2026',years.ge(2025))]:
        reports[period]={name:{'primary_10bps':size_metrics(data.loc[mask],sides[mask],.1,10),
                              'selection_cost_20bps':size_metrics(data.loc[mask],sides[mask],.1,20)}
                         for name,sides in strategies.items()}
    return {'selected_strategy':selected,'ranking':rows,'reports':reports,
            'go_no_go':'NO_VALIDATED_EDGE'}
