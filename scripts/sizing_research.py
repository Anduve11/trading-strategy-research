"""Replay frozen incumbent and simple challengers; no capital is moved."""
import argparse,gzip,json,os,sys,uuid,hashlib
from io import BytesIO
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.adaptive_research import quarterly_forecasts,select_sides
from trade_lab.sizing_research import compare_sizing
from scripts.daily_screen import save
from scripts.automated_research import required_env,send_private_report


def main():
    p=argparse.ArgumentParser();p.add_argument('--pair',choices=list(UNIVERSE),required=True);a=p.parse_args()
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY');archive=SupabaseArchive(url,secret)
    response=archive.session.get(url.rstrip('/')+'/rest/v1/market_edge_research_runs',headers=archive._headers(),
      params={'select':'run_id,summary,diagnostics','summary->>model_type':'eq.adaptive_cost_aware_v1',
       'summary->>pair':'eq.'+a.pair,'code_sha':'eq.980a62b51881793ef87a29b29f61fb18f0bb7e4e','order':'created_at.desc','limit':'1'},timeout=60)
    if not response.ok:raise RuntimeError(f'Private source report HTTP {response.status_code}')
    rows=response.json()
    if len(rows)!=1 or not rows[0]['summary'].get('selected'):raise RuntimeError('Frozen adaptive source report unavailable')
    source=rows[0];chosen=source['summary']['selected']
    r=archive.session.get(archive._url(source['diagnostics']['snapshot']),headers=archive._headers(),timeout=60)
    if not r.ok:raise RuntimeError(f'Private source snapshot HTTP {r.status_code}')
    if hashlib.sha256(r.content).hexdigest()!=source['diagnostics']['snapshot_sha256']:raise ValueError('Source snapshot checksum mismatch')
    data=pd.read_csv(BytesIO(gzip.decompress(r.content)));data['date']=pd.to_datetime(data.date).dt.date
    frame,forecasts=quarterly_forecasts(data,source['diagnostics']['feature_sets'][chosen['feature_set']],chosen['window'])
    sides=select_sides(forecasts,float(chosen['cushion']),chosen['mode'])
    result=compare_sizing(frame,sides,UNIVERSE[a.pair].leverage);ranking=result.pop('ranking')
    run=str(uuid.uuid4());frame=frame.copy();frame['frozen_incumbent_side']=sides
    payload=gzip.compress(frame.to_csv(index=False).encode(),mtime=0);key=f'research/sizing-v1/{run}/replay.csv.gz';save(archive,key,payload)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2021-01-01','research_end':'2026-09-30',
      'candidate_count':len(ranking),'summary':{'model_type':'sizing_and_rules_v1','pair':a.pair,**result},'leaderboard':json.loads(ranking.to_json(orient='records')),
      'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'source_run_id':source['run_id'],'frozen_incumbent':chosen,
        'snapshot':key,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),'batch_budget':'18 pairs x 5 simple rules = 90 new signal hypotheses; sizing scenarios are diagnostics, not extra alpha claims',
        'limitations':['All sizing is hypothetical; 100% capital in leveraged ETFs implies large underlying exposure without account borrowing',
          'Sizing is not an edge; dollar scale changes no percentage return under the same fill assumptions',
          'Drawdowns use daily closes, not intraday lows; allocation impact on real fills is unmodeled',
          'Volatility target uses lagged proxy volatility times stated leverage, an approximation',
          'Selection uses 2021-2023 only; 2024-2026 inspected historical diagnostics',
          'Incumbent quarterly retrains on earlier quarters only; no current/future-quarter labels',
          'Simple rules and all allocations predeclared; no later-period choice of position size',
          'Vendor daily fill definitions, liquidity, survivor selection and multiple testing remain limitations']}}
    send_private_report(url,secret,json.loads(json.dumps(body,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))))
    print(f'{a.pair}: hypothetical sizing and rule study saved privately; no orders.',flush=True)


if __name__=='__main__':main()
