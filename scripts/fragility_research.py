"""Replay frozen sizing-study incumbents/challengers without selecting again."""
import argparse,gzip,json,os,sys,uuid,hashlib
from io import BytesIO
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.sizing_research import rule_sides
from trade_lab.fragility import run_fragility
from scripts.automated_research import required_env,send_private_report
from scripts.daily_screen import save


def main():
    p=argparse.ArgumentParser();p.add_argument('--pair',choices=list(UNIVERSE),required=True);a=p.parse_args()
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY');archive=SupabaseArchive(url,secret)
    r=archive.session.get(url.rstrip('/')+'/rest/v1/market_edge_research_runs',headers=archive._headers(),
      params={'select':'run_id,summary,diagnostics','summary->>model_type':'eq.sizing_and_rules_v1','summary->>pair':'eq.'+a.pair,
        'code_sha':'eq.c599c70dda70af030e7f0627712e30ab4287ee98','order':'created_at.desc','limit':'1'},timeout=60)
    if not r.ok:raise RuntimeError(f'Private source lookup HTTP {r.status_code}')
    rows=r.json()
    if len(rows)!=1:raise ValueError('Frozen sizing source unavailable')
    source=rows[0];r=archive.session.get(archive._url(source['diagnostics']['snapshot']),headers=archive._headers(),timeout=60)
    if not r.ok:raise RuntimeError(f'Private replay HTTP {r.status_code}')
    if hashlib.sha256(r.content).hexdigest()!=source['diagnostics']['snapshot_sha256']:raise ValueError('Replay checksum mismatch')
    frame=pd.read_csv(BytesIO(gzip.decompress(r.content)));frame['date']=pd.to_datetime(frame.date).dt.date
    strategies={'frozen_adaptive_incumbent':frame.frozen_incumbent_side.to_numpy(dtype=int)}
    rule=source['summary'].get('selected_rule')
    if rule:strategies['frozen_development_selected_rule']=rule_sides(frame)[rule]
    reports=run_fragility(frame,strategies)
    run=str(uuid.uuid4());payload=gzip.compress(json.dumps(reports,allow_nan=False).encode(),mtime=0)
    key=f'research/fragility-v1/{run}/all-diagnostics.json.gz';save(archive,key,payload)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2024-01-01','research_end':'2026-09-30',
      'candidate_count':len(strategies),'summary':{'model_type':'frozen_strategy_fragility_v1','pair':a.pair,
       'go_no_go':'NO_VALIDATED_EDGE','reports':reports,'selected_rule':rule},'leaderboard':[],
      'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'source_run_id':source['run_id'],
        'snapshot':key,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),
        'scope':'18 pairs, frozen strategies, 10/50/100% allocations; diagnostics only, no new winner selection',
        'limitations':['Skipping winners uses hindsight to assess fragility, not an executable strategy',
          'Signal delays count eligible observations, not guaranteed consecutive calendar sessions or intraday latency',
          'Missing-trade simulations and circular shifts are synthetic sensitivity controls, not fill evidence',
          'Bootstrap/circular comparisons do not adjust for historical strategy/universe selection',
          'Daily vendor prices and drawdowns omit auction/quote verification, intraday losses and size impact',
          'All results are previously inspected history; genuinely new prospective testing still required']}}
    send_private_report(url,secret,json.loads(json.dumps(body,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))))
    print(f'{a.pair}: frozen-strategy fragility diagnostics saved privately; no orders.',flush=True)


if __name__=='__main__':main()
