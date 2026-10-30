import numpy as np
import pandas as pd
import pytest
from trade_lab.reversal_research import reversal_sides,run_reversals


def sample():
    dates=pd.bdate_range('2021-01-01','2026-09-30')
    n=len(dates)
    return pd.DataFrame({'date':dates,'prior_return_1':np.resize([-.02,.02],n),
       'prior_vol_20':.2,'prior_return_20':.1,'prior_sma50_gap':.05,
       'prior_efficiency20':.1,'tqqq_net_10bps_pct':.3,'sqqq_net_10bps_pct':-.1,
       'tqqq_net_20bps_pct':.1,'sqqq_net_20bps_pct':-.3})


def test_filters_and_threshold_neighborhood():
    data=sample().head(4)
    data['prior_return_1']=[-.011,.011,-.02,.02]
    sides=reversal_sides(data)
    assert len(sides)==12
    np.testing.assert_array_equal(sides['sigma_1_both'],[0,0,1,-1])
    np.testing.assert_array_equal(sides['sigma_1_bull_only'],[0,0,1,0])
    np.testing.assert_array_equal(sides['sigma_1_trend_aligned'],[0,0,1,0])
    assert np.count_nonzero(sides['sigma_0.75_both'])>=np.count_nonzero(sides['sigma_1.25_both'])
    data['prior_efficiency20']=.5
    assert not reversal_sides(data)['sigma_1_low_directionality'].any()


def test_later_outcomes_cannot_change_selection_or_rank():
    data=sample();a=run_reversals(data)
    data.loc[data.date.dt.year>=2024,['tqqq_net_20bps_pct','sqqq_net_20bps_pct']]=100
    b=run_reversals(data)
    assert a['ranking']==b['ranking']
    assert a['selected_strategy']==b['selected_strategy']
    report=a['reports']['inspected_2025_2026']['sigma_1_bull_only']
    assert report['selection_cost_20bps']['return_pct']<report['primary_10bps']['return_pct']


def test_missing_predictors_rejected_and_outcomes_not_predictors():
    data=sample();a=reversal_sides(data)
    data['tqqq_net_10bps_pct']=999
    for name,sides in reversal_sides(data).items():np.testing.assert_array_equal(sides,a[name])
    data.loc[0,'prior_vol_20']=np.nan
    with pytest.raises(ValueError,match='finite'):reversal_sides(data)
