"""Market Edge v0.1: no brokerage execution or live trading."""
from dataclasses import replace
import io
import pandas as pd
import streamlit as st
from trade_lab.data import generate_synthetic, validate_bars, audit_bar_coverage
from trade_lab.alpaca import fetch_bars
from trade_lab.signals import STRATEGIES
from trade_lab.engine import Config, simulate, summarize, split_by_session

st.set_page_config(page_title='Market Edge — Research Lab', page_icon='📈', layout='wide')
st.title('Market Edge  |  Intraday ETF Research Lab')
st.caption('RESEARCH & PAPER SIMULATION ONLY · TQQQ / SQQQ entries driven by completed QQQ 1-minute bars · no live orders')
st.warning('Results are hypothetical. Leveraged ETFs can lose money rapidly. 1-minute OHLC bars cannot reveal the exact order of intrabar price moves; ambiguous bars are scored as stop-losses. Stops can execute worse in live markets.', icon='⚠️')

with st.sidebar:
    st.header('Data')
    source = st.radio('Source', ['Synthetic demo (fake data)', 'Upload historical 1-minute CSV', 'Alpaca historical ETF data'])
    bars = None
    if source == 'Synthetic demo (fake data)':
        days = st.slider('Synthetic sessions', 20, 100, 65, step=5)
        bars = generate_synthetic(days=days)
        st.info('Artificial test data only. Do NOT use these outcomes to evaluate a trading strategy.')
    elif source == 'Upload historical 1-minute CSV':
        uploaded = st.file_uploader('Upload CSV', type='csv')
        st.caption('Required: timestamp, symbol, open, high, low, close, volume. Include QQQ, TQQQ, SQQQ; timestamps ISO-8601 with timezone/UTC.')
        if uploaded:
            try:
                bars = validate_bars(pd.read_csv(uploaded))
            except Exception as exc:
                st.error(f'CSV validation error: {exc}')
    else:
        feed_label = st.selectbox('Historical price feed', ['SIP — consolidated (recommended)', 'IEX — single exchange (incomplete)'])
        feed = 'sip' if feed_label.startswith('SIP') else 'iex'
        st.caption('Historical SIP data older than 15 minutes is available on Alpaca Basic. IEX covers one exchange only and may omit many 1-minute bars.')
        key = st.text_input('Alpaca key ID', type='password')
        secret = st.text_input('Alpaca secret', type='password')
        a,b = st.columns(2)
        start = a.date_input('From', value=pd.Timestamp('2026-08-03').date())
        end = b.date_input('Through', value=pd.Timestamp('2026-08-14').date())
        if st.button('Fetch historical data'):
            try:
                with st.spinner('Retrieving three aligned symbols...'):
                    downloaded = fetch_bars(key, secret, str(start), str(end), feed=feed)
                    st.session_state['alpaca_bars'] = downloaded
                    st.session_state['alpaca_feed'] = feed
            except Exception as exc:
                st.error(str(exc))
        bars = st.session_state.get('alpaca_bars')
        if bars is not None:
            st.caption(f"Currently loaded: {st.session_state.get('alpaca_feed', 'unknown').upper()} feed. Click Fetch after changing feed or dates.")
    st.divider()
    st.header('Risk / execution assumptions')
    strategy = st.selectbox('Entry strategy', STRATEGIES)
    target_pct = st.slider('Take-profit %', .5, 5., 1.5, .25)
    stop_pct = st.slider('Stop-loss %', .5, 5., 1., .25)
    slip = st.slider('Slippage, basis points per side', 0., 30., 5., 1.)
    fees = st.slider('Fees, basis points per side', 0., 30., 0., 1.)
    allocation = st.slider('Allocation % of equity per trade', 1, 100, 10, 1)
    capital = st.number_input('Initial hypothetical capital ($)', min_value=1000, max_value=1000000, value=10000, step=1000)

if bars is None:
    st.info('Supply a historical CSV or retrieve Alpaca data, or use the synthetic demo to inspect the app.')
    st.stop()
try:
    train, test, cutoff = split_by_session(bars)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

st.info(f'Data loaded: **{len(bars):,}** one-minute bars across **{bars.timestamp.dt.tz_convert("America/New_York").dt.date.nunique()}** sessions. Holdout starts **{cutoff}**. Data source: **{source}**.')
coverage = audit_bar_coverage(bars)
st.caption(f"Data quality: **{coverage['expected_coverage_pct']:.1f}%** of bars expected for full 390-minute sessions, "
           f"and **{coverage['aligned_minutes_pct']:.1f}%** of observed minute timestamps contain all three symbols. "
           'Coverage denominator assumes full trading days; half-days require a trading calendar adjustment.')
if coverage['expected_coverage_pct'] < 98 or coverage['aligned_minutes_pct'] < 98:
    st.warning('Incomplete or unsynchronized 1-minute bars detected. Backtest results may be distorted by missing price minutes. Prefer historical SIP data; do not treat this run as execution-quality evidence.')
if source == 'Alpaca historical ETF data' and st.session_state.get('alpaca_feed') == 'iex':
    st.warning('This run uses the limited IEX feed. Select historical SIP, click Fetch, and compare coverage before interpreting the strategy results.')
config = Config(strategy=strategy,target_pct=target_pct,stop_pct=stop_pct,
                slippage_bps_each_side=slip,fee_bps_each_side=fees,
                allocation_pct=allocation,initial_capital=capital)

single, sweep = st.tabs(['Strategy backtest', 'Compare entry and exit strategies'])

with single:
    trn, eqn = simulate(train,config)
    te, eqt = simulate(test,config)
    ms = summarize(trn,eqn,capital)
    mt = summarize(te,eqt,capital)
    st.subheader('Chronological out-of-sample validation')
    st.caption('First 70% of trading sessions = development period. Last 30% = holdout. Tune on development data; repeatedly inspecting the holdout eventually contaminates it.')
    for label, met, trades, eq in [('Development (70%)',ms,trn,eqn),('Holdout (30%)',mt,te,eqt)]:
        st.markdown(f'**{label}**')
        c = st.columns(4)
        c[0].metric('Trades',met['trades'])
        c[1].metric('Win rate',f"{met['win_rate']:.1f}%")
        c[2].metric('Return on account',f"{met['total_return']:+.2f}%")
        c[3].metric('Max drawdown*',f"{met['max_drawdown']:.2f}%")
        st.caption('Drawdown sampled after trades/end of sessions, not intrabar. Return incorporates configured allocation and costs.')
        if not eq.empty:
            st.line_chart(eq.set_index('date')['equity'])
        if not trades.empty:
            view = trades[['date','ticker','entry_time','exit_time','reason','net_return_pct','pnl_dollars','ambiguous_bar']].copy()
            st.dataframe(view, use_container_width=True, hide_index=True)
            st.download_button(f'Download {label} trades CSV', trades.to_csv(index=False), file_name=f"market_edge_{'train' if label.startswith('Development') else 'holdout'}_trades.csv", mime='text/csv')
        else:
            st.warning('No trades in this segment under the selected settings.')

with sweep:
    st.subheader('Development-set strategy sweep')
    st.caption('Compare four entry signals against 9 exit configurations; rank on development data only, then evaluate the chosen configuration once on the holdout. This is research, not automatic strategy discovery.')
    take_grid = st.multiselect('Take-profit values (%)', [1.,1.5,2.,3.], default=[1.,1.5,2.])
    stop_grid = st.multiselect('Stop-loss values (%)', [.75,1.,1.5,2.], default=[.75,1.,1.5])
    min_trades = st.number_input('Minimum development trades', min_value=1, max_value=100, value=8)
    if st.button('Run comparison on development data', type='primary'):
        if not take_grid or not stop_grid:
            st.error('Select at least one target and stop value.')
        else:
            rows=[]
            progress=st.progress(0)
            combos=[(s,tp,sp) for s in STRATEGIES for tp in take_grid for sp in stop_grid]
            for j,(s,tp,sp) in enumerate(combos):
                cfg=replace(config,strategy=s,target_pct=tp,stop_pct=sp)
                trades, eq=simulate(train,cfg)
                m=summarize(trades,eq,capital)
                rows.append({'strategy':s,'target_pct':tp,'stop_pct':sp,**m})
                progress.progress((j+1)/len(combos))
            st.session_state['sweep_results'] = pd.DataFrame(rows)
    if 'sweep_results' in st.session_state:
        res=st.session_state['sweep_results'].copy()
        qualifying=res[res.trades >= min_trades].sort_values('total_return',ascending=False)
        st.dataframe(qualifying, use_container_width=True, hide_index=True)
        if not qualifying.empty:
            st.caption('Highest development return is NOT a validated edge. Sweep ranking is susceptible to multiple-testing bias.')
            idx=st.selectbox('Choose ONE configuration for a holdout check', range(len(qualifying)), format_func=lambda i: f"{qualifying.iloc[i].strategy} | target {qualifying.iloc[i].target_pct}% | stop {qualifying.iloc[i].stop_pct}%")
            if st.button('Evaluate selected strategy on holdout'):
                r=qualifying.iloc[idx]
                cfg=replace(config,strategy=r.strategy,target_pct=float(r.target_pct),stop_pct=float(r.stop_pct))
                t,e=simulate(test,cfg)
                m=summarize(t,e,capital)
                st.write({'configuration':f'{r.strategy}, target {r.target_pct}%, stop {r.stop_pct}%', 'holdout_metrics':m})
                st.caption('Changing the strategy after seeing holdout results makes that period no longer a clean holdout.')
        else:
            st.warning('No strategies meet the minimum trade threshold.')

st.divider()
with st.expander('Methodology and limitations — read before interpreting results'):
    st.markdown('''
- **Signal timing:** QQQ signal uses only a completed minute bar; entry is at the next minute's TQQQ/SQQQ opening price, plus assumed adverse slippage.
- **Trade direction:** Bullish QQQ buys TQQQ; bearish QQQ buys SQQQ. No shorting. Maximum one trade per regular-session day.
- **Risk:** Stop and target levels are measured from the actual simulated entry fill. If both touched in the same minute, STOP is assumed first. Intrabar order cannot be known from OHLC bars. An unfavorable opening gap can execute worse than the stop on later minutes.
- **Forced exit:** Position is liquidated at or before the 3:54 PM ET bar close, with adverse slippage. No overnight position.
- **Friction:** Separate adjustable fees and adverse slippage per side; does not model partial fills, halt conditions, bid/ask spread variation, market impact, borrowing, or financing.
- **Performance:** Equity is updated after completed trades; max drawdown does not capture interim intratrade equity swings.
- **Data:** The free IEX feed has incomplete exchange coverage. For valid historical research prefer consolidated SIP trades plus quotes and split-corrected prices. Validate symbol coverage, missing bars, and session calendars before trusting results.
- **Multiple testing:** Comparing dozens of parameter combinations will produce lucky winners. Use forward-chaining walk-forward validation and untouched test periods before believing a backtest.
- **Not implemented:** Broker orders, live data streams, AI sentiment, real-world paper orders, position reconciliation, alarms, earnings/macro calendars, and portfolio-level risk controls.
''')