import pandas as pd
import pytest
from trade_lab.auto import search_candidates, FILTERS, filter_mask, replay_returns, evaluate_filters,run_summary


def sample_log():
    return pd.DataFrame([
        {'candidate':'A','date':'2020-01-01','period':'Development','regime':'Downtrend / High volatility','net_return_pct':3.},
        {'candidate':'A','date':'2020-01-02','period':'Development','regime':'Uptrend / Normal volatility','net_return_pct':-2.},
        {'candidate':'A','date':'2024-01-01','period':'Validation','regime':'Downtrend / High volatility','net_return_pct':1.},
        {'candidate':'A','date':'2025-01-01','period':'Final holdout','regime':'Uptrend / Normal volatility','net_return_pct':-1.},
        {'candidate':'B','date':'2020-01-01','period':'Development','regime':'Downtrend / High volatility','net_return_pct':-3.},
        {'candidate':'B','date':'2024-01-01','period':'Validation','regime':'Downtrend / High volatility','net_return_pct':-1.},
    ])


def test_candidates_are_predeclared_and_unique():
    grid=search_candidates()
    assert len(grid)==168
    assert len(set(grid))==168
    assert len(grid)*len(FILTERS)==1344


def test_filters_do_not_use_outcomes():
    x=sample_log()
    mask=filter_mask(x,'downtrend_high_vol')
    assert x.loc[mask,'date'].tolist()==['2020-01-01','2024-01-01','2020-01-01','2024-01-01']
    y=x.copy();y['net_return_pct']*= -123
    assert mask.equals(filter_mask(y,'downtrend_high_vol'))


def test_replay_compounds_allocation_and_drawdown():
    x=pd.DataFrame([{'date':'2020-01-01','net_return_pct':10.},{'date':'2020-01-02','net_return_pct':-10.}])
    out=replay_returns(x,10,10000)
    assert out['ending_equity']==pytest.approx(9999.)
    assert out['max_drawdown_pct']==pytest.approx(-1.0)
    assert replay_returns(pd.DataFrame(),10)['return_pct']==0


def test_leaderboard_ranks_only_development():
    x=sample_log()
    a=evaluate_filters({'trade_log':x},min_dev_trades=1)
    # Holdout changes cannot affect ordering or selected candidate
    y=x.copy();y.loc[y.period=='Final holdout','net_return_pct']=10000
    b=evaluate_filters({'trade_log':y},min_dev_trades=1)
    assert a.test_id.tolist()==b.test_id.tolist()
    assert run_summary(a)['selected']==run_summary(b)['selected']
    assert len(a)==len(FILTERS)*2