import runpy
import numpy as np
import pandas as pd
from trade_lab.context_factors import context_features,build_experiment,CONTEXT,BEHAVIOR
from trade_lab.daily_screen import FEATURES,UNIVERSE


def fixture():
    raw,days=runpy.run_path('tests/test_daily_screen.py')['sample']()
    q=raw.loc[raw.symbol.eq('QQQ')].copy()
    proxies=pd.concat([q.assign(symbol=s,date=q.timestamp.dt.date) for s in ['QQQ','SPY','IWM','SOXX','TLT','GLD']],ignore_index=True)
    return raw,days,proxies


def test_context_and_behavior_are_strictly_lagged():
    raw,days,proxies=fixture()
    context=context_features(proxies,days)
    before=build_experiment(raw,UNIVERSE['nasdaq3'],days,context,'day')
    day=before.date.iloc[3]
    altered=proxies.copy();altered.loc[altered.date>=day,'close']*=1.5
    c=context_features(altered,days)
    changed=raw.copy();changed.loc[changed.timestamp.dt.date>=day,['open','high','low','close']]*=1.5
    after=build_experiment(changed,UNIVERSE['nasdaq3'],days,c,'day')
    cols=[*FEATURES,*CONTEXT,*BEHAVIOR]
    np.testing.assert_allclose(before.loc[before.date.eq(day),cols],after.loc[after.date.eq(day),cols])


def test_overnight_uses_next_scheduled_open_and_observed_close():
    raw,days,proxies=fixture();context=context_features(proxies,days)
    result=build_experiment(raw,UNIVERSE['nasdaq3'],days,context,'overnight')
    first=result.iloc[0];i=list(days.date).index(first.date)
    t=raw.loc[raw.symbol.eq('TQQQ')].reset_index(drop=True)
    expected=100*(t.iloc[i+1].open*.9995/(t.iloc[i].close*1.0005)-1)
    assert np.isclose(first.tqqq_net_5bps_pct,expected)
    assert days[-1].date() not in set(result.date)
    changed=raw.loc[~(raw.symbol.eq('TQQQ')&raw.timestamp.dt.date.eq(days[i+1].date()))]
    damaged=build_experiment(changed,UNIVERSE['nasdaq3'],days,context,'overnight')
    assert first.date not in set(damaged.date)


def test_cross_market_missing_observations_not_forward_filled():
    _,days,proxies=fixture()
    day=days[100].date()
    proxies=proxies.loc[~(proxies.symbol.eq('TLT')&proxies.date.eq(day))]
    result=context_features(proxies,days)
    assert pd.isna(result.loc[result.date.eq(days[101].date()),'bonds_5']).all()
