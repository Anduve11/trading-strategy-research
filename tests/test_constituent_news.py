from datetime import date
import pandas as pd
import pytest
from trade_lab.constituents import validate_filing_facts,asof_filing,aggregate_filing_features,CURRENT_SECURITIES
from trade_lab.news_lab import lexicon_score,aggregate_news_asof,fetch_news_chunk,derived_key


def test_news_scoring_and_strict_predecision():
    assert lexicon_score('Apple beats estimates and raises guidance')>0
    assert lexicon_score('Company cuts guidance after revenue miss')<0
    assert lexicon_score('Tech business report')==0
    et='America/New_York'
    decisions=pd.DataFrame([{'date':date(2024,6,3),'timestamp':pd.Timestamp('2024-06-03 09:50',tz=et)}])
    news=pd.DataFrame([
        {'created_at':'2024-06-03T13:44:00Z','score':1.,'is_qqq':0,'company_symbols':1},
        {'created_at':'2024-06-03T13:46:00Z','score':-1.,'is_qqq':1,'company_symbols':1},
        {'created_at':'2024-06-03T13:50:00Z','score':-1.,'is_qqq':0,'company_symbols':1}])
    result=aggregate_news_asof(news,decisions,delay_minutes=5)
    assert result.news_count_72h.iloc[0]==1
    assert result.news_score_mean_72h.iloc[0]==1
    assert result.news_qqq_count_72h.iloc[0]==0


def test_news_no_articles_and_invalid_score():
    decisions=pd.DataFrame([{'date':date(2024,6,3),'timestamp':pd.Timestamp('2024-06-03 13:50:00Z')}])
    r=aggregate_news_asof(pd.DataFrame(),decisions)
    assert r.iloc[0].news_count_72h==0
    assert r.iloc[0].news_score_mean_72h==0
    with pytest.raises(ValueError, match='Invalid news score'):
        aggregate_news_asof(pd.DataFrame([{'created_at':'2024-06-03T13:00:00Z','score':2.,'is_qqq':0,'company_symbols':0}]),decisions)


def test_sec_filing_asof_includes_only_prior_public_data():
    companyfacts={'facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':[
       {'val':10,'end':'2023-03-31','filed':'2023-05-01','form':'10-Q','accn':'A'},
       {'val':100,'end':'2023-06-30','filed':'2023-08-10','form':'10-Q','accn':'B'},
       {'val':500,'end':'2023-06-30','filed':'2024-03-01','form':'10-K','accn':'C'}]}}}}}
    facts=validate_filing_facts(companyfacts,'net_income')
    assert asof_filing(facts,date(2023,5,1)) is None
    assert asof_filing(facts,date(2023,5,2))['value']==10
    assert asof_filing(facts,date(2023,8,10))['value']==10
    assert asof_filing(facts,date(2023,8,11))['value']==100
    assert asof_filing(facts,date(2024,3,2))['value']==500


def test_companyweights_current_only_and_issuer_dedup():
    assert len(CURRENT_SECURITIES)==10
    assert CURRENT_SECURITIES['GOOG']>0 and CURRENT_SECURITIES['GOOGL']>0
    decisions=pd.DataFrame({'date':[date(2023,1,1)]})
    features=aggregate_filing_features(decisions,{})
    assert features.issuer_filing_coverage.iloc[0]==0
    assert pd.isna(features.issuer_profit_margin_mean.iloc[0])


class FakeNewsResponse:
    def __init__(self,status,body):
        self.status_code=status;self.ok=status==200;self._body=body
    def json(self):return self._body


class FakeNewsSession:
    def __init__(self,fail=False):self.count=0;self.fail=fail
    def get(self,url,params,headers,timeout):
        self.count+=1
        if self.fail:return FakeNewsResponse(401,{})
        if self.count==1:return FakeNewsResponse(200,{'news':[
          {'id':1,'created_at':'2024-06-01T12:00:00Z','headline':'company raises guidance','symbols':['AAPL']}],
          'next_page_token':'next'})
        return FakeNewsResponse(200,{'news':[
          {'id':1,'created_at':'2024-06-01T12:00:00Z','headline':'company raises guidance','symbols':['AAPL']},
          {'id':2,'created_at':'2024-06-02T12:00:00Z','headline':'misses estimates','symbols':['MSFT']}],
          'next_page_token':None})


def test_pagination_and_dedupe():
    result=fetch_news_chunk('fake','fake',date(2024,6,1),date(2024,7,1),session=FakeNewsSession(),rate_delay=0)
    assert len(result)==2
    assert result.score.iloc[0]>0 and result.score.iloc[1]<0
    assert 'static-2026-basket' in derived_key(date(2024,6,1))
    with pytest.raises(RuntimeError,match='HTTP 401'):
        fetch_news_chunk('fake','fake',date(2024,6,1),date(2024,7,1),session=FakeNewsSession(fail=True),rate_delay=0)


def test_out_of_interval_updated_story_is_excluded_not_retimestamped():
    class OldNews:
        def get(self,url,params,headers,timeout):
            return FakeNewsResponse(200,{'news':[
                {'id':111,'created_at':'2024-05-25T01:00:00Z','headline':'old news updated later','symbols':['AAPL']},
                {'id':112,'created_at':'2024-06-01T11:00:00Z','headline':'earnings beat','symbols':['AAPL']},
                {'id':113,'created_at':'2024-07-01T00:00:00Z','headline':'outside end','symbols':['AAPL']}],
                'next_page_token':None})
    data=fetch_news_chunk('fake','fake',date(2024,6,1),date(2024,7,1),session=OldNews(),rate_delay=0)
    assert data.id.tolist()==['112']


def test_news_archive_never_requests_months_after_frozen_price_history(monkeypatch):
    import scripts.news_research as study
    requested=[]
    def cached(archive,first):
        requested.append(first)
        return pd.DataFrame({'cached':[True]})
    monkeypatch.setattr(study,'load_features',cached)
    class NoPriceDownloads:
        def load(self,month):
            raise AssertionError('Cached news must not request any ETF history')
    study.archive_years(NoPriceDownloads(),'unused','unused',2025,2026)
    assert len(requested)==21
    assert max(requested)==date(2026,9,1)
    assert date(2026,10,1) not in requested
