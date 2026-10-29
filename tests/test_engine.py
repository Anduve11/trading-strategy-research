import pandas as pd
from trade_lab.data import generate_synthetic, validate_bars, audit_bar_coverage
from trade_lab.engine import Config, simulate, summarize, split_by_session
from trade_lab.signals import STRATEGIES, calculate_signals


def test_generated_bars_and_training_split():
    bars = generate_synthetic(12)
    assert len(bars) == 12*390*3
    train, test, cutoff = split_by_session(bars)
    assert train.timestamp.max() < test.timestamp.min()
    assert test.timestamp.dt.tz_convert('America/New_York').dt.date.min() == cutoff


def test_all_strategies_execute_without_overnight_holds():
    bars = generate_synthetic(12)
    for strategy in STRATEGIES:
        trades, equity = simulate(bars, Config(strategy=strategy))
        assert len(equity) == 12
        assert len(trades) <= 12
        if not trades.empty:
            a=trades.entry_time.dt.tz_convert('America/New_York')
            b=trades.exit_time.dt.tz_convert('America/New_York')
            assert (a.dt.date == b.dt.date).all()
            assert (b.dt.strftime('%H:%M') <= '15:54').all()
            assert set(trades.ticker).issubset({'TQQQ','SQQQ'})
        summary=summarize(trades,equity)
        assert summary['trades'] == len(trades)


def test_invalid_ohlc_is_rejected():
    df = generate_synthetic(2)
    df.loc[0,'high'] = 0.01
    try:
        validate_bars(df)
        assert False, 'Should reject inconsistent OHLC'
    except ValueError:
        pass


def test_next_bar_prevents_signal_bar_entry():
    df=generate_synthetic(8)
    q=calculate_signals(df,'EMA trend')
    trades,_=simulate(df,Config(strategy='EMA trend'))
    if not trades.empty:
        for _,r in trades.iterrows():
            assert r.entry_time > r.signal_time
            assert r.entry_time - r.signal_time == pd.Timedelta(minutes=1)


def test_zero_fee_but_higher_slippage_cannot_improve_same_trade():
    df=generate_synthetic(10)
    low,_=simulate(df,Config(strategy='EMA trend',target_pct=20,stop_pct=20,slippage_bps_each_side=0))
    high,_=simulate(df,Config(strategy='EMA trend',target_pct=20,stop_pct=20,slippage_bps_each_side=10))
    if len(low):
        assert list(low['ticker'])==list(high['ticker'])
        assert (high['net_return_pct'].to_numpy() <= low['net_return_pct'].to_numpy()+1e-8).all()


def test_full_session_and_missing_bar_coverage():
    df = generate_synthetic(2)
    full = audit_bar_coverage(df)
    assert full['expected_coverage_pct'] == 100
    assert full['aligned_minutes_pct'] == 100
    missing = audit_bar_coverage(df.iloc[1:].copy())
    assert missing['expected_coverage_pct'] < 100
    assert missing['aligned_minutes_pct'] < 100