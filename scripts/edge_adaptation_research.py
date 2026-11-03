"""Replay past-opportunity controllers on cached observed endpoints; no orders."""
import argparse,gzip,json,os,sys,uuid,hashlib
from pathlib import Path
from io import BytesIO
import pandas as pd
import exchange_calendars as xcals
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.edge_adaptation import MANIFEST,run_adaptation
from trade_lab.execution_refinement import trade_days
from scripts.execution_research import cached_session
from scripts.full_equity_research import source_report
from scripts.automated_research import required_env,send_private_report
from scripts.daily_screen import save


def main():
    p=argparse.ArgumentParser();p.add_argument('--pair',choices=MANIFEST['pairs'],required=True);a=p.parse_args()
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY');archive=SupabaseArchive(url,secret)
    source=source_report(archive,url,a.pair,'sizing_and_rules_v1','c599c70dda70af030e7f0627712e30ab4287ee98')
    r=archive.session.get(archive._url(source['diagnostics']['snapshot']),headers=archive._headers(),timeout=60)
    if not r.ok:raise RuntimeError(f'Private source HTTP {r.status_code}')
    if hashlib.sha256(r.content).hexdigest()!=source['diagnostics']['snapshot_sha256']:raise ValueError('Source checksum mismatch')
    data=pd.read_csv(BytesIO(gzip.decompress(r.content)));data['date']=pd.to_datetime(data.date).dt.date
    data=data.sort_values('date').reset_index(drop=True)
    cal=xcals.get_calendar('XNYS',start='2021-01-01',end='2026-09-30')
    calendar={pd.Timestamp(day).date():(row.open,row.close) for day,row in cal.schedule.iterrows()}
    sessions={};provenance=[];pair=UNIVERSE[a.pair]
    for day in trade_days(data):
        sessions[day],meta=cached_session(archive,a.pair,pair,day,*calendar[day],
            required_env('ALPACA_KEY_ID'),required_env('ALPACA_SECRET_KEY'))
        provenance.append(meta)
    result=run_adaptation(data,pair,calendar,sessions)
    run=str(uuid.uuid4());prefix=f'research/edge-adaptation-v1/{run}'
    payload=gzip.compress(json.dumps(result,allow_nan=False).encode(),mtime=0)
    snapshot=prefix+'/full-report.json.gz';save(archive,snapshot,payload)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2021-01-01','research_end':'2026-09-30',
      'candidate_count':108,'summary':{'model_type':'edge_adaptation_v1','pair':a.pair,'selected':result['selected'],
        'go_no_go':'NO_VALIDATED_EDGE','manifest':result['manifest'],'manifest_sha256':result['manifest_sha256'],
        'reports':result['reports'],'baseline_reports':result['baseline_reports']},'leaderboard':result['ranking'],
      'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'allocation_percent':100,
        'source_run_id':source['run_id'],'source_snapshot_sha256':source['diagnostics']['snapshot_sha256'],
        'snapshot':snapshot,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),'minute_sources':provenance,
        'budget':'4 pairs x 3 thresholds x 3 opportunity windows x 2 controller modes x 2 direction restrictions x 3 entry delays = 432 configurations',
        'limitations':['Controller introduced after inspecting previous results; all evaluation years already inspected, no fresh holdout',
          '2021 is controller warmup; 2022-2023 select, require 20 total and 5 annual development trades, positive cost-20bps log score',
          'Decisions emitted before reading current session outcomes; updates use earlier completed opportunities only',
          'History includes observed counterfactual returns of both ETFs even on cash days; missing pairs do not become zero returns',
          'Time-only strategy needs exact entry/exit endpoints, not intervening OHLC; no stop/target or fabricated bars',
          'Any missing planned development trade makes a policy ineligible; later incomplete results remain explicitly labeled observed subsets',
          'Observed minute endpoints are hypothetical fills; quotes, auction participation, intraday drawdown and size impact remain unverified',
          'Independent per-pair paper accounts, 100% equity on active trades, no borrowing or real orders']}}
    send_private_report(url,secret,body)
    print(f'{a.pair}: causal opportunity-controller research saved privately; no orders.',flush=True)


if __name__=='__main__':main()
