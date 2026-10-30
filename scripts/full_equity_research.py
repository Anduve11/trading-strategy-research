"""Replay full account equity in paper research; contains no order API."""
import argparse,gzip,json,os,sys,uuid,hashlib
from io import BytesIO
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.full_allocation import run_full_equity
from scripts.automated_research import required_env,send_private_report
from scripts.daily_screen import save


def source_report(archive,url,pair,model,sha):
    r=archive.session.get(url.rstrip('/')+'/rest/v1/market_edge_research_runs',headers=archive._headers(),
      params={'select':'run_id,summary,diagnostics','summary->>model_type':'eq.'+model,'summary->>pair':'eq.'+pair,
              'code_sha':'eq.'+sha,'order':'created_at.desc','limit':'1'},timeout=60)
    if not r.ok:raise RuntimeError(f'Private source HTTP {r.status_code}')
    rows=r.json()
    if len(rows)!=1:raise ValueError('Frozen source unavailable')
    return rows[0]


def run_pair(archive,url,secret,pair):
    sizing=source_report(archive,url,pair,'sizing_and_rules_v1','c599c70dda70af030e7f0627712e30ab4287ee98')
    family=source_report(archive,url,pair,'family_factory_v1','683bb5438174f622e5b7f18edb8f6b8d26ca3693')
    checksum=sizing['diagnostics']['snapshot_sha256']
    if family['diagnostics']['source_snapshot_sha256']!=checksum:raise ValueError('Source lineage mismatch')
    r=archive.session.get(archive._url(sizing['diagnostics']['snapshot']),headers=archive._headers(),timeout=60)
    if not r.ok:raise RuntimeError(f'Private replay HTTP {r.status_code}')
    if hashlib.sha256(r.content).hexdigest()!=checksum:raise ValueError('Replay checksum mismatch')
    data=pd.read_csv(BytesIO(gzip.decompress(r.content)));data['date']=pd.to_datetime(data.date).dt.date
    result,replay=run_full_equity(data,family['summary'])
    run=str(uuid.uuid4());prefix=f'research/full-equity-v1/{run}'
    payload=gzip.compress(json.dumps(result,allow_nan=False).encode(),mtime=0)
    replay_payload=gzip.compress(replay.to_csv(index=False).encode(),mtime=0)
    report_key=prefix+'/full-report.json.gz';replay_key=prefix+'/signals.csv.gz'
    save(archive,report_key,payload);save(archive,replay_key,replay_payload)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2021-01-01','research_end':'2026-09-30',
      'candidate_count':55,'summary':{'model_type':'full_equity_v1','pair':pair,'go_no_go':'NO_VALIDATED_EDGE',
        'manifest':result['manifest'],'manifest_sha256':result['manifest_sha256'],
        'selected_growth':result['selected_growth'],'selected_fold_resilience':result['selected_fold_resilience'],
        'quarterly_decisions':[{k:v for k,v in row.items() if k!='ranking'} for row in result['quarterly_decisions']],
        'individual_reports':result['individual_reports'],'policy_reports':result['policy_reports'],
        'signal_diagnostics':result['signal_diagnostics']},
      'leaderboard':result['growth_ranking'],
      'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'user_requested_primary_allocation_percent':100,
        'source_run_ids':[sizing['run_id'],family['run_id']],'source_snapshot_sha256':checksum,
        'snapshot':report_key,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),
        'signal_replay':replay_key,'signal_replay_sha256':hashlib.sha256(replay_payload).hexdigest(),
        'batch_budget':'18 x 49 = 882 single-position replays; 18 x 4 = 72 new policy comparisons and 36 frozen policy controls. Allocation/cost/sensitivity scenarios are diagnostics, not new independent signals.',
        'limitations':['100% means current equity compounded on each qualifying entry, cash on no signal, no account borrowing',
          'Each ETF-pair report is an independent hypothetical account; returns cannot be added into one portfolio',
          'Fixed-slot ensemble control can leave cash; the separate active-weight ensemble deploys 100% across active legs',
          'At 3x ETF leverage, full-equity allocation can carry very large underlying exposure; intraday drawdowns are not measured',
          '50bps adverse cost is derived from the same observed close/open ratio, not invented market prices',
          'Development growth and fold-resilience choices use 2021-2023 only; quarterly growth uses earlier observations with two-observation embargo',
          'Growth policy cash gate tests positive historical training growth; it does not validate an edge',
          'No fresh holdout, prospective prediction, verified auction/quote fill or size-dependent liquidity model',
          'All 2024-2026 history already inspected; repeated universe, model and policy searches create selection bias',
          'Skip-winning-session tests use hindsight and are not executable strategies',
          'Returns exclude taxes, cash yield, and commissions beyond assumed adverse fill prices']}}
    send_private_report(url,secret,body)
    print(f'{pair}: full-equity paper replays saved privately; no orders.',flush=True)


def main():
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--pair',choices=list(UNIVERSE));group.add_argument('--all',action='store_true');a=p.parse_args()
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY');archive=SupabaseArchive(url,secret)
    pairs=([a.pair] if a.pair else ['semiconductors','semiconductors2']+
           [x for x in UNIVERSE if x not in ('semiconductors','semiconductors2')])
    failed=[]
    for pair in pairs:
        try:run_pair(archive,url,secret,pair)
        except Exception as exc:
            # Numeric results, source bodies and credentials stay private.
            print(f'{pair}: research failed ({type(exc).__name__}); continuing other pairs.',flush=True)
            failed.append(pair)
    if failed:raise RuntimeError('Full-equity research failed for: '+', '.join(failed))


if __name__=='__main__':main()
