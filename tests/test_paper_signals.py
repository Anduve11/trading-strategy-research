import copy
import pandas as pd
import pytest
import exchange_calendars as xcals
from trade_lab.daily_screen import UNIVERSE
from trade_lab.paper_signals import target_session,freeze_signal,reconcile_signal,latest_expected_started_session


def sample(now='2026-11-03T13:00Z'):
    cal=xcals.get_calendar('XNYS',start='2025-01-01',end='2027-01-01')
    target,prior,history,final=target_session(cal.schedule,pd.Timestamp(now))
    times=[pd.Timestamp(d).tz_localize('America/New_York').tz_convert('UTC') for d in history]
    x=pd.DataFrame({'timestamp':times,'symbol':'SOXX','open':100.,'high':110.,'low':80.,'close':100.,'volume':100.})
    x.loc[x.index[-1],['close','volume']]=[90.,1000.]
    return cal,x,target,prior


def test_signal_is_frozen_before_entry_and_identity_is_stable():
    cal,x,target,prior=sample()
    a=freeze_signal(x,'semiconductors',UNIVERSE['semiconductors'],cal.schedule,pd.Timestamp('2026-11-03T13:00Z'),'abc')
    b=freeze_signal(x,'semiconductors',UNIVERSE['semiconductors'],cal.schedule,pd.Timestamp('2026-11-03T13:01Z'),'abc')
    assert a['side']==1 and a['symbol']=='SOXL' and a['allocation_fraction']==1
    assert a['target_session']=='2026-11-03' and a['source_last_session']=='2026-11-02'
    assert pd.Timestamp(a['created_at'])<pd.Timestamp(a['target_open'])-pd.Timedelta(minutes=5)
    assert a['prediction_id']==b['prediction_id'] and a['no_live_orders']


def test_current_or_future_proxy_bar_is_rejected():
    cal,x,_,_=sample();bad=x.copy()
    bad.loc[bad.index[-1],'timestamp']=pd.Timestamp('2026-11-03T05:00Z')
    with pytest.raises(ValueError,match='every required'):freeze_signal(bad,'semiconductors',UNIVERSE['semiconductors'],cal.schedule,pd.Timestamp('2026-11-03T13:00Z'),'abc')


def test_no_premature_prediction_from_current_incomplete_daily_bar():
    cal,x,_,_=sample('2026-11-02T18:00Z')
    with pytest.raises(ValueError,match='not yet eligible'):freeze_signal(x,'semiconductors',UNIVERSE['semiconductors'],cal.schedule,pd.Timestamp('2026-11-02T18:00Z'),'abc')


def test_cash_and_exact_endpoint_reconciliation():
    cal,x,_,_=sample()
    record=freeze_signal(x,'semiconductors',UNIVERSE['semiconductors'],cal.schedule,pd.Timestamp('2026-11-03T13:00Z'),'abc')
    opening=pd.Timestamp(record['target_open']);closing=pd.Timestamp(record['target_close'])
    bars=pd.DataFrame({'timestamp':[opening,opening+pd.Timedelta(minutes=5),closing-pd.Timedelta(minutes=1)],
        'symbol':'SOXL','open':[100.,101.,110.],'high':111.,'low':99.,'close':[100.,101.,110.],'volume':100.})
    result=reconcile_signal(record,bars)
    assert result['status']=='OBSERVED_ENDPOINTS_HYPOTHETICAL_FILL'
    assert result['returns']['0']['10']>result['returns']['5']['10']
    assert result['returns']['0']['50']<result['returns']['0']['10']
    assert reconcile_signal(record,bars.head(2))['status']=='MISSING_EXACT_ENDPOINTS'
    late=copy.deepcopy(record);late['created_at']=record['target_open']
    with pytest.raises(ValueError,match='deadline'):reconcile_signal(late,bars)
    x['close']=100.;x['volume']=100.
    cash=freeze_signal(x,'semiconductors',UNIVERSE['semiconductors'],cal.schedule,pd.Timestamp('2026-11-03T13:00Z'),'abc')
    assert cash['side']==0 and cash['allocation_fraction']==0
    assert reconcile_signal(cash,pd.DataFrame())['status']=='CASH'


def test_halfday_and_holiday_use_exchange_schedule():
    cal,_,target,prior=sample('2026-11-27T13:00Z')
    assert str(pd.Timestamp(target).date())=='2026-11-27'
    assert str(pd.Timestamp(prior).date())=='2026-11-25'
    assert cal.schedule.loc[target,'close']==pd.Timestamp('2026-11-27T18:00Z')


def test_health_check_reports_started_session_without_backfilling_it():
    cal,_,_,_=sample()
    assert latest_expected_started_session(cal.schedule,pd.Timestamp('2026-11-03T13:00Z')) is None
    assert latest_expected_started_session(cal.schedule,pd.Timestamp('2026-11-03T15:00Z'))=='2026-11-03'
    assert latest_expected_started_session(cal.schedule,pd.Timestamp('2026-11-04T13:00Z'))=='2026-11-03'
    target,_,_,_=target_session(cal.schedule,pd.Timestamp('2026-11-03T15:00Z'))
    assert str(pd.Timestamp(target).date())=='2026-11-04'
