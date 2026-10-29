from datetime import date,timedelta
import pandas as pd
import numpy as np
from trade_lab.macro import append_previous_day_macro,MACRO_FEATURES


def test_only_prior_day_macro_may_enter_model():
    days=pd.bdate_range('2026-09-01',periods=24)
    obs=pd.DataFrame({'date':days.date,'VIXCLS':[20.]*24,'DGS10':[4.]*24,'DGS2':[3.]*24})
    decisions=pd.DataFrame({'date':[date(2026,9,30)],'timestamp':['2026-09-30T13:50:00Z']})
    baseline=append_previous_day_macro(decisions,obs)
    changed=obs.copy()
    changed.loc[changed.date==date(2026,9,30),'VIXCLS']=10000.
    again=append_previous_day_macro(decisions,changed)
    assert baseline.prior_vix.iloc[0]==again.prior_vix.iloc[0]
    assert baseline.prior_vix.iloc[0]==20.
    assert baseline.prior_10y_2y_spread.iloc[0]==1.
    assert all(c in baseline for c in MACRO_FEATURES)


def test_market_features_do_not_forward_fill_a_year():
    market=pd.DataFrame({'date':[date(2020,1,2)],'VIXCLS':[15.], 'DGS10':[2.], 'DGS2':[1.]})
    decision=pd.DataFrame({'date':[date(2026,2,1)],'timestamp':['2026-02-01T14:50:00Z']})
    out=append_previous_day_macro(decision,market)
    assert np.isnan(out.prior_vix.iloc[0])