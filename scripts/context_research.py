"""Registered 18-pair x 2-interval cross-market hypothesis batch; no orders."""
import argparse,gzip,json,os,sys,uuid,hashlib
from io import BytesIO
from pathlib import Path
from dataclasses import asdict
import pandas as pd
import exchange_calendars as xcals
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.daily_screen import UNIVERSE,FEATURES,validate_daily
from trade_lab.context_factors import CONTEXT,BEHAVIOR,context_features,build_experiment
from trade_lab.archive import SupabaseArchive
from trade_lab.macro import fetch_fred_market_daily,append_previous_day_macro,MACRO_FEATURES
from trade_lab.edge_research import walk_forward_search,predict_profit,choose_side,metrics
from scripts.daily_screen import save
from scripts.automated_research import required_env,send_private_report
from scripts.universe_research import enough_data


def load(archive,name):
    p=UNIVERSE[name]
    key=f'alpaca/sip/split/1day/screen-v1/{p.proxy}-{p.bull}-{p.bear}/2018-2026-09.csv.gz'
    r=archive.session.get(archive._url(key),headers=archive._headers(),timeout=60)
    if not r.ok:raise RuntimeError(f'Required existing daily cache {name} HTTP {r.status_code}')
    return validate_daily(pd.read_csv(BytesIO(gzip.decompress(r.content))),p)


def main():
    p=argparse.ArgumentParser();p.add_argument('--pair',choices=list(UNIVERSE),required=True);a=p.parse_args()
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY')
    archive=SupabaseArchive(url,secret)
    proxies=[]
    for name in ('nasdaq3','sp500','smallcap','semiconductors','treasury2','gold2'):
        bars=load(archive,name);proxies.append(bars.loc[bars.symbol.eq(UNIVERSE[name].proxy)])
    sessions=xcals.get_calendar('XNYS',start='2018-01-01',end='2026-09-30').sessions
    context=context_features(pd.concat(proxies,ignore_index=True),sessions)
    raw=load(archive,a.pair);macro=fetch_fred_market_daily()
    specs={'price':{'columns':list(FEATURES),'macro_weight':1.},
      'price_behavior':{'columns':[*FEATURES,*BEHAVIOR],'macro_weight':1.},
      'price_context':{'columns':[*FEATURES,*CONTEXT],'macro_weight':1.},
      'all_context':{'columns':[*FEATURES,*BEHAVIOR,*CONTEXT,*MACRO_FEATURES],'macro_weight':1.}}
    for interval in ('day','overnight'):
        data=append_previous_day_macro(build_experiment(raw,UNIVERSE[a.pair],sessions,context,interval),macro).dropna(subset=list(MACRO_FEATURES)).sort_values('date')
        run=str(uuid.uuid4());rank=[];total=0
        summary={'model_type':'cross_market_behavior_v1','pair':a.pair,'interval':interval,'instruments':asdict(UNIVERSE[a.pair]),'go_no_go':'NO_VALIDATED_EDGE'}
        if enough_data(data):
            result=walk_forward_search(data,specs,label_column='proxy_forward_return_pct')
            ranking=result.pop('ranking');total=len(ranking);rank=json.loads(ranking.to_json(orient='records'))
            selected=result['selected']
            if selected:
                train=data.loc[pd.to_datetime(data.date).dt.year<=2023].iloc[:-2]
                test=data.loc[pd.to_datetime(data.date).dt.year>=2024]
                sides=choose_side(predict_profit(train,test,specs[selected['feature_set']],selected['model']),selected['cushion_pct'])
                result['inspected_2024_2026_stress_20bps']=metrics(test,sides,20)
            result['feature_group_development_leaders']=json.loads(ranking.groupby('feature_set').head(1).to_json(orient='records'))
            summary.update(result);summary['status']='COMPLETED_HISTORICAL_DIAGNOSTIC'
        else:summary['status']='INSUFFICIENT_DAILY_DATA'
        payload=gzip.compress(data.to_csv(index=False).encode(),mtime=0)
        key=f'research/context-v1/{run}/features-outcomes.csv.gz';save(archive,key,payload)
        diagnostics={'no_live_orders':True,'actual_candidates_tested':total,'allocation_percent':10,'sessions':int(data.date.nunique()),
          'snapshot':key,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),'feature_sets':specs,
          'batch_budget':'18 pairs x 2 intervals x 24 configurations = 864 maximum',
          'horizon_unit':'One vendor daily interval; horizon=1 is NOT one minute',
          'limitations':['All predictors lag at least one full session; no current gap/volume is known before assumed fill',
            'Overnight includes weekends and next scheduled sessions; missing next-session prices never bridged',
            'Vendor daily closes/opens are hypothetical fills, not verified auction prices',
            'No interpolation or daily OHLC stop/target inference; slippage 5/10/20bps per side',
            'Cross-market associations do not establish causality or intraday first-mover timing',
            '2024-2026 already inspected; historical diagnostics only, prospective testing required',
            'Surviving-fund selection, benchmark/proxy mismatches and multiple testing remain limitations',
            '10% allocation is not equal risk across asset classes; no hindsight cross-pair winner',
            'candidate_count sentinel 1 when actual_candidates_tested=0']}
        body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2019-01-01','research_end':'2026-09-30','candidate_count':max(1,total),'summary':summary,'leaderboard':rank,'diagnostics':diagnostics}
        send_private_report(url,secret,json.loads(json.dumps(body,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))))
        print(f'{a.pair} {interval}: context-factor report saved privately; no orders.',flush=True)


if __name__=='__main__':main()
