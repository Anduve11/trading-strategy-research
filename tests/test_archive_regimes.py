from datetime import date
import pandas as pd
import numpy as np
import pytest

from trade_lab.archive import (ArchivedFetcher, SupabaseArchive, encode_bars, decode_bars,
                               month_key, month_windows)
from trade_lab.data import ET, generate_synthetic
from trade_lab.regimes import classify_sessions, summarize_regime_trades


def for_month(bars, target_year, target_month):
    desired = pd.Timestamp(date(target_year, target_month, 2), tz=ET)
    actual = bars.timestamp.min().tz_convert(ET).normalize()
    changed = bars.copy()
    changed['timestamp'] = changed['timestamp'] + (desired - actual)
    return changed


def test_partition_and_compressed_roundtrip():
    assert list(month_windows(date(2025,12,12),date(2026,2,4))) == [
        (date(2025,12,1),date(2025,12,31)),
        (date(2026,1,1),date(2026,1,31)),
        (date(2026,2,1),date(2026,2,28))]
    assert month_key(date(2026,1,1)).endswith('2026-01.csv.gz')
    sample = for_month(generate_synthetic(2),2026,8)
    result = decode_bars(encode_bars(sample),date(2026,8,1))
    assert len(result)==len(sample)
    assert result.symbol.tolist()==sample.symbol.tolist()
    assert np.allclose(result.close,sample.close)
    with pytest.raises(ValueError,match='wrong month'):
        decode_bars(encode_bars(sample),date(2025,8,1))


class DummyResponse:
    def __init__(self, status, content=b''):
        self.status_code=status
        self.content=content
        self.text=content.decode('utf-8','ignore') if isinstance(content,bytes) else content
        self.ok=200<=status<300


class MemoryHTTP:
    def __init__(self):
        self.storage={}
    def get(self,url,headers,timeout):
        # Supabase may return HTTP 400 although the JSON reports a missing
        # object (statusCode 404). This is the production regression case.
        return (DummyResponse(200,self.storage[url]) if url in self.storage else
                DummyResponse(400,b'{"statusCode":"404","error":"not_found","message":"Object not found","code":"NoSuchKey"}'))
    def post(self,url,headers,data,timeout):
        if url in self.storage:
            return DummyResponse(400,b'{"statusCode":"409","code":"KeyAlreadyExists","message":"Object already exists"}')
        self.storage[url]=data
        return DummyResponse(200)


def test_archive_only_downloads_each_month_once():
    remote=MemoryHTTP()
    archive=SupabaseArchive('https://xyzproject.supabase.co','sb_secret_FAKE_FOR_TESTS',session=remote)
    downloads=[]
    def fetch(start,end):
        downloads.append((start,end))
        return for_month(generate_synthetic(3),2026,8)
    cached=ArchivedFetcher(archive,fetch)
    a=cached('2026-08-01','2026-08-31')
    b=cached('2026-08-01','2026-08-31')
    assert len(downloads)==1
    assert cached.cache_hits==1 and cached.saved==1
    assert len(a)==len(b)
    assert set(remote.storage)
    assert 'Authorization' not in archive._headers()  # new sb_secret_ is not a JWT


class ErrorHTTP:
    def __init__(self, payload, status=400):
        self.payload=payload
        self.status=status
    def get(self,url,headers,timeout):
        return DummyResponse(self.status,self.payload)


def test_missing_object_is_only_a_cache_miss_not_a_fatal_http_400():
    archive=SupabaseArchive('https://xyzproject.supabase.co','sb_secret_FAKE_FOR_TESTS',
                            session=ErrorHTTP(b'{"statusCode":"404","code":"NoSuchKey","message":"Object not found"}'))
    assert archive.load(date(2024,1,1)) is None
    legacy=SupabaseArchive('https://xyzproject.supabase.co','sb_secret_FAKE_FOR_TESTS',
                           session=ErrorHTTP(b'{"statusCode":"404","error":"not_found","message":"Object not found"}'))
    assert legacy.load(date(2024,1,1)) is None


def test_missing_bucket_and_bad_access_are_not_mistaken_for_cache_misses():
    for payload, expected in [
        (b'{"statusCode":"404","code":"NoSuchBucket","message":"Bucket not found"}', 'bucket'),
        (b'{"statusCode":"403","code":"AccessDenied","message":"Access denied"}', 'access denied'),
        (b'{"statusCode":"400","code":"InvalidRequest","message":"Invalid request"}', 'InvalidRequest'),
        (b'not json', 'unavailable'),
    ]:
        archive=SupabaseArchive('https://xyzproject.supabase.co','sb_secret_FAKE_FOR_TESTS',
                                session=ErrorHTTP(payload))
        with pytest.raises(RuntimeError,match=expected):
            archive.load(date(2024,1,1))


def test_archive_invalid_origin_refused():
    with pytest.raises(ValueError,match='Supabase project URL'):
        SupabaseArchive('http://example.com','fake')


def test_market_regime_does_not_use_current_session_close():
    # Prior session history: 50 gradually increasing prices; sufficiently stable.
    history=list(np.linspace(100,120,50))
    sample=for_month(generate_synthetic(2),2026,8)
    first,carry=classify_sessions(sample,history)
    assert len(first)==2
    assert first.iloc[0].trend=='Uptrend'
    assert first.iloc[0].regime!='Insufficient history'
    changed=sample.copy()
    first_day=changed.timestamp.dt.tz_convert(ET).dt.date.min()
    current_day=changed.timestamp.dt.tz_convert(ET).dt.date==first_day
    changed.loc[current_day, 'close'] *= 1.5
    again,_=classify_sessions(changed,history)
    assert again.iloc[0].regime==first.iloc[0].regime
    assert again.iloc[0].vol20_annualized == first.iloc[0].vol20_annualized
    assert len(carry)==52
    empty,_=classify_sessions(sample,[])
    assert empty.iloc[0].regime == 'Insufficient history'


def test_regime_summary_does_not_infer_profitability():
    sample=pd.DataFrame([{'candidate':'one','period':'Development','regime':'Uptrend / Normal volatility',
                          'pnl_dollars':10,'net_return_pct':1.0},
                         {'candidate':'one','period':'Development','regime':'Uptrend / Normal volatility',
                          'pnl_dollars':-5,'net_return_pct':-0.5}])
    summary=summarize_regime_trades(sample)
    assert summary.iloc[0].trades==2
    assert summary.iloc[0].win_rate==50.0
    assert summary.iloc[0].pnl_dollars==5.0