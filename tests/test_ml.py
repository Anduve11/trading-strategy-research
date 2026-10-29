from datetime import date
import numpy as np
import pandas as pd
import pytest
from trade_lab.data import generate_synthetic
from trade_lab.ml import extract_month, decide, evaluate_decisions, split_periods
from trade_lab.news import aggregate_predecision_sentiment


def test_ml_features_only_known_before_entry():
    bars=generate_synthetic(66)
    features,_=extract_month(bars)
    assert len(features)>10
    assert features.target_up.isin([0,1]).all()
    assert 'tqqq_net_pct' not in features.columns
    altered=bars.copy()
    affected=features.iloc[0].date
    later=(altered.timestamp.dt.tz_convert('America/New_York').dt.date == affected) & (
        altered.timestamp.dt.tz_convert('America/New_York').dt.strftime('%H:%M') >= '11:00')
    # Edit post-label bars only: existing decision-time features must remain unchanged.
    altered.loc[later,'close'] *= 1.5
    first,_=extract_month(altered)
    cols=['overnight_gap','opening20_return','opening20_range','lag_return_5','opening20_volume_ratio']
    assert np.allclose(features.iloc[0][cols].astype(float),first.iloc[0][cols].astype(float))


def test_decision_and_cost_adjusted_account():
    p=np.array([.63,.50,.35,.70])
    assert decide(p,.6).tolist()==[1,0,-1,1]
    df=pd.DataFrame({'tqqq_net_pct':[1,2,-1,0.5], 'sqqq_net_pct':[-1,-2,2,-0.5]})
    perf=evaluate_decisions(df,decide(p,.6),allocation=.1,initial=10000)
    assert perf['trades']==3
    assert perf['return_pct']>0


def test_sentiment_does_not_include_future_news():
    ds=pd.DataFrame([{'date':date(2026,9,1),'timestamp':'2026-09-01T13:50:00Z'}])
    news=pd.DataFrame([
        {'created_at':'2026-09-01T13:30:00Z','headline':'Factual headline','symbols':'QQQ','source':'test','sentiment':-0.4},
        {'created_at':'2026-09-01T13:48:00Z','headline':'Headline too late (5-min lag)','symbols':'QQQ','source':'test','sentiment':1.0},
        {'created_at':'2026-09-01T15:00:00Z','headline':'Future headline','symbols':'QQQ','source':'test','sentiment':1.0},
    ])
    agg=aggregate_predecision_sentiment(news,ds,delay_minutes=5)
    assert agg.iloc[0].news_articles==1
    assert agg.iloc[0].news_sentiment==-0.4
    with pytest.raises(ValueError,match='Sentiment unavailable'):
        aggregate_predecision_sentiment(news.drop(columns='sentiment'),ds)