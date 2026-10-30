import runpy
import numpy as np
import pandas as pd
import pytest
from trade_lab.sizing_research import size_metrics,rule_sides,compare_sizing


def sample():
    df=runpy.run_path('tests/test_edge_research.py')['mock_research_data']()
    df['prior_efficiency20']=.4
    for side in ('tqqq','sqqq'):df[f'{side}_net_20bps_pct']=df[f'{side}_net_10bps_pct']-.2
    return df


def test_account_size_changes_dollars_not_percent():
    df=sample().head(2);df['tqqq_net_10bps_pct']=[10.,-10.]
    m=size_metrics(df,[1,1],1.)
    assert m['return_pct']==pytest.approx(-1.)
    assert m['max_close_to_close_drawdown_pct']==pytest.approx(-10.)
    assert m['ending_100000']==pytest.approx(10*m['ending_10000'])
    with pytest.raises(ValueError,match='Allocation'):size_metrics(df,[1,1],1.01)


def test_cash_and_costs_and_array_allocations():
    df=sample().head(5)
    assert size_metrics(df,np.zeros(5),1.)['return_pct']==0
    a=size_metrics(df,np.ones(5),[.1,.25,.5,.75,1.],10)
    b=size_metrics(df,np.ones(5),[.1,.25,.5,.75,1.],20)
    assert b['return_pct']<a['return_pct']


def test_rule_selection_never_uses_later_outcomes():
    df=sample();inc=np.zeros(len(df),dtype=int)
    a=compare_sizing(df,inc,3)
    future=pd.to_datetime(df.date).dt.year>=2024
    changed=df.copy();changed.loc[future,['tqqq_net_10bps_pct','sqqq_net_10bps_pct']]=50.
    b=compare_sizing(changed,inc,3)
    assert a['selected_rule']==b['selected_rule']
    pd.testing.assert_frame_equal(a['ranking'],b['ranking'])
    assert a['go_no_go']=='NO_VALIDATED_EDGE'


def test_rule_predicates_do_not_read_outcomes():
    df=sample();a=rule_sides(df)
    df['tqqq_net_10bps_pct']=10000
    b=rule_sides(df)
    for key in a:np.testing.assert_array_equal(a[key],b[key])
