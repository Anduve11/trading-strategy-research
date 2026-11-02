"""Read-only, bounded Alpaca historical requests. Never contains order URLs."""
import re
import time
import requests
import pandas as pd


def historical_bars(symbols,start,end,timeframe,key,secret,session=None):
    if not symbols or any(not re.fullmatch(r'[A-Z]{1,12}',s) for s in symbols):raise ValueError('Invalid tickers')
    if timeframe not in ('1Min','1Day'):raise ValueError('Unsupported interval')
    if not key or not secret:raise ValueError('Missing market-data credentials')
    start,end=pd.Timestamp(start),pd.Timestamp(end)
    if start.tzinfo is None or end.tzinfo is None or end<=start:raise ValueError('Require ordered aware timestamps')
    session=session or requests.Session()
    params={'symbols':','.join(symbols),'start':start.isoformat(),'end':end.isoformat(),
            'timeframe':timeframe,'feed':'sip','adjustment':'split','limit':10000,'sort':'asc'}
    original=params.copy();headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
    rows=[];seen=set()
    for _ in range(20):
        for retry in range(5):
            response=session.get('https://data.alpaca.markets/v2/stocks/bars',params=params,headers=headers,timeout=45)
            if response.status_code not in (429,500,502,503,504):break
            if retry<4:time.sleep(min(16,2**retry))
        if not response.ok:raise RuntimeError(f'Historical market-data HTTP {response.status_code}')
        body=response.json()
        for symbol,bars in body.get('bars',{}).items():
            for b in bars:rows.append({'timestamp':b['t'],'symbol':symbol,'open':b['o'],'high':b['h'],
                'low':b['l'],'close':b['c'],'volume':b['v']})
        token=body.get('next_page_token')
        if not token:break
        if token in seen:raise ValueError('Repeated historical-data page token')
        seen.add(token);params['page_token']=token;time.sleep(.35)
    else:raise ValueError('Historical pagination limit')
    time.sleep(.35)
    return pd.DataFrame(rows,columns=['timestamp','symbol','open','high','low','close','volume']),original
