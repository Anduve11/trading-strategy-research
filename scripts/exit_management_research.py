"""Partial targets, timed exits and trailing bounds on observed ETF bars."""
import argparse,gzip,json,os,sys,uuid,hashlib
from io import BytesIO
from pathlib import Path
import pandas as pd
import exchange_calendars as xcals
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.exit_management import MANIFEST,run_exit_management
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
            required_env('ALPACA_KEY_ID'),required_env('ALPACA_SECRET_KEY'));provenance.append(meta)
    result,replay=run_exit_management(data,pair,calendar,sessions)
    run=str(uuid.uuid4());prefix=f'research/exit-management-v1/{run}'
    payload=gzip.compress(json.dumps(result,allow_nan=False).encode(),mtime=0)
    returns=gzip.compress(replay.to_csv(index=False).encode(),mtime=0)
    snapshot=prefix+'/full-report.json.gz';return_key=prefix+'/exit-returns.csv.gz'
    save(archive,snapshot,payload);save(archive,return_key,returns)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2021-01-01','research_end':'2026-09-30',
      'candidate_count':54,'summary':{'model_type':'exit_management_v1','pair':a.pair,'selected':result['selected'],
        'go_no_go':'NO_VALIDATED_EDGE','manifest':result['manifest'],'manifest_sha256':result['manifest_sha256'],'reports':result['reports']},
      'leaderboard':result['ranking'],'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'allocation_percent':100,
        'source_run_id':source['run_id'],'source_snapshot_sha256':source['diagnostics']['snapshot_sha256'],
        'snapshot':snapshot,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),'minute_sources':provenance,
        'return_snapshot':return_key,'return_snapshot_sha256':hashlib.sha256(returns).hexdigest(),
        'budget':'3 pairs x 2 direction restrictions x 3 entries x 9 exits = 162 configurations',
        'limitations':['Previously inspected history; no fresh holdout, prospective claim or validated edge',
          'Trailing outcomes are conservative bounds across compatible minute OHLC orderings, not verified stop fills',
          'Partial targets assume a touched fixed-price limit fills at adverse costs; no order queue or quote evidence',
          'Proceeds of a half-sale remain cash; no intratrade reinvestment, borrowing or additional account allocation',
          'Endpoint exits do not require invented intervening bars; unknown path-sensitive outcomes stay missing',
          'Coverage can differ by exit; matched same-date close controls are reported explicitly',
          'Any missing planned development trade makes a configuration ineligible; labels of incomplete inspected subsets are retained',
          'Volatility scale uses lagged proxy volatility times stated leverage as an approximation',
          'Daily-close drawdown omits intraday lows; actual spreads, dollar-size market impact and taxes unverified']}}
    send_private_report(url,secret,body)
    print(f'{a.pair}: registered exit-management study saved privately; no orders.',flush=True)


if __name__=='__main__':main()
