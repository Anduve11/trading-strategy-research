"""Optional on-demand download of delayed IEX 1-minute ETF bars from Alpaca.

Never write API credentials to disk. The free IEX feed is NOT consolidated SIP.
"""
import requests
import pandas as pd
from .data import validate_bars

API = 'https://data.alpaca.markets/v2/stocks/bars'


def fetch_bars(api_key: str, api_secret: str, start_date: str, end_date: str, feed: str = 'iex') -> pd.DataFrame:
    if not api_key or not api_secret:
        raise ValueError('Alpaca API key and secret are required.')
    start = pd.Timestamp(start_date).tz_localize('America/New_York').tz_convert('UTC').isoformat()
    end = (pd.Timestamp(end_date)+pd.Timedelta(days=1)).tz_localize('America/New_York').tz_convert('UTC').isoformat()
    if end <= start:
        raise ValueError('End date must not precede start date.')
    headers = {'APCA-API-KEY-ID':api_key,'APCA-API-SECRET-KEY':api_secret}
    params = {'symbols':'QQQ,TQQQ,SQQQ','timeframe':'1Min','start':start,'end':end,'feed':feed,
              'limit':10000,'adjustment':'split','sort':'asc'}
    rows=[]
    with requests.Session() as s:
        for page in range(150):
            resp=s.get(API,headers=headers,params=params,timeout=35)
            if not resp.ok:
                msg = resp.text[:250]
                raise RuntimeError(f'Alpaca market-data request failed ({resp.status_code}): {msg}')
            payload=resp.json()
            for sym,bars in payload.get('bars',{}).items():
                for b in bars:
                    rows.append({'timestamp':b['t'],'symbol':sym,'open':b['o'],'high':b['h'],
                                 'low':b['l'],'close':b['c'],'volume':b['v']})
            token=payload.get('next_page_token')
            if not token:
                break
            params['page_token']=token
        else:
            raise RuntimeError('Pagination safety limit hit. Request fewer dates.')
    if not rows:
        raise ValueError('Alpaca returned no bars. Check date range/feed permissions.')
    return validate_bars(pd.DataFrame(rows))