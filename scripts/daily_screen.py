"""Eighteen-pair daily screen with private replay snapshots. No orders."""
import argparse,gzip,json,os,sys,uuid,hashlib
from io import BytesIO
from dataclasses import asdict
from pathlib import Path
import pandas as pd
import exchange_calendars as xcals
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.daily_screen import UNIVERSE,FEATURES,download_daily,validate_daily,build_daily
from trade_lab.archive import SupabaseArchive
from trade_lab.edge_research import walk_forward_search,predict_profit,choose_side,metrics
from trade_lab.macro import fetch_fred_market_daily,append_previous_day_macro,MACRO_FEATURES
from scripts.automated_research import required_env,send_private_report
from scripts.universe_research import enough_data


def save(archive,path,payload):
    r=archive.session.post(archive._url(path),headers={**archive._headers(),'Content-Type':'application/gzip'},data=payload,timeout=90)
    if not r.ok:raise RuntimeError(f'Private daily save HTTP {r.status_code}')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pair',choices=list(UNIVERSE),required=True);args=parser.parse_args()
    pair=UNIVERSE[args.pair]
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY')
    archive=SupabaseArchive(url,secret)
    key=f'alpaca/sip/split/1day/screen-v1/{pair.proxy}-{pair.bull}-{pair.bear}/2018-2026-09.csv.gz'
    r=archive.session.get(archive._url(key),headers=archive._headers(),timeout=60)
    if r.ok:raw=validate_daily(pd.read_csv(BytesIO(gzip.decompress(r.content))),pair)
    else:
        code,_=archive._storage_error(r)
        if code!='NoSuchKey':raise RuntimeError(f'Daily cache read HTTP {r.status_code}')
        raw=download_daily(pair,required_env('ALPACA_KEY_ID'),required_env('ALPACA_SECRET_KEY'))
        save(archive,key,gzip.compress(raw.to_csv(index=False).encode(),mtime=0))
    cal=xcals.get_calendar('XNYS',start='2018-01-01',end='2026-09-30')
    data=build_daily(raw,pair,cal.sessions)
    data=append_previous_day_macro(data,fetch_fred_market_daily()).dropna(subset=list(MACRO_FEATURES)).sort_values('date')
    specs={'price':{'columns':list(FEATURES),'macro_weight':0.},'price_macro':{'columns':[*FEATURES,*MACRO_FEATURES],'macro_weight':1.}}
    run=str(uuid.uuid4());total=0;ranking=[]
    summary={'model_type':'daily_etf_screen_v1','pair':args.pair,'instruments':asdict(pair),'go_no_go':'NO_VALIDATED_EDGE'}
    if enough_data(data):
        result=walk_forward_search(data,specs)
        rank=result.pop('ranking');total=len(rank);ranking=json.loads(rank.to_json(orient='records'))
        selected=result['selected']
        if selected:
            train=data.loc[pd.to_datetime(data.date).dt.year<=2023].iloc[:-2]
            test=data.loc[pd.to_datetime(data.date).dt.year>=2024]
            sides=choose_side(predict_profit(train,test,specs[selected['feature_set']],selected['model']),selected['cushion_pct'])
            result['inspected_2024_2026_stress_20bps']=metrics(test,sides,20)
        summary.update(result);summary['status']='COMPLETED_HISTORICAL_DIAGNOSTIC'
    else:summary['status']='INSUFFICIENT_DAILY_DATA'
    payload=gzip.compress(data.to_csv(index=False).encode(),mtime=0)
    snapshot=f'research/daily-screen-v1/{run}/features-outcomes.csv.gz';save(archive,snapshot,payload)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2019-01-01','research_end':'2026-09-30',
      'candidate_count':max(1,total),'summary':summary,'leaderboard':ranking,
      'diagnostics':{'no_live_orders':True,'actual_candidates_tested':total,'allocation_percent':10,'sessions':int(data.date.nunique()),
        'raw_cache':key,'snapshot':snapshot,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),
        'batch_budget':'18 pairs, 12 configurations per pair = 216 maximum; no later-return universe winner selection',
        'limitations':['Vendor daily opens/closes are hypothetical fills; exact session/auction definitions unverified',
        'Primary features are strictly previous-session only; daily data never imply intraday stop/target paths',
        'Costs 5,10,20bps per side do not replace quote/size/latency validation',
        'Different pairs have unequal volatility and historical coverage; same capital is not equal risk',
        'All 2024-2026 observations are historical diagnostics, not a new untouched holdout',
        'Current surviving ETF selection and historical benchmark changes can bias comparisons',
        'Missing days remain missing; no interpolation; no prospective edge claim',
        'Candidate count sentinel 1 used when actual_candidates_tested=0']}}
    send_private_report(url,secret,json.loads(json.dumps(body,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))))
    print(f'{args.pair}: daily screen saved privately; no orders.',flush=True)


if __name__=='__main__':main()
