"""Leakage-resistant 09:50 ET session features and baseline classifiers.

The models predict the sign of a subsequent 60-minute QQQ return, not
trading profits. An independent simulator determines whether orders would
have made money after friction; all results are research-only.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import time
import numpy as np
import pandas as pd
from .data import ET

FEATURES = (
    'overnight_gap', 'opening20_return', 'opening20_range',
    'opening20_vwap_gap', 'opening20_volume_ratio',
    'lag_return_1', 'lag_return_5', 'lag_return_20',
    'lag_vol_20', 'lag_sma50_gap', 'weekday',
)


def extract_month(bars: pd.DataFrame, prior_days: list[dict] | None = None):
    """Build decision-time feature rows, carrying ONLY finalized previous days.

    QQQ signal timestamp is bar 09:50, observed after it closes at 09:51.
    The return label is QQQ 09:51 open -> 10:51 close, never a feature.
    Full historical labels are unavailable for the most recent real-time day.
    """
    prior = list(prior_days or [])
    rows = []
    q = bars.loc[bars.symbol.eq('QQQ')].sort_values('timestamp').copy()
    q['day'] = q.timestamp.dt.tz_convert(ET).dt.date
    q['minute'] = q.timestamp.dt.tz_convert(ET).dt.strftime('%H:%M')
    for day, group in q.groupby('day',sort=True):
        x = group.set_index('minute')
        early = x.loc[(x.index >= '09:30') & (x.index <= '09:50')]
        # Update history ONLY AFTER calculating the current-day signal.
        if all(k in x.index for k in ('09:30','09:50','09:51','10:51')) and len(early)==21 and len(prior)>=51:
            closes = np.asarray([d['close'] for d in prior], dtype=float)
            rets = np.diff(np.log(closes[-21:]))
            vhist = [d['opening_volume'] for d in prior[-20:] if d['opening_volume']>0]
            if len(vhist)>=15 and np.all(np.isfinite(closes)):
                start_open = float(x.loc['09:30','open'])
                end_close = float(x.loc['09:50','close'])
                hi = float(early.high.max()); lo=float(early.low.min())
                vol=float(early.volume.sum())
                vwap = float(((early.high+early.low+early.close)/3*early.volume).sum()/max(vol,1))
                entry = float(x.loc['09:51','open'])
                outcome=float(x.loc['10:51','close'])/entry-1
                prev=float(closes[-1])
                signal_ts=pd.Timestamp(x.loc['09:50','timestamp'])
                rows.append({'date':day,'timestamp':signal_ts,
                    'overnight_gap':start_open/prev-1,
                    'opening20_return':end_close/start_open-1,
                    'opening20_range':hi/lo-1,
                    'opening20_vwap_gap':end_close/vwap-1,
                    'opening20_volume_ratio':vol/np.mean(vhist)-1,
                    'lag_return_1':prev/closes[-2]-1,
                    'lag_return_5':prev/closes[-6]-1,
                    'lag_return_20':prev/closes[-21]-1,
                    'lag_vol_20':float(np.std(rets,ddof=1)*np.sqrt(252)),
                    'lag_sma50_gap':prev/np.mean(closes[-50:])-1,
                    'weekday':day.weekday(),
                    'target_up':int(outcome>0),
                    'forward_return_60m':outcome,
                    'entry_open_qqq':entry})
        if not group.empty:
            early_volume=float(early.volume.sum()) if len(early)==21 else 0.0
            prior.append({'close':float(group.iloc[-1].close), 'opening_volume':early_volume})
            prior=prior[-65:]
    return pd.DataFrame(rows),prior


def models():
    """Compact, regularized comparators. scikit-learn is required only for ML job."""
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
    return {
        'logistic_l2':make_pipeline(StandardScaler(),LogisticRegression(C=0.3,max_iter=500,random_state=41)),
        'random_forest':RandomForestClassifier(n_estimators=120,min_samples_leaf=20,
                                              max_depth=5,max_features=0.7,random_state=41,n_jobs=1),
        'hist_gradient_boosting':HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=9,
                                            min_samples_leaf=30,l2_regularization=5.,learning_rate=.04,
                                            random_state=41),
    }


def decide(p_up, threshold):
    p=np.asarray(p_up,dtype=float)
    if not (0.5<threshold<1): raise ValueError('Threshold must be strictly between 0.5 and 1.')
    if (p<0).any() or (p>1).any() or not np.isfinite(p).all():raise ValueError('Invalid probability')
    return np.where(p>=threshold,1,np.where(p<=1-threshold,-1,0))


def evaluate_decisions(frame:pd.DataFrame, side, allocation=0.10, initial=10000.):
    """Compute account returns from already simulated, cost-adjusted actual ETF fills."""
    choices=np.asarray(side,dtype=int)
    if len(choices)!=len(frame):raise ValueError('Side length mismatch')
    if not set(choices).issubset({-1,0,1}):raise ValueError('Unknown trade direction')
    if not 0<allocation<=1:raise ValueError('Invalid allocation')
    r=np.where(choices==1,frame['tqqq_net_pct'].to_numpy(dtype=float),
                np.where(choices==-1,frame['sqqq_net_pct'].to_numpy(dtype=float),0.))
    if not np.isfinite(r).all():raise ValueError('Missing simulated entry/exit')
    eq=initial*np.cumprod(1.+allocation*r/100.)
    peaks=np.maximum.accumulate(np.r_[initial,eq])
    actual=r[choices!=0]
    return {'trades':int(np.count_nonzero(choices)),
            'win_rate_pct':float(np.mean(actual>0)*100) if len(actual) else 0.,
            'return_pct':float((eq[-1]/initial-1)*100) if len(eq) else 0.,
            'max_drawdown_pct':float(np.min(np.r_[initial,eq]/peaks-1.)*100),
            'ending_equity':float(eq[-1]) if len(eq) else float(initial)}


def split_periods(df):
    """Fixed calendar periods. Diagnostic 2025+ already viewed, not clean holdout."""
    years=pd.to_datetime(df.date).dt.year
    return {'training':df.loc[(years>=2019)&(years<=2022)].copy(),
            'development_validation':df.loc[years==2023].copy(),
            'independent_2024':df.loc[years==2024].copy(),
            'inspected_2025_2026':df.loc[(years>=2025)&(years<=2026)].copy()}


def fit_evaluate(df, thresholds=(0.53,0.57,0.60,0.65), min_dev_trades=15):
    """Select model/threshold ONLY with 2023 results; report 2024 and 2025+.

    Historical 2025+ data has been inspected for other strategies and is
    retrospective diagnostics, never a fresh final holdout.
    """
    from sklearn.metrics import brier_score_loss, roc_auc_score
    parts=split_periods(df)
    train=parts['training']; dev=parts['development_validation']
    if len(train)<300 or len(dev)<100 or train.target_up.nunique()<2:
        raise ValueError('Too little complete training/development data for ML research.')
    table=[]; trained={}
    for name,model in models().items():
        model.fit(train[list(FEATURES)],train.target_up.astype(int))
        trained[name]=model
        for threshold in thresholds:
            p=model.predict_proba(dev[list(FEATURES)])[:,1]
            sides=decide(p,threshold)
            met=evaluate_decisions(dev,sides)
            table.append({'model':name,'threshold':float(threshold),
                          'brier_2023':float(brier_score_loss(dev.target_up,p)),
                          **{('dev_'+k):v for k,v in met.items()}})
    ranking=pd.DataFrame(table)
    ranking['eligible']=ranking.dev_trades>=min_dev_trades
    # Do not reward high returns from 2 lucky trades.
    ranking['score']=np.where(ranking.eligible,
            ranking.dev_return_pct-0.7*np.abs(ranking.dev_max_drawdown_pct),-1e6)
    ranking=ranking.sort_values(['score','dev_trades'],ascending=[False,False]).reset_index(drop=True)
    leader=ranking.iloc[0]
    # If no candidate trades enough, report research failure instead of selecting a winner.
    if not bool(leader.eligible):
        return {'qualified':False,'ranking':ranking,'selected':None,'reports':{}}
    # Once 2023 selects the model family/threshold, refit that family on
    # all data available through 2023. Never fit on 2024+ labels.
    cutoff=float(leader.threshold)
    model_name=str(leader.model)
    chosen=models()[model_name]
    historic=pd.concat([train,dev],ignore_index=True)
    chosen.fit(historic[list(FEATURES)],historic.target_up.astype(int))
    reports={}
    for period in ('development_validation','independent_2024','inspected_2025_2026'):
        part=parts[period]
        if part.empty:continue
        prob_model=trained[model_name] if period == 'development_validation' else chosen
        pp=prob_model.predict_proba(part[list(FEATURES)])[:,1]
        sides=decide(pp,cutoff)
        met=evaluate_decisions(part,sides)
        reports[period]={**met,'samples':len(part),
             'brier_score':float(brier_score_loss(part.target_up,pp)),
             'base_up_fraction':float(part.target_up.mean()),
             'prediction_auc':float(roc_auc_score(part.target_up,pp)) if part.target_up.nunique()>1 else None}
    return {'qualified':True,'selected':{'model':str(leader.model),'threshold':cutoff},
            'ranking':ranking,'reports':reports}