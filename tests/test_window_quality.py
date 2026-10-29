import numpy as np
import pandas as pd
import pytest
from trade_lab.data import generate_synthetic
from trade_lab.edge_research import extract_decisions, PRICE_FEATURES
from trade_lab.window_quality import execution_window, window_outcomes
from scripts.universe_research import eligible_policies


def prices():
    index = pd.date_range('2024-06-03T14:00Z',periods=30,freq='min')
    return pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':np.arange(30)+100.,'volume':10.},index=index)


def test_linear_interpolation_is_bounded_flagged_and_does_not_change_observations():
    x = prices()
    broken = x.drop(x.index[5:7])
    primary,n = execution_window(broken,x.index[0],30)
    assert primary is None and n == 2
    diagnostic,n = execution_window(broken,x.index[0],30,interpolate=True)
    assert n == 2
    assert diagnostic.loc[x.index[5],'close'] == 105.
    assert diagnostic.loc[x.index[6],'volume'] == 0
    pd.testing.assert_frame_equal(diagnostic.loc[broken.index],broken,check_dtype=False)
    for index in (x.index[0:1],x.index[-1:],x.index[5:8]):
        assert execution_window(x.drop(index),x.index[0],30,interpolate=True)[0] is None


def test_interpolation_rejects_overnight_and_partial_ohlc_missing():
    x=prices()
    x.iloc[5,x.columns.get_loc('high')] = np.nan
    assert execution_window(x,x.index[0],30,True)[0] is None
    with pytest.raises(ValueError,match='Cross-session'):
        execution_window(x,pd.Timestamp('2024-06-03 23:50',tz='America/New_York'),30,True)


@pytest.fixture(scope='module')
def market():return generate_synthetic(55)


def test_missing_unrelated_etf_minute_no_longer_drops_entire_session(market):
    features,_,_=extract_decisions(market)
    first=features.iloc[0]
    changed=market.drop(market.index[market.symbol.eq('SQQQ') & market.timestamp.eq(first.timestamp.normalize()+pd.Timedelta(hours=19))])
    revised,_,_=extract_decisions(changed,require_full_pair=False)
    before=features.loc[(features.date==first.date)&(features.decision_minute=='09:59')].iloc[0]
    after=revised.loc[(revised.date==first.date)&(revised.decision_minute=='09:59')].iloc[0]
    np.testing.assert_allclose(before[list(PRICE_FEATURES)].astype(float),after[list(PRICE_FEATURES)].astype(float))
    observed,shadow,_=window_outcomes(changed,revised.loc[(revised.date==first.date)&(revised.decision_minute=='09:59')])
    assert len(observed)==8 and shadow.empty


def test_missing_proxy_prefix_is_rejected_but_unrelated_future_gap_is_allowed(market):
    features,_,_=extract_decisions(market)
    first=features.iloc[0]
    for offset,expect in [(-5,False),(200,True)]:
        stamp=first.timestamp+pd.Timedelta(minutes=offset)
        changed=market.drop(market.index[market.symbol.eq('QQQ')&market.timestamp.eq(stamp)])
        f,_,_=extract_decisions(changed,require_full_pair=False)
        found=((f.date==first.date)&(f.decision_minute==first.decision_minute)).any()
        assert bool(found)==expect


def test_imputed_windows_never_enter_primary_training_rows(market):
    features,_,_=extract_decisions(market)
    first=features.iloc[0]
    stamp=first.timestamp+pd.Timedelta(minutes=6)
    changed=market.drop(market.index[market.symbol.eq('TQQQ')&market.timestamp.eq(stamp)])
    primary,shadow,counts=window_outcomes(changed,features.head(1))
    assert primary.empty
    assert len(shadow)==8 and shadow.imputed_minutes.eq(1).all()
    assert shadow.data_quality.eq('INTERPOLATION_SENSITIVITY_ONLY').all()
    assert counts['interpolated_only_windows']==2


def test_policy_coverage_cannot_be_hidden_by_other_times():
    dates=pd.bdate_range('2019-04-01','2026-09-30').date
    a=pd.DataFrame({'date':dates,'decision_minute':'09:59','horizon':30,'exit_policy':'time_only'})
    b=a.iloc[:5].assign(decision_minute='14:29')
    x=pd.concat([a,b])
    candidate,control=eligible_policies(x,x)
    assert set(candidate.decision_minute)=={'09:59'}
    pd.testing.assert_frame_equal(candidate,control)
