"""Time-separated research across bounded chunks of historical 1-minute data.

Designed for reproducible, research-only tests. No brokerage orders.
Configurations are predeclared before any final holdout result is inspected.
"""
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Callable
import pandas as pd

from .data import ET, audit_bar_coverage
from .engine import Config, simulate, summarize
from .signals import STRATEGIES, calculate_signals
from .regimes import classify_sessions, summarize_regime_trades

EXITS = ((1.0, 1.0), (1.5, 1.0), (2.0, 1.5), (3.0, 2.0))


@dataclass(frozen=True)
class Candidate:
    strategy: str
    target_pct: float
    stop_pct: float

    def label(self) -> str:
        return f'{self.strategy} | target {self.target_pct:g}% | stop {self.stop_pct:g}%'


def default_candidates() -> list[Candidate]:
    return [Candidate(s, tp, stop) for s in STRATEGIES for tp, stop in EXITS]


def year_partitions(start_year: int, end_year: int) -> dict[int, str]:
    """First ~60% development; ~20% validation; latest years untouched holdout."""
    n = end_year - start_year + 1
    if n < 3:
        raise ValueError('Multi-year analysis requires at least three calendar years.')
    n_development = max(1, int(n * .65))
    n_validation = max(1, int(n * .20))
    if n_development + n_validation >= n:
        n_development = n - n_validation - 1
    return {y: ('Development' if i < n_development else
                'Validation' if i < n_development+n_validation else 'Final holdout')
            for i, y in enumerate(range(start_year, end_year+1))}


def calendar_quarters(start: date, end: date):
    """Nonoverlapping boundaries; requests end-date inclusive."""
    curr = start
    while curr <= end:
        quarter = ((curr.month-1)//3)+1
        final_month = quarter*3
        if final_month == 12:
            next_quarter = date(curr.year+1, 1, 1)
        else:
            next_quarter = date(curr.year, final_month+1, 1)
        stop = min(end, next_quarter-timedelta(days=1))
        yield curr, stop
        curr = stop+timedelta(days=1)


def run_study(fetcher: Callable[[str, str], pd.DataFrame],
              start: date, end: date, base_config: Config,
              candidates: list[Candidate] | None = None,
              progress: Callable[[int, int, str], None] | None = None) -> dict:
    """Chunked multi-year retrospective study. fetcher accepts ISO start/end dates.

    Chunk boundaries are calendar-quarter aligned. Every strategy's account
    balance carries forward, and each period is evaluated separately.
    The function *calculates* all candidates, but the app only discloses the
    final holdout for the candidate fixed using development data.
    """
    if end <= start:
        raise ValueError('Study end must be after start.')
    partitions = year_partitions(start.year, end.year)
    candidates = candidates if candidates is not None else default_candidates()
    if not candidates:
        raise ValueError('Choose at least one strategy configuration.')
    if len(set(candidates)) != len(candidates):
        raise ValueError('Duplicated candidate configuration.')

    windows = list(calendar_quarters(start, end))
    balance = {c: base_config.initial_capital for c in candidates}
    period_start_balance = {}
    trade_parts = {(c, phase): [] for c in candidates for phase in ('Development', 'Validation', 'Final holdout')}
    equity_parts = {(c, phase): [] for c in candidates for phase in ('Development', 'Validation', 'Final holdout')}
    quality = []
    regime_trade_parts = []
    trailing_qqq_closes = []

    for index, (begin, finish) in enumerate(windows, start=1):
        phase = partitions[begin.year]
        if progress:
            progress(index-1, len(windows), f'Fetching {begin} to {finish} ({phase})')
        bars = fetcher(begin.isoformat(), finish.isoformat())
        if bars is None or bars.empty:
            raise ValueError(f'No market data returned for {begin} to {finish}. The study cannot silently skip periods.')
        report = audit_bar_coverage(bars)
        report.update({'from': begin.isoformat(), 'through': finish.isoformat(), 'period': phase})
        quality.append(report)
        if report['aligned_minutes_pct'] < 99.0:
            raise ValueError(f'Missing synchronized ETF minute bars during {begin}–{finish} ({report["aligned_minutes_pct"]:.1f}% aligned). Correct the dataset before trusting backtests.')
        # Regimes are fixed before trading: only previous sessions' completed
        # daily QQQ closes enter this classification (including at chunk edges).
        regimes, trailing_qqq_closes = classify_sessions(bars, trailing_qqq_closes)
        # Compute the four QQQ trading signals ONCE per chunk, rather than for each exit rule.
        precomputed = {s: calculate_signals(bars, s) for s in set(c.strategy for c in candidates)}
        precomputed_prices = {sym: x.set_index('timestamp').sort_index() for sym, x in bars.groupby('symbol')}
        for candidate in candidates:
            key = candidate, phase
            if key not in period_start_balance:
                period_start_balance[key] = balance[candidate]
            config = replace(base_config, strategy=candidate.strategy,
                             target_pct=candidate.target_pct, stop_pct=candidate.stop_pct,
                             initial_capital=balance[candidate])
            trades, equity = simulate(bars, config, precomputed_signals=precomputed[candidate.strategy],
                                      precomputed_prices=precomputed_prices)
            if not equity.empty:
                balance[candidate] = float(equity.iloc[-1]['equity'])
                equity_parts[key].append(equity)
            if not trades.empty:
                trade_parts[key].append(trades)
                annotated = trades[['date', 'ticker', 'pnl_dollars', 'net_return_pct']].merge(
                    regimes, on='date', how='left', validate='many_to_one')
                annotated['candidate'] = candidate.label()
                annotated['period'] = phase
                regime_trade_parts.append(annotated)
        if progress:
            progress(index, len(windows), f'Processed {begin} through {finish}')

    rows = []
    annual_rows = []
    daily_equity_parts = []
    for candidate in candidates:
        for phase in ('Development', 'Validation', 'Final holdout'):
            key = candidate, phase
            trades = pd.concat(trade_parts[key], ignore_index=True) if trade_parts[key] else pd.DataFrame()
            timeline = pd.concat(equity_parts[key], ignore_index=True) if equity_parts[key] else pd.DataFrame()
            initial = period_start_balance.get(key, base_config.initial_capital)
            summary = summarize(trades, timeline, initial)
            if not timeline.empty:
                annual_equity = timeline.copy()
                annual_equity['year'] = pd.to_datetime(annual_equity['date']).dt.year
                for year, year_equity in annual_equity.groupby('year', sort=True):
                    first = year_equity.iloc[0]
                    year_start = float(first['equity']) / (1 + float(first['daily_return_pct']) / 100)
                    year_trades = trades.loc[pd.to_datetime(trades['date']).dt.year == year] if not trades.empty else pd.DataFrame()
                    year_summary = summarize(year_trades, year_equity, year_start)
                    annual_rows.append({
                        'candidate': candidate.label(), 'year': int(year), 'period': phase,
                        'starting_equity': round(year_start, 2),
                        'ending_equity': round(float(year_equity.iloc[-1]['equity']), 2),
                        'net_pnl': round(float(year_equity.iloc[-1]['equity']) - year_start, 2),
                        **year_summary,
                    })
                slim = timeline[['date', 'equity']].copy()
                slim['candidate'] = candidate.label()
                slim['period'] = phase
                daily_equity_parts.append(slim)
            rows.append({
                'candidate': candidate.label(), 'strategy': candidate.strategy,
                'take_profit': candidate.target_pct, 'stop_loss': candidate.stop_pct,
                'period': phase, 'starting_equity': round(initial, 2),
                'ending_equity': round(initial*(1+summary['total_return']/100), 2),
                'net_pnl': round(initial*summary['total_return']/100, 2),
                **summary,
            })
    return {
        'results': pd.DataFrame(rows),
        'annual_results': pd.DataFrame(annual_rows),
        'equity_curve': pd.concat(daily_equity_parts, ignore_index=True) if daily_equity_parts else pd.DataFrame(),
        'regime_results': summarize_regime_trades(pd.concat(regime_trade_parts, ignore_index=True) if regime_trade_parts else pd.DataFrame()),
        'coverage': pd.DataFrame(quality),
        'trade_log': pd.concat(regime_trade_parts, ignore_index=True) if regime_trade_parts else pd.DataFrame(columns=['date','net_return_pct','candidate','period','regime']),
        'partitions': partitions,
        'initial_capital': base_config.initial_capital,
        'candidate_count': len(candidates),
        'start': start.isoformat(), 'end': end.isoformat(),
    }


def select_development_winner(study: dict, min_trades: int = 100, min_drawdown: float = -20.0) -> dict:
    """Winner chosen EXCLUSIVELY with development data; never by holdout returns."""
    development = study['results'].loc[study['results']['period'].eq('Development')].copy()
    viable = development[(development['trades'] >= min_trades) & (development['max_drawdown'] >= min_drawdown)]
    qualified = not viable.empty
    if not qualified:
        viable = development
    winner = viable.sort_values(['total_return','max_drawdown'], ascending=[False, False]).iloc[0]
    label = winner['candidate']
    selected = study['results'].loc[study['results']['candidate'].eq(label)].copy()
    selected['period'] = pd.Categorical(selected['period'], ['Development','Validation','Final holdout'], ordered=True)
    selected = selected.sort_values('period')
    return {'winner': label, 'qualified': qualified, 'selected': selected, 'development_table': development.sort_values('total_return',ascending=False)}