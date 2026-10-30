import numpy as np
import pandas as pd
from trade_lab.fragility import diagnostics


def sample():
    x=np.array([1.]*29+[30.])
    return pd.DataFrame({'date':pd.bdate_range('2025-01-01',periods=30).date,
      'tqqq_net_10bps_pct':x,'sqqq_net_10bps_pct':-x/2,
      'tqqq_net_20bps_pct':x-.2,'sqqq_net_20bps_pct':-x/2-.2})


def test_fragility_reports_lucky_day_dependence_without_changing_source():
    df=sample();before=df.copy(deep=True)
    r=diagnostics(df,np.ones(30,dtype=int),1.,repetitions=100)
    assert r['skip_best_winning_sessions']['1']['return_pct']<r['baseline_10bps']['return_pct']
    assert r['skip_best_winning_sessions']['5']['active_sessions']==25
    assert r['top3_share_of_positive_position_returns']>.5
    pd.testing.assert_frame_equal(df,before)


def test_random_diagnostics_reproducible_and_higher_costs_worse():
    df=sample();sides=np.tile([1,0,-1],10)
    a=diagnostics(df,sides,.5,repetitions=100)
    b=diagnostics(df,sides,.5,repetitions=100)
    assert a==b
    assert a['stress_20bps']['return_pct']<a['baseline_10bps']['return_pct']
    assert a['signal_delay_eligible_observations']['2']['active_sessions']==19


def test_no_trade_strategy_has_no_fabricated_winners():
    r=diagnostics(sample(),np.zeros(30,dtype=int),1.,repetitions=100)
    assert r['baseline_10bps']['return_pct']==0
    assert r['skip_best_winning_sessions']['3']['removed_winners']==0
    assert r['top3_share_of_positive_position_returns'] is None
    assert r['random_missing_trades']['0.25']['return_pct_p05_median_p95']==[0.,0.,0.]
