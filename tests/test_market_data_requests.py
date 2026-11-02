import json
import pandas as pd
import pytest
import trade_lab.market_data_requests as data


class Response:
    ok=True;status_code=200
    def __init__(self,payload):self.payload=payload
    def json(self):return self.payload


class Session:
    def __init__(self,pages):self.pages=iter(pages);self.tokens=[]
    def get(self,url,params,headers,timeout):
        assert url=='https://data.alpaca.markets/v2/stocks/bars'
        self.tokens.append(params.get('page_token'))
        return Response(next(self.pages))


def test_pagination_across_symbols_and_no_credentials_in_provenance(monkeypatch):
    monkeypatch.setattr(data.time,'sleep',lambda _:None)
    bar={'t':'2025-01-02T14:30Z','o':100,'h':101,'l':99,'c':100,'v':100}
    session=Session([{'bars':{'SOXL':[bar]},'next_page_token':'next'}, {'bars':{'SOXS':[bar]}}])
    frame,meta=data.historical_bars(['SOXL','SOXS'],pd.Timestamp('2025-01-02T14:30Z'),pd.Timestamp('2025-01-02T21:00Z'),'1Min','sensitive-key','sensitive-secret',session)
    assert set(frame.symbol)=={'SOXL','SOXS'} and session.tokens==[None,'next']
    assert 'sensitive' not in json.dumps(meta)
    broken=Session([{'bars':{},'next_page_token':'x'},{'bars':{},'next_page_token':'x'}])
    with pytest.raises(ValueError,match='Repeated'):data.historical_bars(['SOXL'],pd.Timestamp('2025-01-02T14:30Z'),pd.Timestamp('2025-01-02T21:00Z'),'1Min','key','secret',broken)
