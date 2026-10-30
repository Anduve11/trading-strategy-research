import json
import numpy as np
import pandas as pd
import pytest
import trade_lab.regime_models as regime


def sample():
    dates=pd.bdate_range('2019-01-01','2026-09-30');n=len(dates);rng=np.random.default_rng(91)
    data=pd.DataFrame({column:rng.normal(0,.01,n) for column in regime.SPECS['behavior_macro_options']})
    data['date']=dates;data['prior_vol_20']=.2;data['prior_vix']=20.
    data['prior_vol_ratio']=.8;data['prior_close_range_position']=rng.uniform(0,1,n)
    data['prior_volume_shock']=rng.uniform(-.5,1,n)
    for side,sign in [('tqqq',1),('sqqq',-1)]:
        data[f'{side}_net_10bps_pct']=sign*data.prior_return_1*50-.1
        data[f'{side}_net_20bps_pct']=data[f'{side}_net_10bps_pct']-.2
    from trade_lab.full_allocation import with_cost_stress
    return with_cost_stress(data)


def fake_predict(train,test,columns,model):
    assert len(train)>=400 and train.date.max()<test.date.min()
    mean=np.log1p(train[['tqqq_net_20bps_pct','sqqq_net_20bps_pct']].to_numpy()/100).mean(axis=0)
    center=np.tile(mean,(len(test),1))
    return center,center-.01


def test_new_features_are_past_only_and_option_join_strict():
    data=sample();dates=pd.bdate_range('2018-01-01','2026-10-01');n=len(dates)
    options=pd.DataFrame({'date':dates,'VIX':20.,'VIX9D':18.+np.arange(n)*.0001,'VVIX':90.})
    before=regime.build_features(data,options)
    changed=options.copy();changed.loc[changed.date>=pd.Timestamp('2024-01-02'),'VIX9D']*=2
    after=regime.build_features(data,changed)
    mask=before.date<=pd.Timestamp('2024-01-02')
    np.testing.assert_allclose(before.loc[mask,list(regime.OPTION_FEATURES)],after.loc[mask,list(regime.OPTION_FEATURES)])
    mutated=data.copy();mutated.loc[mutated.date>=pd.Timestamp('2024-01-03'),'prior_return_1']*=10
    future=regime.build_features(mutated,options)
    pd.testing.assert_frame_equal(before.loc[mask].reset_index(drop=True),future.loc[mask].reset_index(drop=True))
    assert np.isfinite(before[regime.SPECS['behavior_macro_options']]).all().all()


def test_decision_rules_filter_direction_and_downside():
    center=np.array([[.01,-.01],[-.01,.02],[.02,.01],[0.,0.]])
    lower=np.array([[-.02,-.03],[-.03,-.04],[-.02,-.02],[0.,0.]])
    volume=np.array([1,-1,-1,0])
    assert regime.decisions(center,lower,0,'quantile_log','direct','both',volume).tolist()==[1,0,1,0]
    assert regime.decisions(center,lower,0,'hist_log','volume_confirm','both',volume).tolist()==[1,-1,-1,0]
    assert regime.decisions(center,lower,0,'hist_log','direct','bull_only',volume).tolist()==[1,0,1,0]
    with pytest.raises(ValueError,match='forecasts'):regime.decisions(center[:,0],lower,0,'hist_log','direct','both',volume)


def test_models_fit_actual_log_labels_and_quantiles_do_not_cross():
    data=sample();columns=['prior_return_1','prior_vol_20']
    for model in regime.MODELS:
        center,lower=regime.predict_log(data.head(450),data.iloc[450:470],columns,model)
        assert center.shape==lower.shape==(20,2)
        assert np.isfinite(center).all() and (lower<=center).all()
    with pytest.raises(ValueError,match='overlapping'):
        regime.predict_log(data.head(450),data.head(20),columns,'ridge_log')


def test_quarter_fit_and_feature_scaling_never_use_current_quarter_labels(monkeypatch):
    monkeypatch.setattr(regime,'predict_log',fake_predict)
    data=sample();before,center,_,fits=regime.quarterly_predictions(data,['prior_return_1'],'ridge_log')
    changed=data.copy();quarters=pd.to_datetime(changed.date).dt.to_period('Q')
    changed.loc[quarters.eq(pd.Period('2024Q1')),'tqqq_net_20bps_pct']=50.
    _,new,_,_=regime.quarterly_predictions(changed,['prior_return_1'],'ridge_log')
    q=pd.to_datetime(before.date).dt.to_period('Q')
    np.testing.assert_array_equal(center[q==pd.Period('2024Q1')],new[q==pd.Period('2024Q1')])
    assert not np.allclose(center[q==pd.Period('2024Q2')],new[q==pd.Period('2024Q2')])
    for fit in fits:
        cutoff=data.loc[data.date<pd.Timestamp(fit['prediction_first_date'])].iloc[:-2].date.max()
        assert pd.Timestamp(fit['train_last_date'])<=cutoff
        assert 400<=fit['training_rows']<=756


def test_full_grid_retains_failures_and_selection_ignores_later_results(monkeypatch):
    monkeypatch.setattr(regime,'predict_log',fake_predict)
    data=sample();a,replay=regime.run_models(data)
    changed=data.copy();future=changed.date.dt.year>=2024
    changed.loc[future,'tqqq_net_20bps_pct']=30.
    b,_=regime.run_models(changed)
    assert len(a['ranking'])==48
    assert a['ranking']==b['ranking'] and a['selected']==b['selected']
    assert len(a['individual_reports']['inspected_2024'])==48
    assert len(replay.filter(like='signal__').columns)==48
    json.dumps(a,allow_nan=False)
