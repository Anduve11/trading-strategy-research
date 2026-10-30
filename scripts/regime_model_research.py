"""Archive Cboe once, then run declared daily growth/quantile experiments."""
import argparse,gzip,json,os,sys,uuid,hashlib
from datetime import datetime,timezone
from io import BytesIO
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trade_lab.archive import SupabaseArchive
from trade_lab.daily_screen import UNIVERSE
from trade_lab.edge_research import fetch_option_history
from trade_lab.regime_models import build_features,run_models
from scripts.automated_research import required_env,send_private_report
from scripts.daily_screen import save
from scripts.full_equity_research import source_report
from scripts.universe_research import enough_data


def download(archive,path):
    r=archive.session.get(archive._url(path),headers=archive._headers(),timeout=60)
    if not r.ok:raise RuntimeError(f'Private artifact HTTP {r.status_code}')
    return r.content


def prepare(archive,prefix):
    market,checksums=fetch_option_history()
    market=market.loc[market.date.between('2018-01-01','2026-09-30')].copy()
    if len(market.dropna())<1500:raise ValueError('Insufficient option-index history')
    payload=gzip.compress(market.to_csv(index=False).encode(),mtime=0)
    meta={'snapshot':prefix+'/cboe.csv.gz','snapshot_sha256':hashlib.sha256(payload).hexdigest(),
          'retrieved_at':datetime.now(timezone.utc).isoformat(),'raw_source_sha256':checksums,
          'source':'Official Cboe VIX/VIX9D/VVIX daily CSV histories, retrospective not first-seen vintages'}
    save(archive,meta['snapshot'],payload)
    save(archive,prefix+'/cboe-manifest.json.gz',gzip.compress(json.dumps(meta).encode(),mtime=0))
    print('Cboe input archived privately with checksums; frozen research dates.',flush=True)


def run_pair(archive,url,secret,pair,prefix):
    source=source_report(archive,url,pair,'adaptive_cost_aware_v1','980a62b51881793ef87a29b29f61fb18f0bb7e4e')
    payload=download(archive,source['diagnostics']['snapshot'])
    if hashlib.sha256(payload).hexdigest()!=source['diagnostics']['snapshot_sha256']:raise ValueError('Source checksum mismatch')
    base=pd.read_csv(BytesIO(gzip.decompress(payload)));base['date']=pd.to_datetime(base.date).dt.date
    meta=json.loads(gzip.decompress(download(archive,prefix+'/cboe-manifest.json.gz')))
    payload=download(archive,meta['snapshot'])
    if hashlib.sha256(payload).hexdigest()!=meta['snapshot_sha256']:raise ValueError('Cboe checksum mismatch')
    market=pd.read_csv(BytesIO(gzip.decompress(payload)));market['date']=pd.to_datetime(market.date)
    data=build_features(base,market)
    if not enough_data(data):raise ValueError('Insufficient matched feature coverage')
    result,replay=run_models(data);run=str(uuid.uuid4());root=f'research/regime-ml-v1/{run}'
    report_payload=gzip.compress(json.dumps(result,allow_nan=False).encode(),mtime=0)
    replay_payload=gzip.compress(replay.to_csv(index=False).encode(),mtime=0)
    feature_payload=gzip.compress(data.to_csv(index=False).encode(),mtime=0)
    report_key=root+'/full-report.json.gz';replay_key=root+'/forecasts-signals.csv.gz';feature_key=root+'/matched-features.csv.gz'
    save(archive,report_key,report_payload);save(archive,replay_key,replay_payload);save(archive,feature_key,feature_payload)
    body={'run_id':run,'code_sha':os.getenv('GITHUB_SHA','manual'),'research_start':'2019-01-01','research_end':'2026-09-30',
      'candidate_count':48,'summary':{'model_type':'regime_models_v1','pair':pair,'selected':result['selected'],
        'go_no_go':'NO_VALIDATED_EDGE','manifest':result['manifest'],'manifest_sha256':result['manifest_sha256'],
        'selected_reports':result['selected_reports'],'baseline_reports':result['baseline_reports'],
        'individual_reports':result['individual_reports']},'leaderboard':result['ranking'],
      'diagnostics':{'no_live_orders':True,'no_capital_moved':True,'allocation_percent':100,
        'source_run_id':source['run_id'],'source_snapshot_sha256':source['diagnostics']['snapshot_sha256'],
        'cboe_source':meta,'snapshot':report_key,'snapshot_sha256':hashlib.sha256(report_payload).hexdigest(),
        'forecast_replay':replay_key,'forecast_replay_sha256':hashlib.sha256(replay_payload).hexdigest(),
        'feature_snapshot':feature_key,'feature_snapshot_sha256':hashlib.sha256(feature_payload).hexdigest(),
        'fit_log':result['fit_log'],'coverage_by_year':{str(k):int(v) for k,v in data.groupby(pd.to_datetime(data.date).dt.year).size().items()},
        'batch_budget':'18 pairs x 3 models x 2 matched feature groups x 2 cushions x 2 filters x 2 direction restrictions = 864 hypotheses',
        'limitations':['New model/factor experiments motivated by already-inspected history; no fresh holdout or prospective record',
          'Cboe adds option-implied index context to daily models, not option chains, dealer positioning or historical tradable spreads',
          'Official index histories and FRED market observations are retrospective; real publication and first-seen latency unverified',
          'Rolling windows count eligible observations; predictor histories may cross missing vendor sessions',
          'Expected-log models and median/25th-quantile models have different objectives; predicted quantiles are not guaranteed loss bounds',
          '40 development trades and 5 per year allow sparse signals; sample size and repeated testing limit confidence',
          'Quarterly refits use earlier observations only; previous evaluation quarters can inform later fits',
          'Vendor daily fills, intraday risk, actual spreads and dollar-size impact remain unverified',
          'All ETF-pair accounts independent, 100% current equity on active single-position signals, zero cash yield',
          'No new accounting fundamentals, earnings feed, options chain, SEC data or sentiment model is claimed by this batch']}}
    send_private_report(url,secret,body)
    print(f'{pair}: declared regime-model results saved privately; no orders.',flush=True)


def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare',action='store_true');g.add_argument('--pair',choices=list(UNIVERSE))
    p.add_argument('--prefix',required=True);a=p.parse_args()
    url,secret=required_env('SUPABASE_URL'),required_env('SUPABASE_SECRET_KEY');archive=SupabaseArchive(url,secret)
    if a.prepare:prepare(archive,a.prefix)
    else:run_pair(archive,url,secret,a.pair,a.prefix)


if __name__=='__main__':main()
