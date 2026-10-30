import numpy as np
import pandas as pd
import pytest
from trade_lab.daily_screen import UNIVERSE,FEATURES,validate_daily,build_daily


def sample():
    dates=pd.bdate_range('2018-01-01',periods=400)
    rows=[]
    for symbol,base in [('QQQ',100.),('TQQQ',30.),('SQQQ',20.)]:
        for i,day in enumerate(dates):
            op=base*(1+.0003*i+ .002*np.sin(i))
            close=op*(1+.001*np.cos(i))
            rows.append(dict(timestamp=day.tz_localize('America/New_York'),symbol=symbol,open=op,high=max(op,close)*1.01,low=min(op,close)*.99,close=close,volume=1000))
    return pd.DataFrame(rows),dates


def test_daily_features_cannot_see_current_or_future_prices():
    raw,days=sample();pair=UNIVERSE['nasdaq3']
    before=build_daily(raw,pair,days)
    day=before.date.iloc[5]
    changed=raw.copy()
    mask=changed.timestamp.dt.date>=day
    changed.loc[mask,['open','high','low','close']]*=1.5
    after=build_daily(changed,pair,days)
    np.testing.assert_allclose(before.loc[before.date.eq(day),list(FEATURES)],after.loc[after.date.eq(day),list(FEATURES)])


def test_daily_gaps_stay_missing_and_costs_worsen_returns():
    raw,days=sample();pair=UNIVERSE['nasdaq3']
    before=build_daily(raw,pair,days);day=before.date.iloc[5]
    raw=raw.loc[~(raw.symbol.eq('SQQQ')&raw.timestamp.dt.date.eq(day))]
    after=build_daily(raw,pair,days)
    assert day not in set(after.date)
    assert (after.tqqq_net_20bps_pct<after.tqqq_net_10bps_pct).all()
    assert (after.tqqq_net_10bps_pct<after.tqqq_net_5bps_pct).all()


def test_daily_universe_and_input_integrity():
    assert len(UNIVERSE)==18
    raw,_=sample()
    with pytest.raises(ValueError,match='Duplicate'):
        validate_daily(pd.concat([raw,raw.iloc[:1]]),UNIVERSE['nasdaq3'])
    raw.iloc[0,raw.columns.get_loc('high')]=0
    with pytest.raises(ValueError):validate_daily(raw,UNIVERSE['nasdaq3'])
