import pandas as pd
import pytest

from trade_lab.crypto_research import (
    Candidate,
    audit_crypto_bars,
    backtest_long_cash,
    fetch_coinbase_candles,
    position_signal,
    validate_crypto_bars,
)


def make_bars(closes, symbol="BTC-USD", start="2020-01-01", granularity="1D", opens=None, highs=None):
    timestamps = pd.date_range(start=start, periods=len(closes), freq=granularity, tz="UTC")
    opens = list(opens) if opens is not None else list(closes)
    highs = list(highs) if highs is not None else [max(o, c) * 1.01 for o, c in zip(opens, closes)]
    lows = [min(o, c) * 0.99 for o, c in zip(opens, closes)]
    return pd.DataFrame({
        "timestamp": timestamps,
        "symbol": symbol,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [10.0] * len(closes),
    })


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return self.responses.pop(0)


def test_coinbase_rows_are_paginated_sorted_and_mapped_correctly():
    jan1 = int(pd.Timestamp("2017-01-01", tz="UTC").timestamp())
    nov1 = int(pd.Timestamp("2017-11-01", tz="UTC").timestamp())
    session = FakeSession([
        # Coinbase response order is not relied on; rows use low/high/open/close.
        FakeResponse([[jan1 + 86400, 9, 12, 10, 11, 4], [jan1, 8, 11, 9, 10, 3]]),
        FakeResponse([[nov1, 11, 14, 12, 13, 5]]),
    ])

    bars = fetch_coinbase_candles(
        "BTC-USD", "2017-01-01", "2017-11-01", 86400,
        session=session, request_pause_seconds=0, max_retries=0,
    )

    assert len(session.calls) == 2
    assert bars.timestamp.is_monotonic_increasing
    assert bars.iloc[0].open == 9
    assert bars.iloc[0].high == 11
    assert bars.iloc[0].low == 8
    assert bars.iloc[0].close == 10
    assert set(bars.symbol) == {"BTC-USD"}


def test_crypto_validation_rejects_duplicate_and_inconsistent_candles():
    bars = make_bars([100, 101])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_crypto_bars(pd.concat([bars, bars.iloc[[0]]], ignore_index=True))

    broken = bars.copy()
    broken.loc[0, "high"] = 1
    with pytest.raises(ValueError, match="high"):
        validate_crypto_bars(broken)


def test_sma_signal_is_filled_at_the_next_bar_open():
    bars = make_bars([10, 10, 12, 12, 13], opens=[10, 10, 10, 10, 10])
    candidate = Candidate("SMA trend 2d", "sma", (2,))
    signals = position_signal(bars, candidate, 86400)
    result = backtest_long_cash(
        bars, candidate, 86400, cost_bps_each_side=0,
        allocation_pct=100, initial_capital=10000,
    )

    assert signals.iloc[2] == 1
    assert result["equity_curve"].position_pct.iloc[2] == 0
    assert result["equity_curve"].position_pct.iloc[3] == 100
    assert result["trades"].iloc[0].entry_time == bars.timestamp.iloc[3]


def test_time_series_momentum_uses_trailing_return_and_next_bar_fill():
    bars = make_bars([100, 99, 101, 100, 102, 102], opens=[100] * 6)
    candidate = Candidate("TS momentum 2d", "tsmom", (2,))
    signals = position_signal(bars, candidate, 86400)
    result = backtest_long_cash(
        bars, candidate, 86400, cost_bps_each_side=0,
        allocation_pct=100, initial_capital=10000,
    )

    assert signals.iloc[1] == 0
    assert signals.iloc[2] == 1
    assert result["equity_curve"].position_pct.iloc[2] == 0
    assert result["trades"].iloc[0].entry_time == bars.timestamp.iloc[3]


def test_bollinger_reversion_enters_below_lower_band_and_exits_at_mean():
    bars = make_bars([100] * 10 + [50, 120, 100], opens=[100] * 13)
    candidate = Candidate("Bollinger reversion 10d/2sd", "bollinger", (10, 2))
    signals = position_signal(bars, candidate, 86400)
    result = backtest_long_cash(
        bars, candidate, 86400, cost_bps_each_side=0,
        allocation_pct=100, initial_capital=10000,
    )

    assert signals.iloc[9] == 0
    assert signals.iloc[10] == 1
    assert signals.iloc[11] == 0
    assert result["trades"].iloc[0].entry_time == bars.timestamp.iloc[11]
    assert result["trades"].iloc[0].exit_time == bars.timestamp.iloc[12]


def test_donchian_entry_uses_prior_bars_not_current_high():
    bars = make_bars([100, 100, 102, 101], highs=[101, 101, 200, 103])
    candidate = Candidate("Donchian 2d/1d", "donchian", (2, 1))
    signals = position_signal(bars, candidate, 86400)
    assert signals.iloc[2] == 1


def test_higher_cost_cannot_improve_same_long_cash_backtest():
    bars = make_bars([10, 10, 12, 13, 11, 10, 12, 14], opens=[10] * 8)
    candidate = Candidate("SMA trend 2d", "sma", (2,))
    no_cost = backtest_long_cash(bars, candidate, 86400, cost_bps_each_side=0)
    with_cost = backtest_long_cash(bars, candidate, 86400, cost_bps_each_side=25)

    assert no_cost["summary"]["trades"] > 0
    assert with_cost["summary"]["return_pct"] < no_cost["summary"]["return_pct"]


def test_fractional_allocation_holds_fixed_units_and_pays_entry_and_exit_costs():
    bars = make_bars(
        [10, 10, 12, 13, 14], opens=[10, 10, 10, 10, 10]
    )
    candidate = Candidate("SMA trend 2d", "sma", (2,))
    result = backtest_long_cash(
        bars, candidate, 86400, cost_bps_each_side=100,
        allocation_pct=50, initial_capital=1000,
    )

    # A $500 allocation includes the entry fee, then keeps the resulting spot
    # units unchanged through the trade and pays a sell fee at the final close.
    expected_final = 500 + (500 / 1.01 / 10) * 14 * 0.99
    assert result["equity_curve"].iloc[-1].equity == pytest.approx(expected_final)
    assert result["equity_curve"].iloc[3].position_pct > 50
    assert result["trades"].iloc[-1].status == "liquidated_at_end"
    assert result["summary"]["cash_return_pct"] == 0


def test_coverage_audit_counts_missing_and_off_grid_candles():
    bars = make_bars([10, 10, 10, 10], start="2020-01-01", granularity="1h")
    bars = bars.iloc[[0, 1, 3]].copy()
    off_grid = make_bars([10], start="2020-01-01 00:30", granularity="1h")
    bars = pd.concat([bars, off_grid], ignore_index=True)

    audit = audit_crypto_bars(bars, 3600, "2020-01-01", "2020-01-01").iloc[0]

    assert audit.expected_bars == 24
    assert audit.observed_bars == 3
    assert audit.missing_bars == 21
    assert audit.unexpected_bars == 1
    assert audit.max_missing_streak_bars == 20
