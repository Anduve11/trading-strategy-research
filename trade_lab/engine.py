"""Single-entry/day, next-minute-open, conservative-bar-fill simulator.

No brokerage connectivity or actual order submissions are included.
"""
from dataclasses import dataclass
from datetime import time
import pandas as pd
from .signals import calculate_signals
from .data import ET


@dataclass(frozen=True)
class Config:
    strategy: str = 'Momentum + VWAP'
    target_pct: float = 1.5
    stop_pct: float = 1.0
    fee_bps_each_side: float = 0.0
    slippage_bps_each_side: float = 5.0
    allocation_pct: float = 10.0
    initial_capital: float = 10000.0

    def __post_init__(self):
        if not (0 < self.target_pct <= 25 and 0 < self.stop_pct <= 25):
            raise ValueError('Targets and stops must be in (0,25]%.')
        if self.fee_bps_each_side < 0 or self.slippage_bps_each_side < 0:
            raise ValueError('Costs cannot be negative.')
        if not (0 < self.allocation_pct <= 100) or self.initial_capital <= 0:
            raise ValueError('Invalid allocation or initial capital.')


def simulate(bars: pd.DataFrame, config: Config):
    """Returns trade log and equity timeline.

    Bars timestamped at start of one-minute interval. Signal seen after bar t
    completes; next bar OPEN executes entry. A stop and target in same bar is
    scored as STOP. Long-only TQQQ/SQQQ. One trade per session, if any.
    """
    q = calculate_signals(bars, config.strategy)
    bysym = {sym: x.set_index('timestamp').sort_index() for sym, x in bars.groupby('symbol')}
    qqq_index = bysym['QQQ'].index
    equity = config.initial_capital
    trades, timeline = [], []
    for date, dayq in q.groupby('day', sort=True):
        day_start_equity = equity
        for _, r in dayq.loc[dayq['signal'] != 0].iterrows():
            ts = r['timestamp']
            i = qqq_index.searchsorted(ts)
            if i + 1 >= len(qqq_index):
                continue
            entry_ts = qqq_index[i+1]
            if entry_ts - ts != pd.Timedelta(minutes=1):
                continue
            local_entry = entry_ts.tz_convert(ET)
            if local_entry.date() != date or local_entry.time() > time(14,31):
                continue
            sym = 'TQQQ' if int(r['signal']) == 1 else 'SQQQ'
            prices = bysym[sym]
            if entry_ts not in prices.index:
                continue
            entry = float(prices.at[entry_ts, 'open'])*(1 + config.slippage_bps_each_side/10000)
            stop = entry*(1-config.stop_pct/100)
            target = entry*(1+config.target_pct/100)
            # Restrict data to today's eligible minute bars; no carrying overnight.
            eligible = prices.loc[(prices.index >= entry_ts)].copy()
            loc = eligible.index.tz_convert(ET)
            eligible = eligible.loc[(loc.date == date) & (loc.time <= time(15,54))]
            if eligible.empty:
                continue
            exit_ts = None
            exit_raw = None
            reason = None
            ambiguous = False
            for bt, b in eligible.iterrows():
                op, hi, lo = float(b['open']), float(b['high']), float(b['low'])
                if lo <= stop and hi >= target:
                    ambiguous = True
                    exit_raw = min(op, stop) if bt != entry_ts else stop
                    reason = 'stop (same-bar ambiguity)'
                elif lo <= stop:
                    exit_raw = min(op, stop) if bt != entry_ts else stop
                    reason = 'stop'
                elif hi >= target:
                    exit_raw = target  # no favorable gap improvement assumed
                    reason = 'target'
                if reason:
                    exit_ts = bt
                    break
            if exit_ts is None:
                exit_ts = eligible.index[-1]
                exit_raw = float(eligible.iloc[-1]['close'])
                reason = 'end-of-day'
            exit_fill = exit_raw*(1-config.slippage_bps_each_side/10000)
            f = config.fee_bps_each_side/10000
            net = (exit_fill*(1-f))/(entry*(1+f))-1
            gross = exit_raw/float(prices.at[entry_ts,'open'])-1
            pnl = equity*(config.allocation_pct/100)*net
            equity += pnl
            trades.append({'date': date, 'ticker': sym, 'signal_time': ts, 'entry_time': entry_ts,
                           'exit_time': exit_ts, 'entry': round(entry,5), 'exit': round(exit_fill,5),
                           'reason': reason, 'ambiguous_bar': ambiguous, 'gross_return_pct': 100*gross,
                           'net_return_pct': 100*net, 'pnl_dollars': pnl, 'equity_after': equity})
            break
        timeline.append({'date': date, 'equity': equity, 'daily_return_pct': (equity/day_start_equity-1)*100})
    return pd.DataFrame(trades), pd.DataFrame(timeline)


def summarize(trades: pd.DataFrame, equity: pd.DataFrame, initial_capital=10000.0) -> dict:
    if equity.empty:
        return {'trades':0,'win_rate':0.,'total_return':0.,'max_drawdown':0.,'avg_net_trade':0.,'profit_factor':None}
    vals = equity['equity']
    peak = pd.concat([pd.Series([initial_capital]), vals], ignore_index=True).cummax().iloc[1:]
    dd = vals.to_numpy()/peak.to_numpy()-1
    if trades.empty:
        return {'trades':0,'win_rate':0.,'total_return':0.,'max_drawdown':float(dd.min()*100),'avg_net_trade':0.,'profit_factor':None}
    wins = trades.loc[trades.pnl_dollars > 0,'pnl_dollars'].sum()
    losses = -trades.loc[trades.pnl_dollars < 0,'pnl_dollars'].sum()
    return {'trades':int(len(trades)),
            'win_rate':float(100*(trades.pnl_dollars > 0).mean()),
            'total_return':float((vals.iloc[-1]/initial_capital-1)*100),
            'max_drawdown':float(dd.min()*100),
            'avg_net_trade':float(trades.net_return_pct.mean()),
            'profit_factor':float(wins/losses) if losses>0 else None}


def split_by_session(bars: pd.DataFrame, train_fraction: float = .7):
    sessions = sorted(bars['timestamp'].dt.tz_convert(ET).dt.date.unique())
    if len(sessions) < 8:
        raise ValueError('Need at least 8 trading sessions to create a train/test split.')
    n = max(2, min(len(sessions)-2, int(len(sessions)*train_fraction)))
    is_train = bars['timestamp'].dt.tz_convert(ET).dt.date.isin(sessions[:n])
    return bars.loc[is_train].copy(), bars.loc[~is_train].copy(), sessions[n]