"""Deterministic high-throughput retrospective search built from real trade logs.

This never submits orders. Candidate-specific exit fills are simulated once;
regime filters are replayed from *prior-session-only* regime classifications.
All candidate selection uses development observations exclusively.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .research import Candidate
from .signals import STRATEGIES

TARGETS = (0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)
STOPS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
FILTERS = ('all', 'uptrend', 'downtrend', 'sideways', 'high_vol',
           'normal_vol', 'downtrend_high_vol', 'uptrend_normal_vol')


def search_candidates() -> list[Candidate]:
    return [Candidate(s, tp, sl) for s in STRATEGIES for tp in TARGETS for sl in STOPS]


def filter_mask(frame: pd.DataFrame, mode: str) -> pd.Series:
    r = frame['regime'].fillna('Insufficient history').astype(str)
    if mode == 'all':
        return pd.Series(True, index=frame.index)
    if mode == 'uptrend':
        return r.str.startswith('Uptrend /')
    if mode == 'downtrend':
        return r.str.startswith('Downtrend /')
    if mode == 'sideways':
        return r.str.startswith('Sideways /')
    if mode == 'high_vol':
        return r.str.endswith('/ High volatility')
    if mode == 'normal_vol':
        return r.str.endswith('/ Normal volatility')
    if mode == 'downtrend_high_vol':
        return r.eq('Downtrend / High volatility')
    if mode == 'uptrend_normal_vol':
        return r.eq('Uptrend / Normal volatility')
    raise ValueError('Unknown market regime filter: '+mode)


def replay_returns(trades: pd.DataFrame, allocation_pct: float=10.0,
                   initial_equity: float=10000.0) -> dict:
    """Recompound selected trade returns, preserving chronological ordering.

    Values in `net_return_pct` are for the invested position, NOT entire account.
    No-trade days contribute zero. OOS phase returns are evaluated separately at
    the same starting equity so performance across years is comparable.
    """
    if not 0 < allocation_pct <= 100:
        raise ValueError('allocation_pct must be between 0 and 100.')
    if initial_equity <= 0:
        raise ValueError('initial_equity must be positive.')
    if trades.empty:
        return {'trades':0,'win_rate':0.,'return_pct':0.,'max_drawdown_pct':0.,
                'profit_factor':None,'ending_equity':float(initial_equity)}
    if trades['date'].isna().any() or trades['net_return_pct'].isna().any():
        raise ValueError('Missing dates or trade returns.')
    t=trades.sort_values('date',kind='stable')
    per_trade=t['net_return_pct'].to_numpy(dtype=float)/100
    if not np.isfinite(per_trade).all() or np.any(per_trade <= -1):
        raise ValueError('Invalid return in trade log.')
    account_factors=1+(allocation_pct/100)*per_trade
    equity=np.r_[initial_equity,initial_equity*np.cumprod(account_factors)]
    pnl=np.diff(equity)
    gains=pnl[pnl>0].sum()
    losses=-pnl[pnl<0].sum()
    peaks=np.maximum.accumulate(equity)
    return {'trades':int(len(t)),
            'win_rate':float(100*np.mean(pnl>0)),
            'return_pct':float(100*(equity[-1]/initial_equity-1)),
            'max_drawdown_pct':float(100*np.min(equity/peaks-1)),
            'profit_factor':float(gains/losses) if losses>0 else None,
            'ending_equity':float(equity[-1])}


def evaluate_filters(study:dict, allocation_pct:float=10.0,
                     initial_capital:float=10000.0,
                     min_dev_trades:int=100) -> pd.DataFrame:
    """Evaluate each regime rule on each candidate's already-simulated trades.

    The filter predicates are observable BEFORE the trading session. The
    development ranking is independent of validation and diagnostic outcomes.
    """
    t=study.get('trade_log')
    if t is None:
        raise ValueError('Study must include trade_log (run_study include_trade_log=True).')
    rows=[]
    for name, sub in t.groupby('candidate',sort=True):
        for rule in FILTERS:
            chosen=sub.loc[filter_mask(sub,rule)]
            d={}
            for phase, prefix in [('Development','dev'),('Validation','val'),('Final holdout','historical_diagnostic')]:
                metrics=replay_returns(chosen.loc[chosen.period==phase],allocation_pct,initial_capital)
                for k,v in metrics.items():
                    if k!='ending_equity': d[f'{prefix}_{k}']=v
            rows.append({'candidate':name,'regime_filter':rule,'test_id':name+' | '+rule, **d})
    table=pd.DataFrame(rows)
    if table.empty:
        return table
    # No optimization using validation or previously viewed holdout results.
    # Penalize drawdown, too few trades and excess complexity.
    # Score units are percentage points on the full 2019-2023 development interval.
    table['qualified_dev']=(table['dev_trades']>=min_dev_trades) & (table['dev_max_drawdown_pct']>=-15.)
    table['dev_score']=table['dev_return_pct'] - 0.5*abs(table['dev_max_drawdown_pct'])
    table.loc[~table['qualified_dev'],'dev_score']=-1e6
    return table.sort_values(['dev_score','dev_return_pct'],ascending=False).reset_index(drop=True)


def run_summary(leaderboard:pd.DataFrame) -> dict:
    if leaderboard.empty: return {'candidates':0,'qualified_count':0,'selected':None}
    qualified=leaderboard.loc[leaderboard.qualified_dev]
    # Choosing from development only. A candidate can be a NO-GO even if it
    # looks best among alternatives; do not portray a winner as profitable.
    leader=qualified.iloc[0] if len(qualified) else leaderboard.iloc[0]
    return {'candidates':int(len(leaderboard)),
            'qualified_count':int(len(qualified)),
            'selected':str(leader.test_id),
            'development_return_pct':float(leader.dev_return_pct),
            'validation_return_pct':float(leader.val_return_pct),
            'historical_diagnostic_return_pct':float(leader.historical_diagnostic_return_pct),
            'validation_trades':int(leader.val_trades),
            'go_no_go':'PROMISING_RESEARCH_ONLY' if bool(leader.qualified_dev) and leader.dev_return_pct>0 and leader.val_return_pct>0 and leader.val_trades>=20 else 'NO_VALIDATED_EDGE'}