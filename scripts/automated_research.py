"""Unattended, research-only GitHub Actions job.

Required server-side env: SUPABASE_URL, SUPABASE_SECRET_KEY. Optional Alpaca
keys allow archiving new *completed* months. Credentials are NEVER written
or printed. Results are written to a locked Supabase database table, not
GitHub logs or public artifacts.
"""
import os
import sys
import json
import uuid
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive, ArchivedFetcher
from trade_lab.alpaca import fetch_bars
from trade_lab.auto import search_candidates, evaluate_filters, run_summary
from trade_lab.research import run_study
from trade_lab.engine import Config


def required_env(name):
    v=os.environ.get(name,'').strip()
    if not v:
        raise RuntimeError(f'Missing GitHub Actions secret or variable: {name}. Configure it in repository Settings > Secrets and variables > Actions.')
    return v


def completed_month_end(today: date) -> date:
    return date(today.year,today.month,1)-timedelta(days=1)


def send_private_report(base_url: str,key: str, body: dict):
    url=base_url.rstrip('/')+'/rest/v1/market_edge_research_runs'
    headers={'apikey':key,'Content-Type':'application/json','Prefer':'return=minimal'}
    if key.startswith('eyJ'):
        headers['Authorization']='Bearer '+key
    resp=requests.post(url,json=body,headers=headers,timeout=60)
    if not resp.ok:
        # Supabase may include sensitive details in an error body. Do not log it.
        raise RuntimeError(f'Private research report storage failed (HTTP {resp.status_code}). Check Supabase table and service credentials.')


def main():
    project_url=required_env('SUPABASE_URL')
    secret=required_env('SUPABASE_SECRET_KEY')
    bucket=os.environ.get('SUPABASE_BUCKET','market-edge-history')
    archive=SupabaseArchive(project_url,secret,bucket)
    alpaca_key=os.environ.get('ALPACA_KEY_ID','').strip()
    alpaca_secret=os.environ.get('ALPACA_SECRET_KEY','').strip()
    both=bool(alpaca_key and alpaca_secret)
    if bool(alpaca_key) != bool(alpaca_secret):
        raise RuntimeError('Set BOTH ALPACA_KEY_ID and ALPACA_SECRET_KEY or leave both unset.')
    def download_missing(a,b):
        if not both:
            raise ValueError(f'Missing archived month beginning {a}; configure Alpaca paper market-data keys for automatic additions.')
        return fetch_bars(alpaca_key,alpaca_secret,a,b,feed='sip')
    fetcher=ArchivedFetcher(archive,download_missing)
    # Freeze the already inspected 2019-2026 study; DO NOT change its partitions
    # while chasing improved performance. Future data will require a separate
    # prospective monitoring report and cannot be folded into model selection.
    start=date(2019,1,1)
    end=date(2026,9,30)
    base=Config(initial_capital=10000,allocation_pct=10,
                slippage_bps_each_side=5,fee_bps_each_side=0)
    candidates=search_candidates()
    print(f'Research-only baseline: {len(candidates)} simulated exits x 8 predeclared regime filters. No orders.')
    study=run_study(fetcher,start,end,base,candidates=candidates)
    leaderboard=evaluate_filters(study,allocation_pct=base.allocation_pct,initial_capital=base.initial_capital,min_dev_trades=100)
    summary=run_summary(leaderboard)
    # Keep a useful comparison but do NOT use diagnostic results for ranking.
    columns=['test_id','candidate','regime_filter','qualified_dev','dev_score',
             'dev_trades','dev_return_pct','dev_max_drawdown_pct','dev_profit_factor',
             'val_trades','val_return_pct','val_max_drawdown_pct','val_profit_factor',
             'historical_diagnostic_trades','historical_diagnostic_return_pct',
             'historical_diagnostic_max_drawdown_pct']
    top=leaderboard.head(100)[columns].where(leaderboard.head(100)[columns].notna(),None)
    # Native scalar conversion avoids JSON errors on NumPy values.
    records=json.loads(top.to_json(orient='records'))
    run_id=str(uuid.uuid4())
    body={
        'run_id':run_id,'code_sha':os.environ.get('GITHUB_SHA','local'),
        'research_start':start.isoformat(),'research_end':end.isoformat(),
        'candidate_count':len(leaderboard),'summary':summary,
        'leaderboard':records,
        'diagnostics':{'base_candidates':len(candidates),'regime_filters':8,
                       'months_read':fetcher.cache_hits+fetcher.saved,
                       'new_months_archived':fetcher.saved,
                       'holdout_reused_for_selection':False,
                       'historical_diagnostic_period_already_inspected':True,
                       'forward_testing_begins_after':'2026-10-29',
                       'note':'No proven trading edge. Historical fits are not future guarantees.'}
    }
    send_private_report(project_url,secret,body)
    print(f'Research completed: {len(leaderboard)} configurations. Summary saved privately; run ID {run_id}.')


if __name__=='__main__':
    main()