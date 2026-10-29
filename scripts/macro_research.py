"""Private price-only vs lagged VIX/Treasury macro comparison.

The FRED graph CSV is retrospectively available data, not an ALFRED vintage
feed. Uses prior-day market indicators only, no present-day future knowledge.
No brokerage actions, and this research does NOT support a trading edge claim.
"""
import os
import sys
import json
import uuid
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from trade_lab.archive import SupabaseArchive,month_windows
from trade_lab.ml import extract_month,fit_evaluate,FEATURES
from trade_lab.macro import fetch_fred_market_daily,append_previous_day_macro,MACRO_FEATURES
from scripts.ml_research import outcomes_by_day,full_aligned_days
from scripts.automated_research import send_private_report,required_env


def assemble(archive):
    blocks=[]; lag=[]; omitted=0
    for first,_ in month_windows(date(2019,1,1),date(2026,9,30)):
        bars=archive.load(first)
        if bars is None:raise ValueError('Missing archived month: '+first.isoformat())
        eligible,total=full_aligned_days(bars)
        omitted+=total-len(eligible)
        features,lag=extract_month(bars,lag)
        if features.empty:continue
        features=features.loc[features.date.isin(eligible)]
        if features.empty:continue
        day=bars.timestamp.dt.tz_convert('America/New_York').dt.date
        simulation=outcomes_by_day(bars.loc[day.isin(eligible)].copy(),features)
        blocks.append(simulation.dropna(subset=['tqqq_net_pct','sqqq_net_pct']))
    result=pd.concat(blocks,ignore_index=True).sort_values('timestamp').reset_index(drop=True)
    return result,omitted


def report_view(value):
    return {'chosen':value['selected'],'metrics':value['reports'],
            'qualified':bool(value['qualified'])}


def main():
    url=required_env('SUPABASE_URL');secret=required_env('SUPABASE_SECRET_KEY')
    archive=SupabaseArchive(url,secret,os.environ.get('SUPABASE_BUCKET','market-edge-history'))
    data,excluded=assemble(archive)
    market=fetch_fred_market_daily(start='2018-01-01',end='2026-09-30')
    both=append_previous_day_macro(data,market)
    both=both.dropna(subset=list(MACRO_FEATURES)).reset_index(drop=True)
    if len(both)<1000:raise ValueError('Macro source does not cover enough historical days')
    price=fit_evaluate(both,feature_columns=FEATURES)
    plus=fit_evaluate(both,feature_columns=(*FEATURES,*MACRO_FEATURES))
    rows=[]
    for name,study in [('price_only',price),('prior_day_vix_and_yields',plus)]:
        t=study['ranking'].copy()
        t.insert(0,'feature_set',name)
        rows.extend(t.to_dict(orient='records'))
    leaderboard=pd.DataFrame(rows).replace([np.inf,-np.inf],np.nan)
    leaderboard=leaderboard.astype(object).where(pd.notna(leaderboard),None)
    # 2024 is historical evaluation and NOT used for selecting models.
    summary={'model_type':'price_vs_prior_day_market_fundamentals',
            'base_price_only':report_view(price),
            'with_macro':report_view(plus),
            'go_no_go':'NO_VALIDATED_EDGE',
            'note':'2019-2022 training, 2023 selection, 2024 evaluation, already inspected 2025-2026 diagnostics. No live orders.'}
    import hashlib
    # Reproducibility hash of sourced historical macro observations.
    digest=hashlib.sha256(market.to_csv(index=False).encode('utf8')).hexdigest()
    body={'run_id':str(uuid.uuid4()),'code_sha':os.environ.get('GITHUB_SHA','manual'),
          'research_start':'2019-01-01','research_end':'2026-09-30',
          'candidate_count':len(leaderboard),'summary':summary,
          'leaderboard':leaderboard.to_dict(orient='records'),
          'diagnostics':{'macro_data_source':'FRED graph CSV, latest historical values (not real-time vintage)',
                         'macro_columns':list(MACRO_FEATURES),'macro_checksum_sha256':digest,
                         'matched_sessions':len(both),'excluded_incomplete_sessions':excluded,
                         'not_point_in_time_for_revised_macroeconomic_releases':True,
                         'sentiment_integrated':False,
                         'data_latency':'Observations strictly dated before trade day; live release timing not confirmed.',
                         'no_live_orders':True}}
    body=json.loads(json.dumps(body,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)))
    send_private_report(url,secret,body)
    print('Macro comparison archived in private Supabase. No live orders.')

if __name__=='__main__':main()