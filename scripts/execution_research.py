"""Audit retrospective minute execution paths, with explicit incomplete cases."""
import argparse,gzip,json,os,sys,uuid,hashlib
from io import BytesIO
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
import exchange_calendars as xcals
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.execution_refinement import MANIFEST,trade_days,validate_minutes,run_execution_audit
from trade_lab.market_data_requests import historical_bars
from scripts.full_equity_research import source_report
from scripts.automated_research import required_env,send_private_report
from scripts.daily_screen import save


def cached_session(archive,name,pair,day,opening,closing,key,secret):
    path=f'alpaca/sip/split/1min/execution-v1/{name}/{pair.bull}-{pair.bear}/{day}.json.gz'
    r=archive.session.get(archive._url(path),headers=archive._headers(),timeout=60)
    if r.ok:
        payload=r.content;stored=json.loads(gzip.decompress(payload))
        if stored.get('date')!=str(day) or stored.get('symbols')!=[pair.bull,pair.bear]:raise ValueError('Cached session identity mismatch')
        raw=pd.DataFrame(stored['bars'],columns=['timestamp','symbol','open','high','low','close','volume'])
    else:
        code,message=archive._storage_error(r)
        if code!='NoSuchKey' and not (code in ('','not_found') and message.lower()=='object not found'):
            raise RuntimeError(f'Private minute cache HTTP {r.status_code}')
        raw,request=historical_bars([pair.bull,pair.bear],opening,closing-pd.Timedelta(nanoseconds=1),'1Min',key,secret)
        checked=validate_minutes(raw,{pair.bull,pair.bear},opening,closing)
        stored={'date':str(day),'symbols':[pair.bull,pair.bear],'request':request,
                'retrieved_at':datetime.now(timezone.utc).isoformat(),
                'bars':json.loads(checked.assign(timestamp=checked.timestamp.astype(str)).to_json(orient='records')) if not checked.empty else []}
        payload=gzip.compress(json.dumps(stored,allow_nan=False).encode(),mtime=0);save(archive,path,payload)
    raw=validate_minutes(raw,{pair.bull,pair.bear},opening,closing)
    return raw,{'path':path,'sha256':hashlib.sha256(payload).hexdigest(),'date':str(day)}


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
    schedule={pd.Timestamp(day).date():(row.open,row.close) for day,row in cal.schedule.iterrows()}
    pair=UNIVERSE[a.pair];sessions={};provenance=[]
    for day in trade_days(data):
        if day not in schedule:raise ValueError('Trade date outside exchange schedule')
        opening,closing=schedule[day]
        sessions[day],meta=cached_session(archive,a.pair,pair,day,opening,closing,
            required_env('ALPACA_KEY_ID'),required_env('ALPACA_SECRET_KEY'))
        provenance.append(meta)
    result,replay=run_execution_audit(data,pair,schedule,sessions)
    run=str(uuid.uuid4());prefix=f'research/execution-v1/{run}'
    payload=gzip.compress(json.dumps(result,allow_nan=False).encode(),mtime=0)
    returns_payload=gzip.compress(replay.to_csv(index=False).encode(),mtime=0)
    report_path=prefix+'/audit.json.gz';returns_path=prefix+'/observed-path-returns.csv.gz'
    save(archive,report_path,payload);save(archive,returns_path,returns_payload)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2021-01-01','research_end':'2026-09-30',
      'candidate_count':96,'summary':{'model_type':'execution_refinement_v1','pair':a.pair,
        'go_no_go':'NO_VALIDATED_EDGE','manifest':result['manifest'],'manifest_sha256':result['manifest_sha256'],
        'selected':result['selected'],'coverage':result['coverage'],'reports':result['reports'],
        'largest_daily_winners_audit':result['largest_daily_winners_audit']},'leaderboard':result['ranking'],
      'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'allocation_percent':100,
        'source_run_id':source['run_id'],'source_snapshot_sha256':source['diagnostics']['snapshot_sha256'],
        'snapshot':report_path,'snapshot_sha256':hashlib.sha256(payload).hexdigest(),
        'path_returns':returns_path,'path_returns_sha256':hashlib.sha256(returns_payload).hexdigest(),'minute_sources':provenance,
        'budget':'4 pairs x 6 frozen volume-signal variants x 4 entry times x 4 exits = 384 configurations',
        'limitations':['Same-vendor cross-resolution check, not independent data-source verification or executable quote evidence',
          'Daily bars and regular-session minute intervals may represent different trade coverage; differences are retained, not labeled automatically erroneous',
          'Exact endpoints audited even when path incomplete; path-dependent replay requires every scheduled minute, including half-days',
          'Incomplete trade outcomes excluded only from clearly labeled observed-subset diagnostics, never silently replaced with cash or interpolated prices',
          'Missing any development trade makes a configuration ineligible for selection; 2024-2026 never selects parameters',
          'Targets are hypothetical touched-price fills, stop-first when both touched, gap-through-stop handling; no quote, queue or order-size evidence',
          'Minute-low adverse excursion is a per-trade diagnostic, not an account-wide intraday drawdown estimate',
          '2024-2026 already inspected and experiments motivated by that history; no fresh holdout or validated edge']}}
    send_private_report(url,secret,body)
    print(f'{a.pair}: minute audit and registered execution refinements saved privately; no orders.',flush=True)


if __name__=='__main__':main()
