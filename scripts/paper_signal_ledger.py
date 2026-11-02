"""Immutable prospective signals and later hypothetical reconciliation; no orders."""
import gzip,json,os,sys,uuid,hashlib
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
import exchange_calendars as xcals
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.paper_signals import MANIFEST,target_session,freeze_signal,reconcile_signal
from trade_lab.market_data_requests import historical_bars
from scripts.daily_screen import save
from scripts.automated_research import required_env,send_private_report


def optional_blob(archive,path):
    r=archive.session.get(archive._url(path),headers=archive._headers(),timeout=60)
    if r.ok:return r.content
    code,message=archive._storage_error(r)
    if code=='NoSuchKey' or (code in ('','not_found') and message.lower()=='object not found'):return None
    raise RuntimeError(f'Private ledger HTTP {r.status_code}')


def key_for(day,name,suffix='prediction'):
    return f'paper/volume-reversal-forward-v1/{day}/{name}/{suffix}.json.gz'


def main():
    now=pd.Timestamp(datetime.now(timezone.utc))
    cal=xcals.get_calendar('XNYS',start=(now-pd.Timedelta(days=400)).date(),end=(now+pd.Timedelta(days=40)).date())
    target,prior,history,final_after=target_session(cal.schedule,now)
    day=str(pd.Timestamp(target).date());previous_day=str(pd.Timestamp(prior).date())
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY');archive=SupabaseArchive(url,secret)
    key,api_secret=required_env('ALPACA_KEY_ID'),required_env('ALPACA_SECRET_KEY')
    checks=[];new_predictions=0
    for name in MANIFEST['pairs']:
        pair=UNIVERSE[name];check={'pair':name,'target_session':day}
        # Reconcile only an already-recorded signal after its session closes.
        past=optional_blob(archive,key_for(previous_day,name))
        if past and now>=cal.schedule.loc[prior,'close']+pd.Timedelta(minutes=30):
            old=json.loads(gzip.decompress(past));outcome_path=key_for(previous_day,name,'outcome')
            if optional_blob(archive,outcome_path) is None:
                raw=pd.DataFrame()
                if old['side']:
                    raw,_=historical_bars([old['symbol']],pd.Timestamp(old['target_open']),
                        pd.Timestamp(old['target_close'])-pd.Timedelta(nanoseconds=1),'1Min',key,api_secret)
                outcome=reconcile_signal(old,raw)
                outcome.update(reconciled_at=datetime.now(timezone.utc).isoformat(),prediction_sha256=hashlib.sha256(past).hexdigest())
                observed=gzip.compress(raw.to_json(orient='records').encode(),mtime=0)
                observed_path=key_for(previous_day,name,'reconciliation-input-'+str(uuid.uuid4()))
                save(archive,observed_path,observed)
                outcome.update(observed_snapshot=observed_path,observed_sha256=hashlib.sha256(observed).hexdigest())
                # Missing endpoints are a retained attempt, never a final fill.
                destination=outcome_path if outcome['status']!='MISSING_EXACT_ENDPOINTS' else key_for(previous_day,name,'incomplete-attempt-'+str(uuid.uuid4()))
                save(archive,destination,gzip.compress(json.dumps(outcome,allow_nan=False).encode(),mtime=0))
                check['previous_reconciliation_status']=outcome['status']
        if optional_blob(archive,key_for(day,name)) is not None:
            check['prediction_status']='ALREADY_LOGGED_IMMUTABLE'
        elif now<final_after:
            check['prediction_status']='WAITING_FOR_PRIOR_DAILY_FINALITY'
        else:
            first=pd.Timestamp(history[0]).date();last=pd.Timestamp(prior).date()
            start=pd.Timestamp(first).tz_localize('America/New_York').tz_convert('UTC')
            end=(pd.Timestamp(last).tz_localize('America/New_York')+pd.DateOffset(days=1)-pd.Timedelta(nanoseconds=1)).tz_convert('UTC')
            raw,request=historical_bars([pair.proxy],start,end,'1Day',key,api_secret)
            created=pd.Timestamp(datetime.now(timezone.utc))
            record=freeze_signal(raw,name,pair,cal.schedule,created,os.getenv('GITHUB_SHA','manual'))
            if record['target_session']!=day:raise ValueError('Signal crossed pre-entry deadline; refusing late record')
            snapshot=gzip.compress(raw.to_json(orient='records').encode(),mtime=0)
            snapshot_path=key_for(day,name,'source')
            record.update(source_snapshot=snapshot_path,source_sha256=hashlib.sha256(snapshot).hexdigest(),
                          source_request=request,source_first_seen_at=created.isoformat())
            save(archive,snapshot_path,snapshot)
            save(archive,key_for(day,name),gzip.compress(json.dumps(record,allow_nan=False).encode(),mtime=0))
            new_predictions+=1;check.update(prediction_status='FROZEN_BEFORE_ENTRY',prediction_id=record['prediction_id'],
                                            prediction_path=key_for(day,name))
        checks.append(check)
        print(f'{name}: paper-ledger check complete; no orders.',flush=True)
    run=str(uuid.uuid4())
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':day,'research_end':day,
      'candidate_count':4,'summary':{'model_type':'paper_signal_ledger_v1','go_no_go':'NO_VALIDATED_EDGE',
        'target_session':day,'new_predictions_written':new_predictions,'checks':checks,'manifest':MANIFEST},'leaderboard':[],
      'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'count_unit':'4 frozen signal candidates; 0/5-minute entry reconciliation scenarios',
        'limitations':['Prospective evidence starts only with successfully timestamped pre-entry records; never backfill predictions',
          'Observed minute endpoints remain hypothetical fills; quotes, market impact and dollar sizing unverified',
          'Separate paper accounts per pair; no live allocation or combined portfolio is implied',
          'Vendor daily-bar finality buffer is an operational convention, not a guarantee against later revisions']}}
    send_private_report(url,secret,body)


if __name__=='__main__':main()
