"""Spot-crypto data loading and long/cash backtests for Market Edge.

This module is research-only. It uses Coinbase Exchange public candles, does
not connect to an account, and never creates or submits brokerage orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import math
import time as time_module
from typing import Callable, Iterable

import numpy as np
import pandas as pd
import requests


COINBASE_CANDLES_URL = "https://api.exchange.coinbase.com/products/{product}/candles"
PRODUCTS = ("BTC-USD", "ETH-USD")
GRANULARITIES = {3600: "1 hour", 21600: "6 hours", 86400: "1 day"}
MAX_CANDLES_PER_REQUEST = 300
DEVELOPMENT_START = date(2017, 1, 1)
DEVELOPMENT_END = date(2020, 12, 31)
VALIDATION_START = date(2021, 1, 1)
VALIDATION_END = date(2023, 12, 31)
# Indicators are warmed up on prior data; reported research starts in 2017.
WARMUP_START = date(2016, 1, 1)
# Keep the later period closed during iteration. It is intentionally not loaded
# by the baseline CLI or the first Streamlit page.
LOCKED_HOLDOUT_START = date(2024, 1, 1)


@dataclass(frozen=True)
class Candidate:
    name: str
    kind: str
    parameters: tuple[int, ...]


def default_candidates() -> list[Candidate]:
    """Return fixed SMA, Donchian, and time-series momentum candidates."""
    return [
        Candidate("SMA trend 20d", "sma", (20,)),
        Candidate("SMA trend 50d", "sma", (50,)),
        Candidate("SMA trend 100d", "sma", (100,)),
        Candidate("Donchian 20d/10d", "donchian", (20, 10)),
        Candidate("Donchian 55d/20d", "donchian", (55, 20)),
        Candidate("TS momentum 20d", "tsmom", (20,)),
        Candidate("TS momentum 60d", "tsmom", (60,)),
        Candidate("TS momentum 120d", "tsmom", (120,)),
        Candidate("TS momentum 240d", "tsmom", (240,)),
    ]


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise ValueError("Dates must use YYYY-MM-DD format.") from exc


def _utc_midnight(day: date) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, time.min, tzinfo=timezone.utc))


def _api_timestamp(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_crypto_bars(raw: pd.DataFrame, product: str | None = None) -> pd.DataFrame:
    """Validate and normalize OHLCV bars without imposing a US stock calendar."""
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raise ValueError("No crypto candles were supplied.")
    df = raw.copy()
    df.columns = [str(column).strip().lower() for column in df.columns]
    required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required crypto candle columns: {sorted(missing)}")
    df = df[["timestamp", "symbol", "open", "high", "low", "close", "volume"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    if df["timestamp"].isna().any():
        raise ValueError("Invalid timestamp; crypto timestamps must be parseable as UTC.")
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    if product is not None and set(df["symbol"]) != {product.upper()}:
        raise ValueError(f"Expected only {product.upper()} bars.")
    if not set(df["symbol"]).issubset(PRODUCTS):
        raise ValueError(f"Only these Coinbase USD products are enabled: {', '.join(PRODUCTS)}.")
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    if df[["open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError("Invalid price or volume value in crypto candles.")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df["volume"] < 0).any():
        raise ValueError("Prices must be positive and volume nonnegative.")
    if (df["high"] < df[["open", "low", "close"]].max(axis=1)).any():
        raise ValueError("OHLC high is inconsistent with open, low, and close.")
    if (df["low"] > df[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("OHLC low is inconsistent with open, high, and close.")
    if df.duplicated(["timestamp", "symbol"]).any():
        raise ValueError("Duplicate timestamp/product candles found.")
    return df.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def fetch_coinbase_candles(
    product: str,
    start: date | datetime | str,
    end: date | datetime | str,
    granularity_seconds: int = 21600,
    *,
    session: requests.Session | None = None,
    timeout_seconds: int = 25,
    max_retries: int = 4,
    request_pause_seconds: float = 0.12,
    progress: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Fetch inclusive UTC dates from Coinbase's public, paginated candle API.

    Coinbase returns rows as [time, low, high, open, close, volume], with a
    300-candle request cap. The returned history can contain missing intervals;
    callers should inspect ``audit_crypto_bars`` before interpreting results.
    """
    product = str(product).upper().strip()
    if product not in PRODUCTS:
        raise ValueError(f"Product must be one of: {', '.join(PRODUCTS)}.")
    if granularity_seconds not in GRANULARITIES:
        raise ValueError("Granularity must be 1 hour, 6 hours, or 1 day.")
    if max_retries < 0 or request_pause_seconds < 0:
        raise ValueError("Retry count and request pause cannot be negative.")

    start_day, end_day = _as_date(start), _as_date(end)
    if end_day < start_day:
        raise ValueError("End date precedes start date.")
    start_utc = _utc_midnight(start_day)
    end_exclusive = _utc_midnight(end_day + timedelta(days=1))
    step = pd.Timedelta(seconds=granularity_seconds * MAX_CANDLES_PER_REQUEST)
    total_calls = math.ceil((end_exclusive - start_utc) / step)
    client = session or requests.Session()
    client.headers.update({
        "Accept": "application/json",
        "User-Agent": "MarketEdgeCryptoResearch/0.1",
    })
    url = COINBASE_CANDLES_URL.format(product=product)
    rows: list[list[object]] = []
    cursor = start_utc
    call_number = 0

    while cursor < end_exclusive:
        chunk_end = min(end_exclusive, cursor + step)
        query_end = chunk_end - pd.Timedelta(seconds=1)
        params = {
            "granularity": granularity_seconds,
            "start": _api_timestamp(cursor),
            "end": _api_timestamp(query_end),
        }
        response = None
        for attempt in range(max_retries + 1):
            response = client.get(url, params=params, timeout=timeout_seconds)
            status = int(getattr(response, "status_code", 200))
            if status == 429 or status >= 500:
                if attempt == max_retries:
                    response.raise_for_status()
                retry_after = getattr(response, "headers", {}).get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 0.5 * (2 ** attempt)
                except (TypeError, ValueError):
                    delay = 0.5 * (2 ** attempt)
                time_module.sleep(max(delay, request_pause_seconds))
                continue
            response.raise_for_status()
            break
        if response is None:
            raise RuntimeError("Coinbase candle request did not return a response.")
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Coinbase returned an unexpected candle response.")
        for candle in payload:
            if not isinstance(candle, (list, tuple)) or len(candle) < 6:
                raise ValueError("Coinbase returned a malformed candle row.")
            rows.append(list(candle[:6]))
        call_number += 1
        if progress:
            progress(call_number, total_calls)
        cursor = chunk_end
        if cursor < end_exclusive and request_pause_seconds:
            time_module.sleep(request_pause_seconds)

    if not rows:
        raise ValueError(f"Coinbase returned no {product} candles for the requested dates.")
    frame = pd.DataFrame(rows, columns=["epoch", "low", "high", "open", "close", "volume"])
    frame["timestamp"] = pd.to_datetime(frame.pop("epoch"), unit="s", utc=True, errors="coerce")
    frame["symbol"] = product
    frame = frame[["timestamp", "symbol", "open", "high", "low", "close", "volume"]]
    frame = frame.loc[(frame["timestamp"] >= start_utc) & (frame["timestamp"] < end_exclusive)]
    # Adjacent API windows can overlap at the boundary. Keep one observation per
    # timestamp, then let the validator reject all other duplicate cases.
    frame = frame.drop_duplicates(["timestamp", "symbol"], keep="last")
    return validate_crypto_bars(frame, product=product)


def audit_crypto_bars(
    bars: pd.DataFrame,
    granularity_seconds: int,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
) -> pd.DataFrame:
    """Report observed candles against the requested 24/7 UTC time grid."""
    bars = validate_crypto_bars(bars)
    if granularity_seconds not in GRANULARITIES:
        raise ValueError("Unsupported crypto candle granularity.")
    if start is None:
        start_utc = bars["timestamp"].min().floor(f"{granularity_seconds}s")
    else:
        start_utc = _utc_midnight(_as_date(start))
    if end is None:
        end_exclusive = bars["timestamp"].max().floor(f"{granularity_seconds}s") + pd.Timedelta(seconds=granularity_seconds)
    else:
        end_exclusive = _utc_midnight(_as_date(end) + timedelta(days=1))
    expected_index = pd.date_range(
        start=start_utc, end=end_exclusive, freq=f"{granularity_seconds}s", inclusive="left"
    )
    expected = len(expected_index)
    if expected <= 0:
        raise ValueError("Requested audit range is empty.")
    rows = []
    for symbol, part in bars.groupby("symbol", sort=True):
        within = part.loc[(part["timestamp"] >= start_utc) & (part["timestamp"] < end_exclusive)]
        observed = pd.DatetimeIndex(within["timestamp"].drop_duplicates())
        on_grid = expected_index.isin(observed)
        actual = int(on_grid.sum())
        missing_mask = ~on_grid
        max_gap = current_gap = 0
        for missing in missing_mask:
            current_gap = current_gap + 1 if missing else 0
            max_gap = max(max_gap, current_gap)
        rows.append({
            "symbol": symbol,
            "start_utc": start_utc,
            "end_exclusive_utc": end_exclusive,
            "expected_bars": expected,
            "observed_bars": actual,
            "missing_bars": max(0, expected - actual),
            "coverage_pct": min(100.0, 100.0 * actual / expected),
            "max_missing_streak_bars": max_gap,
            "unexpected_bars": int((~observed.isin(expected_index)).sum()),
            "first_observed_utc": within["timestamp"].min() if not within.empty else pd.NaT,
            "last_observed_utc": within["timestamp"].max() if not within.empty else pd.NaT,
        })
    return pd.DataFrame(rows)


def _bars_per_day(granularity_seconds: int) -> int:
    if granularity_seconds not in GRANULARITIES:
        raise ValueError("Unsupported crypto candle granularity.")
    return 86400 // granularity_seconds


def position_signal(bars: pd.DataFrame, candidate: Candidate, granularity_seconds: int) -> pd.Series:
    """Return 0/1 close-time signals; execution is deferred to next bar open."""
    bars = validate_crypto_bars(bars)
    if bars["symbol"].nunique() != 1:
        raise ValueError("Calculate one product's signal at a time.")
    if not candidate.parameters or any(int(x) <= 0 for x in candidate.parameters):
        raise ValueError("Candidate lookbacks must be positive whole days.")
    bars_per_day = _bars_per_day(granularity_seconds)
    close = bars["close"].astype(float)
    if candidate.kind == "tsmom" and len(candidate.parameters) == 1:
        window = candidate.parameters[0] * bars_per_day
        prior_close = close.shift(window)
        return (close > prior_close).astype(float).rename("signal")
    if candidate.kind == "sma" and len(candidate.parameters) == 1:
        window = candidate.parameters[0] * bars_per_day
        average = close.rolling(window=window, min_periods=window).mean()
        return (close > average).astype(float).rename("signal")
    if candidate.kind == "donchian" and len(candidate.parameters) == 2:
        entry_window, exit_window = (days * bars_per_day for days in candidate.parameters)
        prior_high = bars["high"].shift(1).rolling(entry_window, min_periods=entry_window).max()
        prior_low = bars["low"].shift(1).rolling(exit_window, min_periods=exit_window).min()
        desired = np.zeros(len(bars), dtype=float)
        in_position = False
        for i, price in enumerate(close.to_numpy(dtype=float)):
            upper, lower = prior_high.iloc[i], prior_low.iloc[i]
            if not in_position and pd.notna(upper) and price > float(upper):
                in_position = True
            elif in_position and pd.notna(lower) and price < float(lower):
                in_position = False
            desired[i] = 1.0 if in_position else 0.0
        return pd.Series(desired, index=bars.index, name="signal")
    raise ValueError(f"Unsupported crypto candidate: {candidate.name}.")


def _trade_return(entry: float, exit_price: float, cost_fraction: float) -> float:
    return ((exit_price * (1.0 - cost_fraction)) /
            (entry * (1.0 + cost_fraction)) - 1.0)


def _summary_from_equity(
    equity: pd.Series,
    initial_equity: float,
    granularity_seconds: int,
    exposure: pd.Series,
    trade_count: int,
    win_rate_pct: float,
    buy_hold_equity: pd.Series,
) -> dict[str, float | int]:
    if equity.empty:
        return {
            "bars": 0, "return_pct": 0.0, "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0, "annualized_volatility_pct": 0.0,
            "sharpe": 0.0, "exposure_pct": 0.0, "trades": 0,
            "win_rate_pct": 0.0, "buy_hold_return_pct": 0.0, "cash_return_pct": 0.0,
        }
    values = equity.to_numpy(dtype=float)
    peak = np.maximum.accumulate(np.r_[initial_equity, values])[1:]
    drawdown = values / peak - 1.0
    total_return = values[-1] / initial_equity - 1.0
    periods_per_year = 365.25 * 86400 / granularity_seconds
    returns = equity.pct_change().dropna().to_numpy(dtype=float)
    volatility = float(np.std(returns, ddof=1) * math.sqrt(periods_per_year)) if len(returns) > 1 else 0.0
    mean_return = float(np.mean(returns)) if len(returns) else 0.0
    standard_deviation = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    sharpe = mean_return / standard_deviation * math.sqrt(periods_per_year) if standard_deviation > 0 else 0.0
    return {
        "bars": int(len(values)),
        "return_pct": float(total_return * 100),
        "cagr_pct": float(((values[-1] / initial_equity) ** (1 / max(len(values) / periods_per_year, 1e-9)) - 1) * 100),
        "max_drawdown_pct": float(np.min(drawdown) * 100) if len(drawdown) else 0.0,
        "annualized_volatility_pct": volatility * 100,
        "sharpe": float(sharpe),
        "exposure_pct": float((exposure > 0).mean() * 100) if len(exposure) else 0.0,
        "trades": int(trade_count),
        "win_rate_pct": float(win_rate_pct),
        "buy_hold_return_pct": float((buy_hold_equity.iloc[-1] / initial_equity - 1) * 100),
        "cash_return_pct": 0.0,
    }


def backtest_long_cash(
    bars: pd.DataFrame,
    candidate: Candidate,
    granularity_seconds: int = 21600,
    *,
    cost_bps_each_side: float = 25.0,
    allocation_pct: float = 100.0,
    initial_capital: float = 10000.0,
    trade_start: date | str | None = None,
) -> dict[str, object]:
    """Simulate unlevered long/cash exposure, entering or exiting next bar open.

    ``cost_bps_each_side`` is a combined fee + spread/slippage scenario for one
    buy or sell. It is charged on entries and exits; no funding, borrowing,
    shorting, staking yield, or stop-order fills are assumed.
    """
    bars = validate_crypto_bars(bars)
    if bars["symbol"].nunique() != 1:
        raise ValueError("Backtest one product at a time.")
    if granularity_seconds not in GRANULARITIES:
        raise ValueError("Unsupported crypto candle granularity.")
    if not 0 <= cost_bps_each_side < 10000:
        raise ValueError("All-in cost must be between 0 and 10,000 bps per side.")
    if not 0 < allocation_pct <= 100:
        raise ValueError("Spot allocation must be in (0, 100]%; leverage is not modeled.")
    if initial_capital <= 0:
        raise ValueError("Initial capital must be positive.")
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    trade_start_utc = _utc_midnight(_as_date(trade_start)) if trade_start is not None else None
    signals = position_signal(bars, candidate, granularity_seconds).to_numpy(dtype=float)
    allocation = allocation_pct / 100.0
    cost = cost_bps_each_side / 10000.0
    cash = float(initial_capital)
    units = 0.0
    benchmark_cash = float(initial_capital)
    benchmark_units = 0.0
    entry_price: float | None = None
    entry_time: pd.Timestamp | None = None
    trade_rows: list[dict[str, object]] = []
    curve_rows: list[dict[str, object]] = []

    for i, row in bars.iterrows():
        timestamp = row["timestamp"]
        opening = float(row["open"])
        closing = float(row["close"])
        if i == 0:
            # The strategy has no prior completed candle, so it starts in cash.
            benchmark_notional = initial_capital * allocation / (1.0 + cost)
            benchmark_cash -= benchmark_notional * (1.0 + cost)
            benchmark_units = benchmark_notional / opening
        else:
            desired_long = bool(signals[i - 1])
            if trade_start_utc is not None and timestamp < trade_start_utc:
                desired_long = False
            if desired_long and units <= 1e-12:
                equity_at_open = cash + units * opening
                budget = equity_at_open * allocation
                notional = budget / (1.0 + cost)
                cash -= notional * (1.0 + cost)
                units = notional / opening
                entry_price = opening
                entry_time = timestamp
            elif not desired_long and units > 1e-12:
                exit_price = opening
                cash += units * exit_price * (1.0 - cost)
                net_return = _trade_return(float(entry_price), exit_price, cost)
                trade_rows.append({
                    "symbol": row["symbol"], "entry_time": entry_time,
                    "exit_time": timestamp, "entry_price": entry_price,
                    "exit_price": exit_price, "net_return_pct": net_return * 100,
                    "days_held": (timestamp - entry_time).total_seconds() / 86400,
                    "status": "closed",
                })
                units = 0.0
                entry_price = None
                entry_time = None

        equity = cash + units * closing
        benchmark_equity = benchmark_cash + benchmark_units * closing
        curve_rows.append({
            "timestamp": timestamp, "equity": equity,
            "buy_hold_equity": benchmark_equity,
            "position_pct": (units * closing / equity * 100) if equity > 0 else 0.0,
            "signal_at_close": signals[i],
        })

    if entry_price is not None and entry_time is not None:
        final_time = bars.iloc[-1]["timestamp"]
        final_close = float(bars.iloc[-1]["close"])
        cash += units * final_close * (1.0 - cost)
        units = 0.0
        trade_rows.append({
            "symbol": bars.iloc[-1]["symbol"], "entry_time": entry_time,
            "exit_time": final_time, "entry_price": entry_price,
            "exit_price": final_close,
            "net_return_pct": _trade_return(entry_price, final_close, cost) * 100,
            "days_held": (final_time - entry_time).total_seconds() / 86400,
            "status": "liquidated_at_end",
        })
        curve_rows[-1]["equity"] = cash

    # Liquidate the benchmark at the final close so both return series include a sell cost.
    final_close = float(bars.iloc[-1]["close"])
    benchmark_cash += benchmark_units * final_close * (1.0 - cost)
    benchmark_units = 0.0
    curve_rows[-1]["buy_hold_equity"] = benchmark_cash

    curve = pd.DataFrame(curve_rows)
    trades = pd.DataFrame(trade_rows, columns=[
        "symbol", "entry_time", "exit_time", "entry_price", "exit_price",
        "net_return_pct", "days_held", "status",
    ])
    closed = trades.loc[trades["status"].isin(["closed", "liquidated_at_end"])] if not trades.empty else trades
    wins = int((closed["net_return_pct"] > 0).sum()) if not closed.empty else 0
    win_rate = 100.0 * wins / len(closed) if len(closed) else 0.0
    summary = _summary_from_equity(
        curve["equity"], initial_capital, granularity_seconds,
        curve["position_pct"], len(closed), win_rate,
        curve["buy_hold_equity"],
    )
    return {"equity_curve": curve, "trades": trades, "summary": summary}


def summarize_period(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    start: date | str,
    end: date | str,
    *,
    initial_capital: float,
    granularity_seconds: int,
) -> dict[str, float | int | str]:
    """Summarize a chronological window using prior close as its starting mark."""
    start_day, end_day = _as_date(start), _as_date(end)
    if end_day < start_day:
        raise ValueError("Period end precedes start.")
    start_utc = _utc_midnight(start_day)
    end_exclusive = _utc_midnight(end_day + timedelta(days=1))
    curve = equity_curve.sort_values("timestamp")
    in_window = curve.loc[(curve["timestamp"] >= start_utc) & (curve["timestamp"] < end_exclusive)]
    before = curve.loc[curve["timestamp"] < start_utc]
    if in_window.empty:
        raise ValueError(f"No backtest bars in {start_day} through {end_day}.")
    start_equity = float(before.iloc[-1]["equity"]) if not before.empty else float(initial_capital)
    start_benchmark = float(before.iloc[-1]["buy_hold_equity"]) if not before.empty else float(initial_capital)
    if start_equity <= 0 or start_benchmark <= 0:
        raise ValueError("Starting equity for the selected period must be positive.")
    equity_values = np.r_[start_equity, in_window["equity"].to_numpy(dtype=float)]
    peaks = np.maximum.accumulate(equity_values)
    drawdown = equity_values / peaks - 1.0
    period_returns = pd.Series(equity_values).pct_change().dropna().to_numpy(dtype=float)
    periods_per_year = 365.25 * 86400 / granularity_seconds
    sd = float(np.std(period_returns, ddof=1)) if len(period_returns) > 1 else 0.0
    sharpe = (float(np.mean(period_returns)) / sd * math.sqrt(periods_per_year)) if sd > 0 else 0.0
    years = max(len(in_window) / periods_per_year, 1e-9)
    final_equity = float(in_window.iloc[-1]["equity"])
    final_benchmark = float(in_window.iloc[-1]["buy_hold_equity"])
    if not trades.empty:
        entry_times = pd.to_datetime(trades["entry_time"], utc=True)
        exit_times = pd.to_datetime(trades["exit_time"], utc=True)
        window_trades = trades.loc[(entry_times >= start_utc) & (entry_times < end_exclusive)]
        closed = trades.loc[
            (exit_times >= start_utc) & (exit_times < end_exclusive) &
            trades["status"].isin(["closed", "liquidated_at_end"])
        ]
    else:
        window_trades = trades
        closed = trades
    return {
        "period": f"{start_day} to {end_day}",
        "bars": int(len(in_window)),
        "return_pct": 100.0 * (final_equity / start_equity - 1.0),
        "cagr_pct": 100.0 * ((final_equity / start_equity) ** (1.0 / years) - 1.0),
        "buy_hold_return_pct": 100.0 * (final_benchmark / start_benchmark - 1.0),
        "max_drawdown_pct": 100.0 * float(np.min(drawdown)),
        "sharpe": sharpe,
        "exposure_pct": float((in_window["position_pct"] > 0).mean() * 100),
        "trades": int(len(window_trades)),
        "closed_trades": int(len(closed)),
        "win_rate_pct": 100.0 * float((closed["net_return_pct"] > 0).mean()) if not closed.empty else 0.0,
        "cash_return_pct": 0.0,
    }


def run_candidate_suite(
    bars: pd.DataFrame,
    granularity_seconds: int = 21600,
    *,
    cost_bps_each_side: float = 25.0,
    allocation_pct: float = 100.0,
    initial_capital: float = 10000.0,
    candidates: Iterable[Candidate] | None = None,
) -> pd.DataFrame:
    """Run the fixed candidate set and report development/validation separately."""
    bars = validate_crypto_bars(bars)
    candidates = list(candidates) if candidates is not None else default_candidates()
    rows: list[dict[str, object]] = []
    phases = (
        ("Development", DEVELOPMENT_START, DEVELOPMENT_END),
        ("Validation", VALIDATION_START, VALIDATION_END),
    )
    for symbol, product_bars in bars.groupby("symbol", sort=True):
        product_bars = product_bars.sort_values("timestamp").reset_index(drop=True)
        for candidate in candidates:
            result = backtest_long_cash(
                product_bars, candidate, granularity_seconds,
                cost_bps_each_side=cost_bps_each_side,
                allocation_pct=allocation_pct,
                initial_capital=initial_capital,
                trade_start=DEVELOPMENT_START,
            )
            for phase, phase_start, phase_end in phases:
                summary = summarize_period(
                    result["equity_curve"], result["trades"], phase_start, phase_end,
                    initial_capital=initial_capital,
                    granularity_seconds=granularity_seconds,
                )
                rows.append({
                    "symbol": symbol, "candidate": candidate.name,
                    "phase": phase, "cost_bps_each_side": cost_bps_each_side,
                    "allocation_pct": allocation_pct, **summary,
                })
    return pd.DataFrame(rows)
