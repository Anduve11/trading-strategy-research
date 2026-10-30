"""Registered adaptive daily models on all 18 cached pairs; private reports."""
import argparse,gzip,json,os,sys,uuid,hashlib
from pathlib import Path
from dataclasses import asdict
import pandas as pd
import exchange_calendars as xcals
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.daily_screen import UNIVERSE,FEATURES
from trade_lab.context_factors import CONTEXT,BEHAVIOR,context_features,build_experiment
from trade_lab.adaptive_research import CALENDAR,append_calendar,adaptive_search
from trade_lab.archive import SupabaseArchive
from trade_lab.macro import MACRO_FEATURES,fetch_fred_market_daily,append_previous_day_macro
from scripts.context_research import load
from scripts.daily_screen import save
from scripts.automated_research import required_env,send_private_report
from scripts.universe_research import enough_data


def main():
    p=argparse.ArgumentParser();p.add_argument('--pair',choices=list(UNIVERSE),required=True);a=p.parse_args()
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY');archive=SupabaseArchive(url,secret)
    proxies=[]
    for name in ('nasdaq3','sp500','smallcap','semiconductors','treasury2','gold2'):
        bars=load(archive,name);proxies.append(bars.loc[bars.symbol.eq(UNIVERSE[name].proxy)])
    # Full calendar years prevent truncated September history from treating
    # September 30 as a false year/month end in the known schedule.
    cal=xcals.get_calendar('XNYS',start='2018-01-01',end='2026-12-31')
    sessions=cal.sessions[cal.sessions<=pd.Timestamp('2026-09-30')]
    context=context_features(pd.concat(proxies,ignore_index=True),sessions)
    data=build_experiment(load(archive,a.pair),UNIVERSE[a.pair],sessions,context,'day')
    data=append_calendar(append_previous_day_macro(data,fetch_fred_market_daily()),cal.sessions).dropna().sort_values('date')
    all_features=[*FEATURES,*BEHAVIOR,*CONTEXT,*MACRO_FEATURES]
    specs={'price':{'columns':list(FEATURES),'macro_weight':1.},
      'context_calendar':{'columns':[*all_features,*CALENDAR],'macro_weight':1.}}
    run=str(uuid.uuid4());count=0;rank=[]
    summary={'model_type':'adaptive_cost_aware_v1','pair':a.pair,'instruments':asdict(UNIVERSE[a.pair]),'go_no_go':'NO_VALIDATED_EDGE'}
    if enough_data(data):
        result=adaptive_search(data,specs);ranking=result.pop('ranking');count=len(ranking);rank=json.loads(ranking.to_json(orient='records'))
        summary.update(result);summary['status']='COMPLETED_HISTORICAL_DIAGNOSTIC'
    else:summary['status']='INSUFFICIENT_DAILY_DATA'
    payload=gzip.compress(data.to_csv(index=False).encode(),mtime=0);key=f'research/adaptive-v1/{run}/features-outcomes.csv.gz';save(archive,key,payload)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2019-01-01','research_end':'2026-09-30',
      'candidate_count':max(1,count),'summary':summary,'leaderboard':rank,'diagnostics':{'actual_candidates_tested':count,
        'no_live_orders':True,'allocation_percent':10,'primary_slippage_bps_per_side':10,'stress_slippage_bps_per_side':20,
        'batch_budget':'18 pairs x 2 feature sets x 2 fit windows x 2 decision rules x 3 cushions = 432 configurations',
        'selection':'Quarterly past-only predictions; rank using 2021-2023 ONLY; 2-session training embargo',
        'label_clipping':'Train 10bps returns clipped at training-only 1%/99% quantiles; evaluation outcomes never clipped',
        'snapshot':key,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),'feature_sets':specs,
        'limitations':['2024-2026 inspected; not untouched validation','Quarterly adaptation may train on earlier evaluation-quarter outcomes, never current/future quarter',
          'Vendor open/close are hypothetical fills, no quote or auction verification','Survivor selection, proxy mismatch and multiple testing remain',
          'Same capital allocation is not equal volatility risk; no hindsight cross-pair winner','No validated edge without genuinely new prospective predictions',
          'Database count sentinel 1 when actual_candidates_tested=0']}}
    send_private_report(url,secret,json.loads(json.dumps(body,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))))
    print(f'{a.pair}: adaptive research saved privately; no orders.',flush=True)


if __name__=='__main__':main()
