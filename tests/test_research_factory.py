import numpy as np
import pandas as pd
import pytest
from trade_lab.research_factory import (MANIFEST,candidates,run_factory,
    policy_returns,policy_report,stable_hash,audit_existing_reversals)


def sample():
    dates=pd.bdate_range('2021-01-01','2026-09-30');n=len(dates)
    return pd.DataFrame({'date':dates,'prior_return_1':np.resize([-.03,.03],n),
      'prior_return_5':np.resize([-.06,.06],n),'prior_return_20':.15,
      'prior_vol_20':.2,'prior_sma50_gap':.1,'prior_close_range_position':.9,
      'prior_volume_shock':.5,'prior_efficiency20':.1,'prior_vol_ratio':.6,
      'market_5':.01,'bonds_5':-.02,'gold_5':.005,
      'tqqq_net_10bps_pct':.4,'sqqq_net_10bps_pct':-.1,
      'tqqq_net_20bps_pct':.2,'sqqq_net_20bps_pct':-.3})


def test_grid_manifest_and_no_outcome_predictors():
    data=sample();a=candidates(data)
    assert len(a)==36 and len({x['family'] for x in a.values()})==6
    data['tqqq_net_10bps_pct']=999
    for key,c in candidates(data).items():
        np.testing.assert_array_equal(c['sides'],a[key]['sides'])
        if c['direction']=='bull_only':assert -1 not in c['sides']
    assert stable_hash(MANIFEST)==stable_hash(dict(reversed(list(MANIFEST.items()))))


def test_shared_budget_and_cash_slots_and_costs():
    data=sample().head(3)
    data['tqqq_net_10bps_pct']=10.;data['sqqq_net_10bps_pct']=-20.
    slots=np.array([[1,1],[1,0],[1,-1]])
    np.testing.assert_allclose(policy_returns(data,slots,10),[10.,5.,-5.])
    report=policy_report(data,slots)
    assert report['cost_10bps']['return_pct']==pytest.approx(100*(1.01*1.005*.995-1))
    assert report['cost_10bps']['mean_capital_deployed_pct']==pytest.approx(10*5/6)
    assert report['skip_best_5_sessions']['mean_capital_deployed_pct']==pytest.approx(10*2/6)
    assert report['quarters_10bps']['2021Q1']['mean_capital_deployed_pct']==pytest.approx(10*5/6)
    assert policy_report(data,np.zeros((3,6),dtype=int))['cost_10bps']['return_pct']==0
    with pytest.raises(ValueError,match='directions'):policy_returns(data,np.full((3,1),2),10)


def test_frozen_selection_and_quarterly_fit_are_causal():
    data=sample();a,replay=run_factory(data)
    changed=data.copy();future=changed.date.dt.year>=2024
    changed.loc[future,['tqqq_net_20bps_pct','sqqq_net_20bps_pct']]=99.
    b,_=run_factory(changed)
    assert a['ranking']==b['ranking']
    assert a['selected_by_family']==b['selected_by_family']
    assert a['quarterly_decisions'][0]==b['quarterly_decisions'][0]
    assert len(replay)==len(data)
    assert replay.filter(like='capital_fraction').max().max()<=1
    for row in a['quarterly_decisions']:
        first=pd.Period(row['quarter']).start_time
        cutoff=data.loc[data.date<first].iloc[:-2].date.max()
        assert pd.Timestamp(row['ranking'][0]['train_last_date'])<=cutoff


def test_negative_training_returns_make_policies_hold_cash():
    data=sample()
    data[['tqqq_net_20bps_pct','sqqq_net_20bps_pct']]=-.5
    result,replay=run_factory(data)
    assert all(x is None for x in result['selected_by_family'].values())
    assert all(x['selected'] is None for x in result['quarterly_decisions'])
    assert (replay.filter(like='capital_fraction')==0).all().all()


def test_missing_and_unsorted_observations_rejected():
    data=sample();data.loc[0,'market_5']=np.nan
    with pytest.raises(ValueError,match='finite'):candidates(data)
    with pytest.raises(ValueError,match='chronological'):candidates(sample().iloc[::-1])


def test_existing_reversal_audit_keeps_all_variants_and_skips_only_winners():
    data=sample();audit=audit_existing_reversals(data)
    assert len(audit)==12
    report=audit['sigma_0.75_bull_only']['inspected_2025_2026']
    assert report['skip_best_5_sessions']['removed_winners']==5
    assert report['skip_best_5_sessions']['return_pct']<report['cost_10bps']['return_pct']
