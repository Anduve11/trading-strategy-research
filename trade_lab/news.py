"""Timestamp-safe adapter for future historical headline/sentiment features.

Deliberately does NOT hallucinate or backfill missing sentiment values.
News fields are NOT part of the ML model until historical coverage is proven.
"""
import pandas as pd

NEEDED={'created_at','headline','symbols','source'}


def validate_news(raw:pd.DataFrame)->pd.DataFrame:
    if not NEEDED.issubset(raw.columns):
        raise ValueError('News must include created_at, headline, symbols, source')
    n=raw.copy()
    n['created_at']=pd.to_datetime(n.created_at,utc=True,errors='coerce')
    if n.created_at.isna().any():raise ValueError('Invalid news creation timestamp')
    n['headline']=n.headline.astype(str)
    if n.headline.str.len().gt(10000).any():raise ValueError('Unusually large headline')
    return n.sort_values('created_at').reset_index(drop=True)


def aggregate_predecision_sentiment(news:pd.DataFrame, decisions:pd.DataFrame,
                                    delay_minutes:int=5, lookback_hours:int=18)->pd.DataFrame:
    """Aggregate externally PRE-SCORED, available news; missing != neutral.

    'sentiment' must be generated without using future prices/outcomes.
    Note: article created_at is only a proxy for genuine vendor first-seen time.
    """
    if 'sentiment' not in news.columns:raise ValueError('Sentiment unavailable; do not fabricate scores')
    n=validate_news(news)
    score=pd.to_numeric(n.sentiment,errors='coerce')
    if score.isna().any() or ((score<-1)|(score>1)).any():raise ValueError('Sentiment must be -1..+1')
    if not 0<=delay_minutes<=120 or not 1<=lookback_hours<=72:raise ValueError('Invalid window')
    dec=decisions[['date','timestamp']].copy()
    dec['timestamp']=pd.to_datetime(dec.timestamp,utc=True)
    out=[]
    for r in dec.itertuples(index=False):
        latest=r.timestamp-pd.Timedelta(minutes=delay_minutes)
        earliest=latest-pd.Timedelta(hours=lookback_hours)
        b=n.loc[n.created_at.between(earliest,latest,inclusive='both')]
        out.append({'date':r.date,'news_articles':len(b),
                    'news_sentiment':float(b.sentiment.mean()) if len(b) else float('nan')})
    return pd.DataFrame(out)


def fetch_alpaca_news(api_key:str,api_secret:str,start_iso:str,end_iso:str,
                      symbols:str='AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA',
                      max_pages:int=250)->pd.DataFrame:
    """Historical Benzinga/Alpaca headline ingestion, RESEARCH ONLY.

    Does not store article content or claim historical headlines were received
    instantaneously. Confirm vendor rights and point-in-time first-seen fields
    before treating the series as executable real-time sentiment.
    """
    import requests
    if not api_key or not api_secret:raise ValueError('Alpaca news credentials required')
    if not 1<=max_pages<=2000:raise ValueError('Invalid page cap')
    params={'start':start_iso,'end':end_iso,'symbols':symbols,'limit':50,'sort':'asc',
            'include_content':'false'}
    headers={'APCA-API-KEY-ID':api_key,'APCA-API-SECRET-KEY':api_secret}
    rows=[]
    with requests.Session() as sess:
        for _ in range(max_pages):
            resp=sess.get('https://data.alpaca.markets/v1beta1/news',headers=headers,params=params,timeout=40)
            if not resp.ok:raise RuntimeError(f'Alpaca news request failed (HTTP {resp.status_code})')
            obj=resp.json()
            for a in obj.get('news',[]):
                rows.append({'created_at':a.get('created_at'), 'headline':a.get('headline',''),
                    'symbols':','.join(a.get('symbols',[])), 'source':a.get('source',''),
                    'id':a.get('id')})
            token=obj.get('next_page_token')
            if not token:break
            params['page_token']=token
        else:raise RuntimeError('News pagination cap reached; use a shorter date range')
    if not rows:return pd.DataFrame(columns=['created_at','headline','symbols','source','id'])
    result=validate_news(pd.DataFrame(rows)).drop_duplicates(subset='id',keep='first')
    return result


def score_finbert(headlines:list[str], batch_size:int=16)->list[float]:
    """Optional finance-specific transformer sentiment, negative=-1, positive=1.

    Requires optional `transformers` and model weights, not in the base ML job.
    Version-lock weights before comparing years; provider revisions and
    inference latency complicate historical execution claims.
    """
    try:
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError('Install optional transformers + torch for FinBERT scoring') from exc
    detector=pipeline('text-classification',model='ProsusAI/finbert',top_k=None,device=-1)
    scores=[]
    for offset in range(0,len(headlines),batch_size):
        batch=detector([h[:1200] for h in headlines[offset:offset+batch_size]],truncation=True)
        for probabilities in batch:
            vals={str(x['label']).lower():float(x['score']) for x in probabilities}
            scores.append(vals.get('positive',0.)-vals.get('negative',0.))
    return scores