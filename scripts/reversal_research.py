"""Run declared reversal refinements on immutable private replay data."""
import argparse,gzip,json,os,sys,uuid,hashlib
from io import BytesIO
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.reversal_research import run_reversals
from scripts.automated_research import required_env,send_private_report
from scripts.daily_screen import save


def main():
    p=argparse.ArgumentParser();p.add_argument('--pair',choices=list(UNIVERSE),required=True);a=p.parse_args()
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY')
    archive=SupabaseArchive(url,secret)
    r=archive.session.get(url.rstrip('/')+'/rest/v1/market_edge_research_runs',headers=archive._headers(),
      params={'select':'run_id,diagnostics','summary->>model_type':'eq.sizing_and_rules_v1','summary->>pair':'eq.'+a.pair,
              'code_sha':'eq.c599c70dda70af030e7f0627712e30ab4287ee98','order':'created_at.desc','limit':'1'},timeout=60)
    if not r.ok:raise RuntimeError(f'Private source lookup HTTP {r.status_code}')
    rows=r.json()
    if len(rows)!=1:raise ValueError('Frozen source unavailable')
    source=rows[0]
    r=archive.session.get(archive._url(source['diagnostics']['snapshot']),headers=archive._headers(),timeout=60)
    if not r.ok:raise RuntimeError(f'Private source replay HTTP {r.status_code}')
    if hashlib.sha256(r.content).hexdigest()!=source['diagnostics']['snapshot_sha256']:
        raise ValueError('Replay checksum mismatch')
    data=pd.read_csv(BytesIO(gzip.decompress(r.content)));data['date']=pd.to_datetime(data.date).dt.date
    result=run_reversals(data);ranking=result.pop('ranking')
    run=str(uuid.uuid4());payload=gzip.compress(json.dumps(result,allow_nan=False).encode(),mtime=0)
    key=f'research/reversal-v1/{run}/all-diagnostics.json.gz';save(archive,key,payload)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2021-01-01','research_end':'2026-09-30',
      'candidate_count':12,'summary':{'model_type':'reversal_refinements_v1','pair':a.pair,**result},'leaderboard':ranking,
      'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'source_run_id':source['run_id'],
        'snapshot':key,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),
        'batch_budget':'18 pairs x 3 thresholds x 4 filters = 216 declared hypotheses; full grid retained',
        'selection':'2021-2023 only, 20bps adverse cost per side, 10% allocation; worst annual return + .25 mean annual return - .5 worst annual drawdown magnitude; minimum 75 trades overall and 10 per year',
        'limitations':['Refinements motivated by previously inspected results; no fresh holdout or post-selection significance claim',
          '2024-2026 are inspected diagnostics, never used to rank this grid',
          'Threshold units use prior proxy annualized volatility divided by sqrt(252), with .1% daily floor',
          'Trend filters and directional efficiency use lagged predictors, not entry-day information',
          'Vendor open-close fills remain hypothetical; no verified auction prices, intraday drawdown or size impact',
          'Cached surviving ETF universe, proxy benchmark differences and repeated testing remain limitations']}}
    send_private_report(url,secret,body)
    print(f'{a.pair}: declared reversal grid saved privately; no orders.',flush=True)


if __name__=='__main__':main()
