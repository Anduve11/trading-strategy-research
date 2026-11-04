import runpy
import numpy as np
import pandas as pd
import pytest
from trade_lab.exit_management import path_return,run_exit_management
from trade_lab.daily_screen import UNIVERSE


def prices(rows):
    opening=pd.Timestamp('2025-01-02T14:30Z')
    frame=pd.DataFrame(rows,columns=['open','high','low','close'],index=pd.date_range(opening,periods=len(rows),freq='min'))
    frame['volume']=100.
    return frame,opening,opening+pd.Timedelta(minutes=len(rows))


def test_half_sale_keeps_remaining_equity_and_does_not_reinvest():
    frame,o,c=prices([[100,104,99,103],[103,121,102,120]])
    full=path_return(frame,o,c,0,'close',0,.2,3)
    partial=path_return(frame,o,c,0,'half3',0,.2,3)
    assert full['net_pct']==pytest.approx(20.)
    assert partial['net_pct']==pytest.approx(11.5)
    assert partial['target_touched']
    stressed=path_return(frame,o,c,0,'half3',50,.2,3)
    assert stressed['net_pct']<partial['net_pct']


def test_trailing_uses_worst_compatible_order_and_gap_through():
    frame,o,c=prices([[100,104,100,103],[103,110,100,108],[108,109,106,107]])
    result=path_return(frame,o,c,0,'trail5',0,.2,3)
    assert result['ambiguous_path']
    assert result['net_pct']==pytest.approx(4.5)
    frame,o,c=prices([[100,101,99,100],[90,91,89,90],[90,91,89,90]])
    result=path_return(frame,o,c,0,'trail5',0,.2,3)
    assert result['net_pct']==pytest.approx(-10.)


def test_missing_bars_are_required_only_when_they_can_change_outcome():
    frame,o,c=prices([[100,101,99,100],[100,101,99,100],[100,101,99,101]])
    missing=frame.drop(frame.index[1])
    assert path_return(missing,o,c,0,'close',0,.2,3)['net_pct']==pytest.approx(1.)
    assert path_return(missing,o,c,0,'half3',0,.2,3) is None
    assert path_return(missing,o,c,0,'trail5',0,.2,3) is None
    frame.iloc[0,frame.columns.get_loc('high')]=104
    partial=path_return(frame.drop(frame.index[1]),o,c,0,'half3',0,.2,3)
    assert partial['net_pct']==pytest.approx(2.)
    # A stop already triggered before a later missing bar remains observable.
    frame.iloc[0,frame.columns.get_loc('low')]=90
    stopped=path_return(frame.drop(frame.index[1]),o,c,0,'trail5',0,.2,3)
    assert stopped is not None and stopped['net_pct']==pytest.approx(-5.)


def test_timed_endpoints_and_volatility_clip():
    frame,o,c=prices([[100,101,99,100],[100,101,99,100],[100,101,99,100]])
    assert path_return(frame,o,c,5,'close',10,.2,3) is None
    assert path_return(frame,o,c,0,'hold30',10,.2,3)['net_pct']<0
    assert path_return(frame,o,c,0,'trail2sigma',0,.001,3)['trailing_fraction']==.02
    assert path_return(frame,o,c,0,'trail2sigma',0,2.,3)['trailing_fraction']==.12


def test_future_prices_cannot_change_development_exit_selection():
    source=runpy.run_path('tests/test_execution_refinement.py')['sample']
    data,calendar,bars=source()
    a,_=run_exit_management(data,UNIVERSE['semiconductors'],calendar,bars)
    changed={day:x.copy() for day,x in bars.items()}
    for day,x in changed.items():
        if day.year>=2024:x.loc[x.index[-1],['high','close']]=200.
    b,_=run_exit_management(data,UNIVERSE['semiconductors'],calendar,changed)
    assert len(a['ranking'])==len(a['reports'])==54
    assert a['ranking']==b['ranking'] and a['selected']==b['selected']
    report=a['reports']['both__delay5__half3']['inspected_2025_2026']
    assert 'matched_close_control' in report and 'matched_candidate' in report
