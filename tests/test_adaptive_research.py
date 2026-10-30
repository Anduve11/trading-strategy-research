import runpy
import numpy as np
import pandas as pd
import trade_lab.adaptive_research as adaptive
from trade_lab.daily_screen import FEATURES


def data():
    df=runpy.run_path('tests/test_edge_research.py')['mock_research_data']()
    for side in ('tqqq','sqqq'):df[f'{side}_net_20bps_pct']=df[f'{side}_net_10bps_pct']-.2
    return df


def fake_predict(train,test,spec,model):
    assert train.date.max()<test.date.min()
    return np.tile(train[['tqqq_net_5bps_pct','sqqq_net_5bps_pct']].mean().to_numpy(),(len(test),1))


def test_quarter_predictions_do_not_see_current_quarter_labels(monkeypatch):
    monkeypatch.setattr(adaptive,'predict_profit',fake_predict)
    df=data();spec={'columns':list(FEATURES),'macro_weight':1.}
    before,forecast=adaptive.quarterly_forecasts(df,spec,'rolling504')
    changed=df.copy();q=pd.to_datetime(changed.date).dt.to_period('Q')
    changed.loc[q.eq(pd.Period('2024Q1')),['tqqq_net_10bps_pct','sqqq_net_10bps_pct']]=500
    after,new=adaptive.quarterly_forecasts(changed,spec,'rolling504')
    mask=pd.to_datetime(before.date).dt.to_period('Q').eq(pd.Period('2024Q1'))
    np.testing.assert_array_equal(forecast[mask],new[mask])
    mask2=pd.to_datetime(before.date).dt.to_period('Q').eq(pd.Period('2024Q2'))
    assert not np.allclose(forecast[mask2],new[mask2])


def test_agreement_requires_both_models_and_cushion():
    forecasts=np.array([[[.3,-.1],[-.1,.3]],[[.3,-.1],[.2,-.1]],[[.01,0],[.3,-.1]]])
    assert adaptive.select_sides(forecasts,.1,'agreement').tolist()==[0,1,0]


def test_calendar_uses_schedule_not_price_outcomes():
    days=pd.bdate_range('2024-01-01','2024-03-29')
    df=pd.DataFrame({'date':[pd.Timestamp('2024-01-30').date()]})
    out=adaptive.append_calendar(df,days)
    assert out.month_end_distance.iloc[0]==1
    assert out.quarter_end_distance.iloc[0]==59


def test_later_labels_do_not_change_selection(monkeypatch):
    monkeypatch.setattr(adaptive,'predict_profit',fake_predict)
    df=data();spec={'price':{'columns':list(FEATURES),'macro_weight':1.}}
    before=adaptive.adaptive_search(df,spec)
    changed=df.copy();future=pd.to_datetime(changed.date).dt.year>=2024
    changed.loc[future,['tqqq_net_10bps_pct','sqqq_net_10bps_pct']]=500
    after=adaptive.adaptive_search(changed,spec)
    assert before['selected']==after['selected']
    pd.testing.assert_frame_equal(before['ranking'],after['ranking'])


def test_selected_strategy_reports_primary_and_higher_costs(monkeypatch):
    monkeypatch.setattr(adaptive,'predict_profit',lambda train,test,spec,model:np.tile([.3,-.2],(len(test),1)))
    result=adaptive.adaptive_search(data(),{'price':{'columns':list(FEATURES),'macro_weight':1.}})
    assert result['selected'] is not None
    report=result['reports']['inspected_2024']
    assert report['primary_10bps']['trades']>100
    assert report['stress_20bps']['return_pct']<report['primary_10bps']['return_pct']
    assert result['go_no_go']=='NO_VALIDATED_EDGE'
