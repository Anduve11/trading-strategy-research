"""Private, unattended 2019-2026 ML benchmark using existing monthly archive.

Runs with encrypted GitHub Actions Supabase secrets. No trading orders or
new price downloads. No private API credentials appear in output.
"""
import os
import sys
import uuid
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from trade_lab.archive import SupabaseArchive, month_windows
from trade_lab.data import audit_bar_coverage
from trade_lab.engine import simulate, Config
from trade_lab.ml import extract_month, fit_evaluate
from scripts.automated_research import send_private_report, required_env


END=date(2026,9,30)
START=date(2019,1,1)


def outcomes_by_day(bars, features):
    """Simulate both hypothetical sides for same predeclared 09:51 entry.

    Each price is from that ETF's own historical bars. Conservative stop-first
    rule, fixed 1.5% profit / 1% stop and 5 bps adverse slippage/side.
    """
    if features.empty:return features.copy()
    cfg=Config(target_pct=1.5,stop_pct=1.0,slippage_bps_each_side=5,
               fee_bps_each_side=0,allocation_pct=10,initial_capital=10000.)
    bysym={sym:x.set_index('timestamp').sort_index() for sym,x in bars.groupby('symbol')}
    result=features.copy()
    for side, symbol, column in ((1,'TQQQ','tqqq_net_pct'),(-1,'SQQQ','sqqq_net_pct')):
        sig=features[['date','timestamp']].copy()
        sig=sig.rename(columns={'date':'day'})
        sig['signal']=side
        trades,_=simulate(bars,cfg,precomputed_signals=sig,precomputed_prices=bysym)
        if not trades.empty:
            returns=trades.set_index('date')['net_return_pct']
            result[column]=result.date.map(returns)
        else:result[column]=np.nan
    return result


def main():
    url=required_env('SUPABASE_URL'); key=required_env('SUPABASE_SECRET_KEY')
    bucket=os.environ.get('SUPABASE_BUCKET','market-edge-history')
    archive=SupabaseArchive(url,key,bucket)
    blocks=[]; prior=[]; good_months=0; rejected=0
    for begin,_ in month_windows(START,END):
        bars=archive.load(begin)
        if bars is None:raise RuntimeError(f'Archive missing historical month {begin:%Y-%m}; no research fallback.')
        coverage=audit_bar_coverage(bars)
        if coverage['aligned_minutes_pct']<99.0:raise RuntimeError(f'Unsynchronized ETF prices for {begin:%Y-%m}')
        f,prior=extract_month(bars,prior)
        if not f.empty:
            combined=outcomes_by_day(bars,f)
            missing=int(combined[['tqqq_net_pct','sqqq_net_pct']].isna().any(axis=1).sum())
            rejected+=missing
            combined=combined.dropna(subset=['tqqq_net_pct','sqqq_net_pct'])
            blocks.append(combined)
        good_months+=1
        if good_months%12==0:print(f'Archived monthly data audited through {begin:%Y-%m}; prepared {sum(len(b) for b in blocks)} decision-time samples.')
    data=pd.concat(blocks,ignore_index=True).sort_values('timestamp').reset_index(drop=True)
    if len(data)<1000:raise RuntimeError('Too few complete decision-time feature rows')
    outcome=fit_evaluate(data)
    rank=outcome['ranking']
    leader=outcome['selected']
    diag={'feature_columns':list(data.columns.difference(['date','timestamp','target_up','forward_return_60m','entry_open_qqq','tqqq_net_pct','sqqq_net_pct'])),
          'feature_decision_time':'09:50 ET completed minute; TQQQ/SQQQ simulated entry 09:51 ET',
          'label':'QQQ return sign from 09:51 open to 10:51 close',
          'feature_rows':int(len(data)),'archive_months':good_months,'rejected_missing_execution':rejected,
          'no_sentiment_in_this_run':True,'macro_features_in_this_run':False,
          'previously_inspected_period':'2025-2026 diagnostic ONLY',
          'all_hypothetical':True,'no_live_orders':True,
          'exit_rule':'ETF +1.5% target / -1.0% stop; stop-first on ambiguous minute; forced EOD',
          'slippage_bps_each_side':5,'position_allocation_percent':10,
          'training_period':'2019-2022','parameter_selection_period':'2023',
          'historical_evaluation':'2024; not guaranteed untouched at the overall project level',
          'future_prospective_testing':'required; no out-of-sample claim for 2025+ watched prices'}
    summary={'model_type':'09:50_directional_classifier',
             'selected':leader,'candidate_count':int(len(rank)),
             'go_no_go':'NO_VALIDATED_EDGE',
             'reports':outcome['reports'],
             'note':'Predictions and hypothetical fills do not establish profitability; avoid trading until independent prospective validation.'}
    # Results live alongside rule-based experiments but are clearly separately typed.
    table=rank.head(100).replace([np.inf,-np.inf],np.nan)
    table=table.astype(object).where(pd.notna(table),None)
    results={
        'run_id':str(uuid.uuid4()),'code_sha':os.environ.get('GITHUB_SHA','manual'),
        'research_start':START.isoformat(),'research_end':END.isoformat(),
        'candidate_count':int(len(rank)),
        'summary':summary,'leaderboard':table.to_dict(orient='records'),
        'diagnostics':diag
    }
    import json
    results=json.loads(json.dumps(results,default=lambda x:x.item() if hasattr(x,'item') else str(x),allow_nan=False))
    send_private_report(url,key,results)
    print('ML research completed. Classification, trade outcomes and ranked models saved privately. No live orders.')


if __name__=='__main__':main()