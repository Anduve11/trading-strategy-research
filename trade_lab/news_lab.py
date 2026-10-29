"""Research-only archive of headline-derived features (no full-text redistribution).

News content is scored with a predeclared, transparent *lexicon baseline*.
Article created_at is NOT guaranteed to be a vendor first-seen timestamp, so
historical results are retrospective diagnostics, not executable evidence.
"""
from __future__ import annotations
from datetime import date,timedelta
import gzip,io,json,re,time
from urllib.parse import quote
import numpy as np
import pandas as pd
import requests
from .constituents import SYMBOLS

WATCHLIST=(*SYMBOLS,'QQQ')
POSITIVE=('beat expectations','beats estimates','raises guidance','raised guidance','record revenue',
    'earnings beat','profit jumps','upgrades','upgraded','buyback','strong demand','guidance raised',
    'revenue growth','sales growth','surges','new high')
NEGATIVE=('misses estimates','missed estimates','cuts guidance','cut guidance','downgrades',
    'downgraded','earnings miss','revenue miss','profit warning','antitrust', 'lawsuit',
    'investigation','recall','layoffs','weak demand','supply disruption','data breach',
    'guidance lowered','regulatory probe','falls sharply')
BASE='alpaca/sip/news-derived-lexicon-v1/static-2026-basket'

def lexicon_score(headline:str)->float:
    h=' '.join(str(headline).lower().split())
    pos=sum(x in h for x in POSITIVE)
    neg=sum(x in h for x in NEGATIVE)
    return float((pos-neg)/max(1,pos+neg))


def fetch_news_chunk(key:str,secret:str,begin:date,end:date,session=None,max_pages=500,
                     rate_delay=1.5) ->pd.DataFrame:
    """Get timestamped article metadata without retaining copyrighted full text.

    Request range inclusive start, exclusive end in UTC; use pagination token.
    429, 500, 502, 503 retry with backoff; hard-fail on cap. Caller caches
    finished months, and treats all other fetch failures as incomplete.
    """
    if not key or not secret:raise ValueError('Missing Alpaca market data keys')
    if end<=begin:raise ValueError('Invalid date interval')
    if not 1<=max_pages<=5000:raise ValueError('Invalid pagination limit')
    sess=session or requests.Session()
    params={'start':f'{begin.isoformat()}T00:00:00Z','end':f'{end.isoformat()}T00:00:00Z',
       'symbols':','.join(WATCHLIST),'limit':50,'sort':'asc','include_content':'false'}
    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
    rows=[]; visited=set()
    for page in range(max_pages):
        if rate_delay:time.sleep(rate_delay)
        for attempt in range(5):
            resp=sess.get('https://data.alpaca.markets/v1beta1/news',params=params,headers=headers,timeout=45)
            if resp.status_code in (429,500,502,503,504) and attempt<4:
                time.sleep(min(30,2**attempt*2));continue
            break
        if not resp.ok:raise RuntimeError(f'Historical Alpaca news HTTP {resp.status_code}')
        data=resp.json()
        for article in data.get('news',[]):
            raw=article.get('created_at');title=article.get('headline')
            if not raw or not title:continue
            rows.append({'id':str(article.get('id','')),
                'created_at':raw,'score':lexicon_score(title),
                'is_qqq':int('QQQ' in article.get('symbols',[])),
                'company_symbols':sum(x in article.get('symbols',[]) for x in SYMBOLS)})
        token=data.get('next_page_token')
        if not token:break
        if token in visited:raise RuntimeError('News pagination token loop')
        visited.add(token)
        params['page_token']=token
    else:raise RuntimeError(f'News exceeded {max_pages} pages; use shorter intervals')
    if not rows:return pd.DataFrame(columns=['id','created_at','score','is_qqq','company_symbols'])
    frame=pd.DataFrame(rows).drop_duplicates(subset='id')
    frame['created_at']=pd.to_datetime(frame.created_at,utc=True,errors='raise')
    lo=pd.Timestamp(begin,tz='UTC');hi=pd.Timestamp(end,tz='UTC')
    if (frame.created_at.lt(lo)|frame.created_at.ge(hi)).any():
        raise ValueError('News provider returned timestamps outside requested interval')
    return frame.sort_values('created_at').reset_index(drop=True)


def aggregate_news_asof(news:pd.DataFrame,decisions:pd.DataFrame,delay_minutes:int=5,
                        lookback_hours:int=72)->pd.DataFrame:
    """News must be at least `delay_minutes` old at QQQ decision instant."""
    if not 0<=delay_minutes<=60:raise ValueError('Invalid decision delay')
    dec=decisions[['date','timestamp']].copy()
    dec['timestamp']=pd.to_datetime(dec.timestamp,utc=True)
    x=news.copy()
    if x.empty:
        x=pd.DataFrame(columns=['created_at','score','is_qqq','company_symbols'])
    else:
        x['created_at']=pd.to_datetime(x.created_at,utc=True,errors='raise')
        if not x.score.between(-1,1).all():raise ValueError('Invalid news score')
    out=[]
    for row in dec.itertuples(index=False):
        stop=row.timestamp+pd.Timedelta(minutes=1-delay_minutes)
        start=stop-pd.Timedelta(hours=lookback_hours)
        subset=x.loc[(x.created_at>=start)&(x.created_at<stop)]
        out.append({'date':row.date,'news_count_72h':int(len(subset)),
            'news_score_mean_72h':float(subset.score.mean()) if len(subset) else 0.,
            'news_negative_share_72h':float((subset.score<0).mean()) if len(subset) else 0.,
            'news_qqq_count_72h':int(subset.is_qqq.sum()) if len(subset) else 0,
            'news_company_mentions_72h':int(subset.company_symbols.sum()) if len(subset) else 0,
            'news_nonzero_share_72h':float((subset.score!=0).mean()) if len(subset) else 0.})
    return pd.DataFrame(out)


def derived_key(month:date)->str:
    return f'{BASE}/{month:%Y-%m}.csv.gz'


def save_features(archive,month:date,features:pd.DataFrame):
    from .archive import SupabaseArchive
    if features.empty:raise ValueError('Cannot archive empty monthly feature set')
    cols=['date','news_count_72h','news_score_mean_72h','news_negative_share_72h',
        'news_qqq_count_72h','news_company_mentions_72h','news_nonzero_share_72h']
    if not set(cols).issubset(features.columns):raise ValueError('Incomplete derived news columns')
    body=gzip.compress(features[cols].to_csv(index=False).encode('utf8'),mtime=0)
    from .archive import SupabaseArchive
    url=archive._url(derived_key(month))
    headers={**archive._headers(),'Content-Type':'application/gzip'}
    resp=archive.session.post(url,headers=headers,data=body,timeout=90)
    if resp.ok:return
    code,_=archive._storage_error(resp)
    if code in ('KeyAlreadyExists','ResourceAlreadyExists'):return
    raise RuntimeError(f'Private news feature archive write failed HTTP {resp.status_code} code {code}')


def load_features(archive,month:date)->pd.DataFrame|None:
    resp=archive.session.get(archive._url(derived_key(month)),headers=archive._headers(),timeout=40)
    if resp.ok:
        if len(resp.content)>1000000:raise ValueError('Derived features object too large')
        result=pd.read_csv(io.BytesIO(gzip.decompress(resp.content)))
        required={'date','news_count_72h','news_score_mean_72h','news_negative_share_72h',
            'news_qqq_count_72h','news_company_mentions_72h','news_nonzero_share_72h'}
        if not required.issubset(result.columns):raise ValueError('Missing derived news data columns')
        result['date']=pd.to_datetime(result.date).dt.date
        if any(d.year!=month.year or d.month!=month.month for d in result.date):
            raise ValueError('Derived news data has wrong month')
        return result
    code,msg=archive._storage_error(resp)
    if code=='NoSuchKey' or (resp.status_code==404 and code!='NoSuchBucket'):return None
    raise RuntimeError(f'Derived news archive read HTTP {resp.status_code} code {code}')