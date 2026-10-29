"""Automated two-stage research: cache static basket news features; then ML.

Historical static 2026 companies are a *survivorship-biased research proxy*,
not an authentic 2019 QQQ constituent-weighted portfolio. Do not live trade.
"""
from __future__ import annotations
import argparse,os,uuid,json
from datetime import date,timedelta
from pathlib import Path
import sys
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from trade_lab.archive import SupabaseArchive,month_windows
from trade_lab.constituents import fetch_companyfacts,aggregate_filing_features
from trade_lab.news_lab import fetch_news_chunk,aggregate_news_asof,save_features,load_features
from trade_lab.ml import extract_month,fit_evaluate,FEATURES
from trade_lab.macro import fetch_fred_market_daily,append_previous_day_macro,MACRO_FEATURES
from scripts.macro_research import assemble
from scripts.automated_research import required_env,send_private_report

START=date(2019,1,1);END=date(2026,9,30)
NEWS_COLUMNS=('news_count_72h','news_score_mean_72h','news_negative_share_72h',
              'news_qqq_count_72h','news_company_mentions_72h','news_nonzero_share_72h')
FILING_COLUMNS=('issuer_profit_margin_mean','issuer_operating_margin_mean','issuer_filing_coverage',
                'issuer_recent_reports_30d','issuer_margin_coverage')

def month_decisions(bars):
    q=bars.loc[bars.symbol.eq('QQQ'),['timestamp']].copy()
    et=q.timestamp.dt.tz_convert('America/New_York')
    q=q.loc[et.dt.strftime('%H:%M').eq('09:50')].copy()
    q['date']=q.timestamp.dt.tz_convert('America/New_York').dt.date
    if q.date.duplicated().any():raise ValueError('Duplicate decision minute for date')
    return q[['date','timestamp']].sort_values('timestamp').reset_index(drop=True)


def archive_years(archive,api_key,secret,start_year,end_year):
    done=0;hits=0;articles=0;days=0
    begin=max(START,date(start_year,1,1))
    finish=min(END,date(end_year,12,31))
    if finish<begin:raise ValueError('Archive years do not overlap the frozen research period')
    for first,last in month_windows(begin,finish):
        old=load_features(archive,first)
        if old is not None:
            hits+=1;continue
        bars=archive.load(first)
        if bars is None:raise ValueError(f'Missing ETF archive {first:%Y-%m}')
        decision=month_decisions(bars)
        if decision.empty:raise ValueError(f'No QQQ decision bars {first:%Y-%m}')
        # Begin 4 days prior to cover weekend/holiday 72h lookback.
        articles_df=fetch_news_chunk(api_key,secret,first-timedelta(days=4),last+timedelta(days=1),max_pages=850,rate_delay=2.)
        derived=aggregate_news_asof(articles_df,decision,delay_minutes=5,lookback_hours=72)
        if len(derived)!=len(decision):raise ValueError('News decision mismatch')
        save_features(archive,first,derived)
        done+=1;articles+=len(articles_df);days+=len(derived)
        print(f'{first:%Y-%m}: derived features saved for {len(derived)} sessions from {len(articles_df)} relevant articles',flush=True)
    print(f'News feature caching complete for {start_year}-{end_year}: new={done}, cached={hits}, headlines processed={articles}, sessions={days}',flush=True)


def evaluate(archive):
    # Same price rows and execution assumptions for every model comparison.
    prices,excluded=assemble(archive)
    blocks=[]
    for first,_ in month_windows(START,END):
        part=load_features(archive,first)
        if part is None:raise RuntimeError(f'Historical derived news features missing {first:%Y-%m}. Archive first.')
        blocks.append(part)
    derived=pd.concat(blocks,ignore_index=True)
    if derived.date.duplicated().any():raise RuntimeError('Duplicate news feature dates')
    joined=prices.merge(derived,on='date',how='left',validate='one_to_one')
    if joined[list(NEWS_COLUMNS)].isna().any().any():raise RuntimeError('Missing derived news features on decision days')
    # Source is daily market conditions, shifted to strictly previous trading days.
    mkt=fetch_fred_market_daily(start='2018-01-01',end='2026-09-30')
    joined=append_previous_day_macro(joined,mkt).dropna(subset=list(MACRO_FEATURES)).reset_index(drop=True)
    if len(joined)<1200:raise RuntimeError('Insufficient joined news/price/macro sessions')
    universe={'price_only':list(FEATURES),
              'price_plus_macro':[ *FEATURES,*MACRO_FEATURES],
              'price_plus_news':[ *FEATURES,*NEWS_COLUMNS],
              'price_macro_news':[ *FEATURES,*MACRO_FEATURES,*NEWS_COLUMNS]}
    issuer_count=0
    user_agent=os.environ.get('SEC_USER_AGENT','').strip()
    if user_agent:
        facts=fetch_companyfacts(user_agent)
        filings=aggregate_filing_features(joined,facts)
        joined=joined.merge(filings,on='date',how='left',validate='one_to_one')
        # Coverage can vary; make the same-date sample explicit when comparing
        # SEC factors rather than filling older observations using future filings.
        if joined[list(FILING_COLUMNS)].notna().all(axis=1).mean()>=.85:
            issuer_count=len(facts)
            universe['price_macro_sec']=list(FEATURES)+list(MACRO_FEATURES)+list(FILING_COLUMNS)
            universe['price_macro_news_sec']=list(FEATURES)+list(MACRO_FEATURES)+list(NEWS_COLUMNS)+list(FILING_COLUMNS)
        else:
            print('SEC historical filing coverage insufficient; excluding SEC models instead of fabricating values.')
    out={};rank=[]
    for key,columns in universe.items():
        sample=joined.dropna(subset=columns).copy()
        if len(sample)<1200:raise RuntimeError(f'Too little data for {key}')
        result=fit_evaluate(sample,feature_columns=columns)
        out[key]={'selected':result['selected'],'reports':result['reports'],
                  'qualified':bool(result['qualified']),'rows':len(sample)}
        l=result['ranking'].copy();l.insert(0,'feature_set',key)
        rank.extend(l.to_dict(orient='records'))
    summary={'model_type':'fixed_basket_headline_lexicon_and_pit_sec_exploration',
        'go_no_go':'NO_VALIDATED_EDGE','models':out,
        'limitations':['2026 QQQ top-ten selected in hindsight: STATIC symbol basket, NOT historical QQQ holdings',
            'Created_at news is not verified first-seen publication latency',
            'Finance term lexicon is NOT trained transformer AI sentiment',
            'SEC companyfacts current feed and filed dates do not ensure complete 2019 vintages',
            '2025-2026 examined previously: retrospective diagnostics only'],
        'sec_issuers_included':issuer_count}
    table=pd.DataFrame(rank).replace([np.inf,-np.inf],np.nan)
    table=table.astype(object).where(pd.notna(table),None)
    body={'run_id':str(uuid.uuid4()),'code_sha':os.getenv('GITHUB_SHA','manual'),
       'research_start':str(START),'research_end':str(END),
       'candidate_count':len(rank),'summary':summary,
       'leaderboard':json.loads(table.to_json(orient='records')),
       'diagnostics':{'sample_sessions':len(joined),'incomplete_market_sessions_excluded':excluded,
           'news_features':list(NEWS_COLUMNS),'sec_features':list(FILING_COLUMNS) if issuer_count else [],
           'data_archive':'monthly private derived headline features, no article text',
           'no_live_orders':True,'survivorship_bias':True,
           'news_model':'transparent predeclared event keyword lexicon v1',
           'historical_news_first_seen_verified':False}}
    send_private_report(required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY'),body)
    print('All feature-set evaluations stored privately; no live orders.',flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=('smoke','archive','evaluate'),required=True)
    p.add_argument('--year-start',type=int,default=2019)
    p.add_argument('--year-end',type=int,default=2026)
    a=p.parse_args()
    url=required_env('SUPABASE_URL');key=required_env('SUPABASE_SECRET_KEY')
    archive=SupabaseArchive(url,key,os.environ.get('SUPABASE_BUCKET','market-edge-history'))
    if a.mode=='smoke':
        result=fetch_news_chunk(required_env('ALPACA_KEY_ID'),required_env('ALPACA_SECRET_KEY'),
            date(2026,9,1),date(2026,9,3),max_pages=150,rate_delay=1.)
        if result.empty:raise RuntimeError('Alpaca news API returned no articles for the smoke-check period')
        print(f'Historical Alpaca news access verified: {len(result)} articles in smoke check; no text retained.',flush=True)
    elif a.mode=='archive':
        if not 2019<=a.year_start<=a.year_end<=2026:raise ValueError('Unsupported research years')
        archive_years(archive,required_env('ALPACA_KEY_ID'),required_env('ALPACA_SECRET_KEY'),a.year_start,a.year_end)
    else:evaluate(archive)

if __name__=='__main__':main()
