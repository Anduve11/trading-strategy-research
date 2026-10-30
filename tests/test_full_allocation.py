import runpy
import numpy as np
import pandas as pd
import pytest
from trade_lab.research_factory import FAMILIES
from trade_lab.full_allocation import (with_cost_stress,risk_metrics,signal_report,
    growth_ranking,rule_grid,run_full_equity,active_weight_returns)


def sample():
    data=runpy.run_path('tests/test_research_factory.py')['sample']()
    data['frozen_incumbent_side']=1
    return data


def source():
    return {'selected_by_family':{family:None for family in FAMILIES},'quarterly_decisions':[]}


def test_compounds_current_equity_and_reports_actual_drawdown():
    data=with_cost_stress(sample().head(3));data['tqqq_net_10bps_pct']=[10,-50,10]
    a=risk_metrics(data,[1,1,1],1.,10);b=risk_metrics(data,[1,1,1],.1,10)
    assert a['return_pct']==pytest.approx(-39.5)
    assert a['max_close_to_close_drawdown_pct']==pytest.approx(-50)
    assert a['recovery_needed_from_max_drawdown_pct']==pytest.approx(100)
    assert a['return_pct']!=pytest.approx(10*b['return_pct'])
    assert a['drawdown_breach_sessions']['50']==1
    assert a['ending_10000']==pytest.approx(6050)


def test_active_ensemble_uses_full_total_budget_and_no_signal_is_cash():
    data=with_cost_stress(sample().head(3));data['tqqq_net_10bps_pct']=10.;data['sqqq_net_10bps_pct']=-20.
    slots=np.array([[1,0,0],[1,-1,0],[0,0,0]])
    np.testing.assert_allclose(active_weight_returns(data,slots,10),[10,-5,0])


def test_50bps_uses_same_observed_close_open_ratio():
    data=sample().head(2);data['tqqq_net_10bps_pct']=100*((1-.001)/(1+.001)-1)
    stressed=with_cost_stress(data)
    np.testing.assert_allclose(stressed.tqqq_net_50bps_pct,100*((1-.005)/(1+.005)-1))
    assert (stressed.tqqq_net_50bps_pct<stressed.tqqq_net_10bps_pct).all()


def test_future_labels_cannot_change_growth_ranking():
    data=with_cost_stress(sample());grid=rule_grid(data)
    train=np.flatnonzero(pd.to_datetime(data.date).dt.year<=2023)
    a=growth_ranking(data,grid,train,75,10)
    data.loc[pd.to_datetime(data.date).dt.year>=2024,'tqqq_net_20bps_pct']=999
    assert a==growth_ranking(data,grid,train,75,10)


def test_full_report_budget_selection_and_embargo():
    data=sample();result,replay=run_full_equity(data,source())
    assert len(result['individual_reports']['inspected_2025_2026'])==49
    assert len(result['growth_ranking'])==48
    assert len(result['policy_reports']['inspected_2024'])==6
    assert result['policy_reports']['inspected_2024']['fixed_slot_family_ensemble']['cost_10bps']['return_pct']==0
    assert len(replay)==len(data)
    for decision in result['quarterly_decisions']:
        if not decision['ranking']:continue
        quarter_start=pd.Period(decision['quarter']).start_time
        cutoff=data.loc[data.date<quarter_start].iloc[:-2].date.max()
        assert pd.Timestamp(decision['ranking'][0]['train_last_date'])<=cutoff


def test_sensitivity_removes_winners_and_shared_budget_metadata():
    data=with_cost_stress(sample().head(6))
    result=signal_report(data,np.ones(6,dtype=int),1.,np.full(6,1/6))
    assert result['cost_10bps']['mean_capital_deployed_pct']==pytest.approx(100/6)
    assert result['skip_best_winning_sessions']['5']['active_sessions']==1
    assert result['skip_best_winning_sessions']['5']['mean_capital_deployed_pct']==pytest.approx(100/36)
    assert result['cost_50bps']['return_pct']<result['cost_10bps']['return_pct']
