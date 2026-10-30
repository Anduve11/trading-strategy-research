"""Causal daily models of log growth and conditional downside; paper only."""
import numpy as np
import pandas as pd
from .daily_screen import FEATURES
from .context_factors import CONTEXT,BEHAVIOR
from .macro import MACRO_FEATURES
from .adaptive_research import CALENDAR
from .edge_research import OPTION_FEATURES,append_option_features
from .research_factory import candidates,stable_hash
from .full_allocation import with_cost_stress,risk_metrics,signal_report,net_returns

INTERACTIONS=('relative_strength_z','volume_return_interaction','gap_session_disagreement',
    'defensive_flow','trend_volatility_interaction','fear_volume_interaction',
    'downside_vol20','return_autocorrelation20','market_correlation20')
BASE=(*FEATURES,*BEHAVIOR,*CONTEXT,*MACRO_FEATURES,*CALENDAR,*INTERACTIONS)
SPECS={'behavior_macro':list(BASE),'behavior_macro_options':[*BASE,*OPTION_FEATURES]}
MODELS=('ridge_log','hist_log','quantile_log')
MANIFEST={'version':'regime_models_v1','models':list(MODELS),'feature_sets':SPECS,
    'cushions_log_return':[0.,.001],'filters':['direct','volume_confirm'],
    'directions':['both','bull_only'],'primary_allocation':1.,'cost_bps_per_side':[10,20,50],
    'training_target':'log1p(actual ETF net return at 20bps per side), no target clipping',
    'rolling_training_observations':756,'minimum_train':400,'embargo_observations':2,
    'selection_years':[2021,2022,2023],'minimum_development_trades':40,'minimum_annual_trades':5,
    'selection_score':'mean daily realized full-equity log growth at 20bps; positive score required',
    'quantile_rule':'choose median log return above cushion and predicted 25th percentile above -0.03',
    'matched_sample':True,'hypotheses_per_pair':48,
    'historical_status':'All evaluation years already inspected; no fresh holdout'}


def build_features(data,options):
    if data.date.duplicated().any() or not data.date.is_monotonic_increasing:raise ValueError('Require chronological unique dates')
    out=append_option_features(data,options)
    sd=(out.prior_vol_20/np.sqrt(252)).clip(lower=.001)
    out['relative_strength_z']=(out.prior_return_5-out.market_5)/(sd*np.sqrt(5))
    out['volume_return_interaction']=out.prior_volume_shock*out.prior_return_1/sd
    out['gap_session_disagreement']=np.sign(out.prior_intraday)*np.sign(out.prior_overnight)
    out['defensive_flow']=.5*(out.bonds_5+out.gold_5)
    out['trend_volatility_interaction']=out.prior_efficiency20*out.prior_vol_ratio
    out['fear_volume_interaction']=out.prior_vix_change5*out.prior_volume_shock
    # These inputs already refer to earlier sessions; rolling adds no extra
    # current-session price or volume. Windows count eligible observations.
    r=out.prior_return_1
    out['downside_vol20']=np.sqrt(r.clip(upper=0).pow(2).rolling(20,min_periods=20).mean()*252)
    out['return_autocorrelation20']=r.rolling(20,min_periods=20).corr(r.shift(1))
    out['market_correlation20']=r.rolling(20,min_periods=20).corr(out.market_1)
    columns=[*SPECS['behavior_macro_options'],'tqqq_net_20bps_pct','sqqq_net_20bps_pct']
    # Identical observations for both feature sets make the options ablation
    # a feature comparison, rather than a hidden change of sample dates.
    return with_cost_stress(out.replace([np.inf,-np.inf],np.nan).dropna(subset=columns).reset_index(drop=True))


def predict_log(train,test,columns,model):
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import HistGradientBoostingRegressor
    if model not in MODELS:raise ValueError('Unknown model')
    if len(train)<400 or train.date.max()>=test.date.min():raise ValueError('Insufficient or overlapping training')
    a=train[columns].to_numpy(dtype=float);b=test[columns].to_numpy(dtype=float)
    if not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('Nonfinite predictors')
    returns=train[['tqqq_net_20bps_pct','sqqq_net_20bps_pct']].to_numpy(dtype=float)/100
    if not np.isfinite(returns).all() or (returns<=-1).any():raise ValueError('Invalid growth labels')
    y=np.log1p(returns)
    if model=='ridge_log':
        scaler=StandardScaler().fit(a);fitted=Ridge(alpha=100.).fit(scaler.transform(a),y)
        center=fitted.predict(scaler.transform(b));return center,center.copy()
    params=dict(max_iter=60,max_leaf_nodes=7,min_samples_leaf=60,learning_rate=.05,
                l2_regularization=5.,early_stopping=False,random_state=83)
    center=[];lower=[]
    for side in range(2):
        estimator=HistGradientBoostingRegressor(loss='quantile' if model=='quantile_log' else 'squared_error',
                    quantile=.5 if model=='quantile_log' else None,**params).fit(a,y[:,side])
        center.append(estimator.predict(b))
        if model=='quantile_log':
            low=HistGradientBoostingRegressor(loss='quantile',quantile=.25,**params).fit(a,y[:,side]).predict(b)
            lower.append(low)
        else:lower.append(center[-1])
    center=np.column_stack(center);lower=np.column_stack(lower)
    # Independently estimated quantiles can cross. Enforce q25 <= median
    # conservatively by lowering q25; never raise the median forecast.
    return center,np.minimum(center,lower)


def quarterly_predictions(data,columns,model):
    quarters=pd.to_datetime(data.date).dt.to_period('Q');pieces=[];predictions=[];tails=[];fits=[]
    for quarter in sorted(quarters.unique()):
        if quarter.year<2021:continue
        idx=np.flatnonzero(quarters==quarter);train=data.iloc[:max(0,idx[0]-2)].tail(756)
        if len(train)<400:continue
        test=data.iloc[idx]
        center,lower=predict_log(train,test,columns,model)
        pieces.append(test);predictions.append(center);tails.append(lower)
        fits.append({'quarter':str(quarter),'training_rows':len(train),
                     'train_first_date':str(train.date.min()),'train_last_date':str(train.date.max()),
                     'prediction_first_date':str(test.date.min()),'prediction_last_date':str(test.date.max())})
    if not pieces:raise ValueError('No eligible causal forecasts')
    return pd.concat(pieces,ignore_index=True),np.concatenate(predictions),np.concatenate(tails),fits


def decisions(center,lower,cushion,model,filter_name,direction,volume_side):
    center=np.asarray(center);lower=np.asarray(lower)
    if center.ndim!=2 or center.shape[1]!=2 or lower.shape!=center.shape or not np.isfinite(center).all() or not np.isfinite(lower).all():
        raise ValueError('Invalid forecasts')
    best=center.argmax(axis=1)
    sides=np.where(best==0,1,-1)
    eligible=(center.max(axis=1)>cushion)&(center[:,0]!=center[:,1])
    if filter_name=='volume_confirm':
        sides=np.asarray(volume_side);best=np.where(sides==1,0,1)
        eligible=(sides!=0)&(center[np.arange(len(sides)),best]>cushion)
    elif filter_name!='direct':raise ValueError('Unknown decision filter')
    if model=='quantile_log':eligible &= lower[np.arange(len(sides)),best]>-.03
    if direction=='bull_only':eligible &= sides==1
    elif direction!='both':raise ValueError('Unknown direction')
    return np.where(eligible,sides,0)


def run_models(data):
    stored={};rank=[];frame=None;forecast_replay=None;fit_log={}
    for feature_set,columns in SPECS.items():
        for model in MODELS:
            part,center,lower,fits=quarterly_predictions(data,columns,model)
            if frame is None:
                frame=part;forecast_replay=part[['date']].copy()
            elif not frame.date.equals(part.date):raise ValueError('Unmatched forecast samples')
            key=f'{feature_set}__{model}';fit_log[key]=fits
            for j,side in enumerate(('bull','inverse')):
                forecast_replay[f'{key}__{side}_center_log']=center[:,j]
                label='q25_log' if model=='quantile_log' else 'center_repeat_log'
                forecast_replay[f'{key}__{side}_{label}']=lower[:,j]
            volume=candidates(part)['volume_reversal__0.75__both']['sides']
            years=pd.to_datetime(part.date).dt.year;dev=years.between(2021,2023)
            for cushion in (0.,.001):
                for filter_name in ('direct','volume_confirm'):
                    for direction in ('both','bull_only'):
                        sides=decisions(center,lower,cushion,model,filter_name,direction,volume)
                        name=f'{key}__{cushion:g}__{filter_name}__{direction}'
                        stored[name]=sides;forecast_replay['signal__'+name]=sides
                        counts=[int((sides[years.eq(y)]!=0).sum()) for y in (2021,2022,2023)]
                        eligible=sum(counts)>=40 and min(counts)>=5
                        score=float(np.log1p(net_returns(part.loc[dev],sides[dev],20)).mean())
                        rank.append({'candidate':name,'feature_set':feature_set,'model':model,'cushion_log':cushion,
                                     'filter':filter_name,'direction':direction,'eligible':bool(eligible),
                                     'score':score,'fold_trades':counts})
    rank=sorted(rank,key=lambda x:(not x['eligible'],-x['score'],x['candidate']))
    selected=next((r['candidate'] for r in rank if r['eligible'] and r['score']>0),None)
    volume=candidates(frame)['volume_reversal__0.75__both']['sides']
    baselines={'unfiltered_volume_reversal':volume,'daily_bull_open_close':np.ones(len(frame),dtype=int)}
    years=pd.to_datetime(frame.date).dt.year;reports={};chosen={};controls={}
    for period,mask in [('development_2021_2023',years.between(2021,2023)),('inspected_2024',years.eq(2024)),
                         ('inspected_2025_2026',years.ge(2025)),('inspected_2024_2026',years.ge(2024))]:
        reports[period]={name:{f'cost_{c}bps':risk_metrics(frame.loc[mask],sides[mask],1.,c) for c in (10,20,50)}
                         for name,sides in stored.items()}
        chosen_sides=stored[selected] if selected else np.zeros(len(frame),dtype=int)
        chosen[period]=signal_report(frame.loc[mask],chosen_sides[mask],1.)
        controls[period]={name:signal_report(frame.loc[mask],sides[mask],1.) for name,sides in baselines.items()}
    return {'manifest':MANIFEST,'manifest_sha256':stable_hash(MANIFEST),'selected':selected,
            'ranking':rank,'individual_reports':reports,'selected_reports':chosen,'baseline_reports':controls,
            'fit_log':fit_log,'go_no_go':'NO_VALIDATED_EDGE'},forecast_replay
