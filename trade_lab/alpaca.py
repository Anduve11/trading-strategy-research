"""On-demand historical ETF minute bars from Alpaca (SIP or IEX).

The API key is only sent in authenticated request headers, never written to disk.
"""
import time
import requests
import pandas as pd
from .data import validate_bars

API = 'https://data.alpaca.markets/v2/stocks/bars'


def fetch_bars(api_key: str, api_secret: str, start_date: str, end_date: str, feed: str = 'iex') -> pd.DataFrame:
    if feed not in ('sip', 'iex'):
        raise ValueError('Choose a supported data feed: SIP or IEX.')
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
            # Paid and free plans have rate limits. Back off instead of failing
            # silently mid-study or keeping a partially fetched quarter.
            for retry in range(5):
                resp=s.get(API,headers=headers,params=params,timeout=35)
                if resp.status_code not in (429, 500, 502, 503, 504):
                    break
                if retry == 4:
                    break
                delay = min(30, 2 ** retry)
                if resp.status_code == 429:
                    try:
                        delay = min(30, max(1, int(float(resp.headers.get('Retry-After','3')))))
                    except ValueError:
                        delay = 3
                time.sleep(delay)
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