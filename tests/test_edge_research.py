from dataclasses import replace
import numpy as np
import pandas as pd
import pytest

from trade_lab.data import generate_synthetic
from trade_lab.edge_research import (PRICE_FEATURES, OPTION_FEATURES, EXITS, ExitPolicy,
    complete_session, extract_decisions, add_outcomes, simulate_window,
    append_option_features, fetch_option_history, choose_side, account_daily,
    metrics, block_bootstrap_interval, feature_specs, walk_forward_search)
from trade_lab.cross_asset import append_cross_asset


@pytest.fixture(scope='module')
def synthetic_bars():
    return generate_synthetic(55)


def test_full_minute_grid_rejects_duplicates_and_missing(synthetic_bars):
    day = synthetic_bars.timestamp.dt.tz_convert('America/New_York').dt.date.min()
    x = synthetic_bars.loc[synthetic_bars.timestamp.dt.tz_convert('America/New_York').dt.date.eq(day)]
    assert complete_session(x)
    assert not complete_session(x.iloc[1:])
    assert not complete_session(pd.concat([x.iloc[1:], x.iloc[1:2]]))


def test_future_prices_cannot_change_decision_features(synthetic_bars):
    before, _, _ = extract_decisions(synthetic_bars)
    first = before.iloc[0]
    mutated = synthetic_bars.copy()
    # Change every QQQ OHLC after the decision; these bars include the labels.
    mask = mutated.symbol.eq('QQQ') & mutated.timestamp.gt(first.timestamp + pd.Timedelta(minutes=5)) & (
        mutated.timestamp.dt.tz_convert('America/New_York').dt.date.eq(first.date))
    mutated.loc[mask, ['open', 'high', 'low', 'close']] *= 1.2
    after, _, _ = extract_decisions(mutated)
    a = after.loc[(after.date == first.date) & (after.decision_minute == first.decision_minute)].iloc[0]
    np.testing.assert_allclose(first[list(PRICE_FEATURES)].astype(float), a[list(PRICE_FEATURES)].astype(float))
    assert abs(first.qqq_forward_30m_pct - a.qqq_forward_30m_pct) > 10


def test_feature_state_crosses_month_boundaries_without_changes(synthetic_bars):
    whole, state, _ = extract_decisions(synthetic_bars)
    days = synthetic_bars.timestamp.dt.tz_convert('America/New_York').dt.date
    unique = sorted(days.unique())
    _, prior, _ = extract_decisions(synthetic_bars.loc[days <= unique[52]])
    chunk, final_state, _ = extract_decisions(synthetic_bars.loc[days > unique[52]], prior)
    expected = whole.loc[whole.date > unique[52]].reset_index(drop=True)
    pd.testing.assert_frame_equal(chunk, expected)
    assert state == final_state


def price_window():
    index = pd.date_range('2024-06-03 14:00Z', periods=60, freq='min')
    return pd.DataFrame({'open': 100., 'high': 100.01, 'low': 99.99, 'close': 100.}, index=index)


def test_exact_horizon_and_round_trip_cost():
    x = price_window()
    x.iloc[30:, x.columns.get_loc('close')] = 200.
    value, ambiguous = simulate_window(x, x.index[0], 30, EXITS[0], slippage_bps=5)
    assert value == pytest.approx(100 * ((1 - .0005) / (1 + .0005) - 1))
    assert not ambiguous
    value60, _ = simulate_window(x, x.index[0], 60, EXITS[0], slippage_bps=5)
    assert value60 > 90
    with pytest.raises(ValueError, match='Incomplete'):
        simulate_window(x.drop(x.index[5]), x.index[0], 30, EXITS[0])


def test_stop_first_and_gap_through_stop():
    x = price_window()
    x.iloc[3] = [100., 101., 99., 100.]
    value, ambiguous = simulate_window(x, x.index[0], 30, EXITS[1], slippage_bps=0)
    assert value == pytest.approx(-.25)
    assert ambiguous
    x.iloc[3] = [98., 98.1, 97.9, 98.]
    value, _ = simulate_window(x, x.index[0], 30, EXITS[1], slippage_bps=0)
    assert value == pytest.approx(-2.)


def test_outcomes_use_actual_etf_prices(synthetic_bars):
    decisions, _, _ = extract_decisions(synthetic_bars)
    first = decisions.head(1)
    outcome = add_outcomes(synthetic_bars, first)
    assert len(outcome) == 8
    assert outcome.tqqq_net_10bps_pct.notna().all()
    # QQQ bars do not determine the realized TQQQ or SQQQ exit path.
    modified = synthetic_bars.copy()
    mask = modified.symbol.eq('TQQQ') & modified.timestamp.gt(first.iloc[0].timestamp + pd.Timedelta(minutes=5))
    modified.loc[mask, ['open', 'high', 'low', 'close']] *= 1.1
    changed = add_outcomes(modified, first)
    np.testing.assert_allclose(outcome.sqqq_net_5bps_pct, changed.sqqq_net_5bps_pct)
    assert not np.allclose(outcome.tqqq_net_5bps_pct, changed.tqqq_net_5bps_pct)


def test_options_are_strictly_prior_and_stale_rejected():
    dates = pd.bdate_range('2024-01-01', periods=10)
    history = pd.DataFrame({'date': dates, 'VIX': 20., 'VIX9D': 10., 'VVIX': np.arange(10) + 100.})
    decisions = pd.DataFrame({'date': [dates[-1].date(), pd.Timestamp('2024-03-01').date()], 'prior_vol_20': [.2, .2]})
    result = append_option_features(decisions, history)
    assert result.prior_vvix.iloc[0] == 108
    assert result.prior_vix9d_vix.iloc[0] == .5
    assert result[list(OPTION_FEATURES)].iloc[1].isna().all()
    history.loc[9, ['VIX', 'VIX9D', 'VVIX']] = 10000.
    changed = append_option_features(decisions, history)
    pd.testing.assert_frame_equal(result, changed)


def test_cross_asset_waits_two_business_days_and_handles_negative_oil():
    dates = pd.bdate_range('2024-01-01', periods=10)
    source = pd.DataFrame({'date': dates, 'DEXUSEU': np.arange(10) + 1.,
                           'DCOILWTICO': [-10.] * 10, 'BAMLH0A0HYM2': np.arange(10) + 2.})
    decisions = pd.DataFrame({'date': [dates[-1].date()]})
    result = append_cross_asset(decisions, source)
    assert result.credit_spread.iloc[0] == 9.  # Jan 10 observed, Jan 12 available.
    assert np.isfinite(result.oil_change5.iloc[0])
    source.loc[8:, 'BAMLH0A0HYM2'] = 999.
    changed = append_cross_asset(decisions, source)
    pd.testing.assert_frame_equal(result, changed)


def test_trade_cushion_ties_and_account_allocation():
    side = choose_side([[.1, -.1], [-.1, .2], [.2, .2], [-1, -2], [.05, 0]], .05)
    assert side.tolist() == [1, -1, 0, 0, 0]
    frame = pd.DataFrame({'date': pd.bdate_range('2024-01-01', periods=5).date,
                          'tqqq_net_5bps_pct': [1.] * 5, 'sqqq_net_5bps_pct': [-1.] * 5})
    r = account_daily(frame, side)
    assert r.tolist() == [.001, -.001, 0., 0., 0.]
    assert metrics(frame, side)['trades'] == 2
    with pytest.raises(ValueError, match='chronological'):
        account_daily(pd.concat([frame, frame]), np.r_[side, side])


def mock_research_data():
    rng = np.random.default_rng(47)
    dates = pd.bdate_range('2019-01-01', '2026-09-30')
    x = rng.normal(size=len(dates))
    df = pd.DataFrame({c: rng.normal(size=len(dates)) for c in PRICE_FEATURES})
    df['gap'] = x
    df['date'] = dates.date
    df['decision_minute'] = '09:59'
    df['horizon'] = 30
    df['exit_policy'] = 'time_only'
    df['tqqq_net_5bps_pct'] = .3 * x - .1
    df['sqqq_net_5bps_pct'] = -.3 * x - .1
    df['tqqq_net_10bps_pct'] = df.tqqq_net_5bps_pct - .1
    df['sqqq_net_10bps_pct'] = df.sqqq_net_5bps_pct - .1
    df['qqq_forward_30m_pct'] = .1 * x
    return df


def test_future_outcomes_never_select_candidate():
    data = mock_research_data()
    specs = {'price': {'columns': list(PRICE_FEATURES), 'macro_weight': 0.}}
    before = walk_forward_search(data, specs, model_names=('ridge',), cushions=(0., .05))
    changed = data.copy()
    future = pd.to_datetime(changed.date).dt.year >= 2024
    changed.loc[future, ['tqqq_net_5bps_pct', 'sqqq_net_5bps_pct']] *= -10
    after = walk_forward_search(changed, specs, model_names=('ridge',), cushions=(0., .05))
    assert before['selected'] == after['selected']
    pd.testing.assert_frame_equal(before['ranking'], after['ranking'])
    assert before['reports']['inspected_2024']['return_pct'] != after['reports']['inspected_2024']['return_pct']
    assert before['go_no_go'] == 'NO_VALIDATED_EDGE'


def test_bootstrap_reproducible_and_no_trade_days_included():
    a = block_bootstrap_interval(np.r_[np.zeros(95), np.ones(5) * .01])
    assert a == block_bootstrap_interval(np.r_[np.zeros(95), np.ones(5) * .01])
    assert a[0] <= .05 <= a[1]
    assert block_bootstrap_interval(np.zeros(10)) is None


def test_no_model_passes_trade_minimum():
    data = mock_research_data()
    specs = {'price': {'columns': list(PRICE_FEATURES), 'macro_weight': 0.}}
    result = walk_forward_search(data, specs, model_names=('ridge',), min_trades=10000)
    assert result['selected'] is None
    assert result['reports'] == {}
