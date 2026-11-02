import json
import runpy
import numpy as np
import pandas as pd
import pytest
from trade_lab.daily_screen import UNIVERSE
from trade_lab.execution_refinement import validate_minutes,run_execution_audit,trade_days


def sample():
    data=runpy.run_path('tests/test_research_factory.py')['sample']().head(7).copy()
    data['date']=pd.to_datetime(['2021-01-04','2022-01-03','2023-01-03','2024-01-02','2025-01-02','2025-07-03','2026-01-02']).date
    data['prior_return_1']=-.03;data['prior_close_range_position']=.1;data['prior_volume_shock']=1.
    data['tqqq_net_10bps_pct']=50.
    calendar={};bars={}
    for day in data.date:
        opening=(pd.Timestamp(day).tz_localize('America/New_York')+pd.Timedelta(hours=9,minutes=30)).tz_convert('UTC')
        minutes=210 if day==pd.Timestamp('2025-07-03').date() else 390
        calendar[day]=(opening,opening+pd.Timedelta(minutes=minutes))
        index=pd.date_range(opening,periods=minutes,freq='min')
        x=pd.DataFrame({'timestamp':index,'symbol':'SOXL','open':100.,'high':101.,'low':99.,'close':100.5,'volume':100.})
        bars[day]=x
    return data,calendar,bars


def test_endpoint_audit_keeps_differences_and_halfdays():
    data,cal,bars=sample();result,replay=run_execution_audit(data,UNIVERSE['semiconductors'],cal,bars)
    assert len(result['ranking'])==96
    assert result['coverage']['complete_paths']==7
    assert result['coverage']['endpoint_differences_over_10bps']==7
    event=next(e for e in result['event_audit'] if e['date']=='2025-07-03')
    assert event['expected_minutes']==210 and event['exact_endpoints']
    assert event['source_daily_net_10bps_pct']==50.
    assert event['minute_regular_session_net_10bps_pct']<1
    assert len(replay)==7*16
    json.dumps(result,allow_nan=False)


def test_missing_trade_never_becomes_cash_or_a_selected_complete_replay():
    data,cal,bars=sample();day=data.date.iloc[1];bars[day]=bars[day].drop(index=20)
    result,_=run_execution_audit(data,UNIVERSE['semiconductors'],cal,bars)
    assert result['selected'] is None
    assert all(not row['development_complete'] for row in result['ranking'])
    report=result['reports']['volume_reversal__0.75__both__delay0__time_only']['development_2021_2023']
    assert report['status']=='INCOMPLETE_OBSERVED_SUBSET_ONLY'
    assert report['expected_trades']==3 and report['observed_trades']==2
    assert report['missing_trade_dates']==[str(day)]
    # The high daily winner remains visible despite an incomplete minute path.
    day=data.date.iloc[4];bars[day]=bars[day].iloc[1:]
    result,_=run_execution_audit(data,UNIVERSE['semiconductors'],cal,bars)
    event=next(e for e in result['largest_daily_winners_audit'] if e['date']==str(day))
    assert not event['exact_endpoints'] and event['source_daily_net_10bps_pct']==50.


def test_validation_rejects_duplicates_and_off_session_data():
    data,cal,bars=sample();day=data.date.iloc[0];opening,closing=cal[day];x=bars[day]
    with pytest.raises(ValueError,match='Duplicate'):validate_minutes(pd.concat([x,x.head(1)]),{'SOXL'},opening,closing)
    changed=x.copy();changed.loc[0,'timestamp']=opening-pd.Timedelta(minutes=1)
    with pytest.raises(ValueError,match='Out-of-session'):validate_minutes(changed,{'SOXL'},opening,closing)


def test_later_prices_do_not_change_development_rankings():
    data,cal,bars=sample();a,_=run_execution_audit(data,UNIVERSE['semiconductors'],cal,bars)
    changed={day:x.copy() for day,x in bars.items()}
    for day,x in changed.items():
        if day.year>=2024:x.loc[x.index[-1],['high','close']]=200.
    b,_=run_execution_audit(data,UNIVERSE['semiconductors'],cal,changed)
    assert a['ranking']==b['ranking']


def test_both_touch_uses_stop_first_and_costs_remain_adverse():
    data,cal,bars=sample();day=data.date.iloc[0]
    bars[day].loc[0,['high','low']]=[110.,90.]
    _,replay=run_execution_audit(data,UNIVERSE['semiconductors'],cal,bars)
    row=replay.loc[replay.date.eq(day)&replay.delay.eq(0)&replay.exit.eq('tp2_sl2')].iloc[0]
    assert row.ambiguous_10bps and row.net_10bps_pct<0
    assert row.net_50bps_pct<row.net_10bps_pct
