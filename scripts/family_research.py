"""Auditable multi-family paper research; reuses checksummed private sources."""
import argparse,gzip,json,os,sys,uuid,hashlib
from io import BytesIO
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.research_factory import run_factory,stable_hash,audit_existing_reversals
from scripts.automated_research import required_env,send_private_report
from scripts.daily_screen import save


def main():
    p=argparse.ArgumentParser();p.add_argument('--pair',choices=list(UNIVERSE),required=True);a=p.parse_args()
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY');archive=SupabaseArchive(url,secret)
    r=archive.session.get(url.rstrip('/')+'/rest/v1/market_edge_research_runs',headers=archive._headers(),
      params={'select':'run_id,diagnostics','summary->>model_type':'eq.sizing_and_rules_v1','summary->>pair':'eq.'+a.pair,
              'code_sha':'eq.c599c70dda70af030e7f0627712e30ab4287ee98','order':'created_at.desc','limit':'1'},timeout=60)
    if not r.ok:raise RuntimeError(f'Private source HTTP {r.status_code}')
    rows=r.json()
    if len(rows)!=1:raise ValueError('Frozen source unavailable')
    source=rows[0];checksum=source['diagnostics']['snapshot_sha256']
    r=archive.session.get(archive._url(source['diagnostics']['snapshot']),headers=archive._headers(),timeout=60)
    if not r.ok:raise RuntimeError(f'Private replay HTTP {r.status_code}')
    if hashlib.sha256(r.content).hexdigest()!=checksum:raise ValueError('Replay checksum mismatch')
    data=pd.read_csv(BytesIO(gzip.decompress(r.content)));data['date']=pd.to_datetime(data.date).dt.date
    result,replay=run_factory(data)
    result['existing_reversal_sensitivity']=audit_existing_reversals(data)
    run=str(uuid.uuid4());sha=os.getenv('GITHUB_SHA','manual')
    prefix=f'research/family-v1/{run}'
    registry=[{'trial_id':stable_hash({'code_sha':sha,'source_sha256':checksum,'pair':a.pair,'candidate':row['candidate'],
                                     'manifest':result['manifest_sha256']}),
               'candidate':row['candidate'],'family':row['family'],'status':'COMPLETED_HISTORICAL_DIAGNOSTIC',
               'development':row,'inspected_reports':{period:reports[row['candidate']]
                    for period,reports in result['individual_reports'].items()}} for row in result['ranking']]
    result['trial_registry']=registry
    payload=gzip.compress(json.dumps(result,allow_nan=False).encode(),mtime=0)
    replay_payload=gzip.compress(replay.to_csv(index=False).encode(),mtime=0)
    report_key=prefix+'/full-report.json.gz';replay_key=prefix+'/policy-replay.csv.gz'
    save(archive,report_key,payload);save(archive,replay_key,replay_payload)
    decisions=[{k:v for k,v in d.items() if k!='ranking'} for d in result['quarterly_decisions']]
    body={'run_id':run,'code_sha':sha,'research_start':'2021-01-01','research_end':'2026-09-30','candidate_count':38,
      'summary':{'model_type':'family_factory_v1','pair':a.pair,'go_no_go':'NO_VALIDATED_EDGE',
                 'manifest':result['manifest'],'manifest_sha256':result['manifest_sha256'],
                 'selected_by_family':result['selected_by_family'],'quarterly_decisions':decisions,
                 'existing_reversal_sensitivity':result['existing_reversal_sensitivity'],
                 'policy_reports':result['policy_reports'],'individual_reports':result['individual_reports']},
      'leaderboard':result['ranking'],
      'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'source_run_id':source['run_id'],
        'source_snapshot_sha256':checksum,'snapshot':report_key,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),
        'policy_replay':replay_key,'policy_replay_sha256':hashlib.sha256(replay_payload).hexdigest(),
        'batch_budget':'18 x 36 rules = 648 signal hypotheses, plus 18 x 2 = 36 policy comparisons; also sensitivity checks on the previous 216 reversal candidates, not new signal hypotheses; no fresh holdout',
        'limitations':['Rules motivated by inspected history; no multiple-testing-adjusted significance or prospective claim',
          'All rules use lagged inputs, but vendor timestamps and real executable open/close prices remain unverified',
          'Quarterly selector uses at most 504 earlier eligible observations, two-observation embargo, four chronological training folds',
          'Policies hold cash without an eligible positive training score; score positivity does not prove an edge',
          'Six fixed equal-capital ensemble slots share 10% account allocation; inactive slots remain cash',
          'Simultaneous bull/inverse legs use separate ETF returns and costs, with no assumed order netting',
          'Daily-close drawdown omits intraday troughs; liquidity, size impact, survivor bias and benchmark differences remain',
          'Market-relative rule is a proxy-return difference, not a fitted beta residual; volume is lagged proxy volume',
          'Skip-best-five is a hindsight sensitivity diagnostic, not a tradable policy',
          'Cash earns zero here; no taxes or additional commissions beyond modeled adverse prices']}}
    send_private_report(url,secret,body)
    print(f'{a.pair}: registered family trials and policy comparisons saved privately; no orders.',flush=True)


if __name__=='__main__':main()
