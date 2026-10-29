"""Market Edge v0.4: research-only ETF intraday experimentation."""
from dataclasses import replace
import hmac
from datetime import date
import io
import pandas as pd
import streamlit as st
from trade_lab.data import generate_synthetic, validate_bars

# Streamlit Cloud may temporarily load a newer app.py with an older cached
# trade_lab.data during a multi-file deployment. This compatibility fallback
# allows the data-quality display to load safely with either module version.
try:
    from trade_lab.data import audit_bar_coverage
except ImportError:
    def audit_bar_coverage(bars: pd.DataFrame) -> dict:
        if bars.empty:
            raise ValueError('Cannot audit an empty bar dataset.')
        sessions = int(bars['timestamp'].dt.tz_convert('America/New_York').dt.date.nunique())
        expected = sessions * 390 * 3
        counts = bars.groupby('timestamp')['symbol'].nunique()
        aligned = int((counts == 3).sum())
        return {
            'sessions': sessions,
            'bars': int(len(bars)),
            'expected_full_session_bars': expected,
            'expected_coverage_pct': 100 * len(bars) / expected if expected else 0.,
            'observed_minutes': int(len(counts)),
            'aligned_minutes': aligned,
            'aligned_minutes_pct': 100 * aligned / len(counts) if len(counts) else 0.,
        }
from trade_lab.alpaca import fetch_bars
from trade_lab.signals import STRATEGIES
from trade_lab.engine import Config, simulate, summarize, split_by_session
from trade_lab.research import run_study, select_development_winner, default_candidates, year_partitions
from trade_lab.archive import SupabaseArchive, ArchivedFetcher, month_windows

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

config = Config(strategy=strategy,target_pct=target_pct,stop_pct=stop_pct,
                slippage_bps_each_side=slip,fee_bps_each_side=fees,
                allocation_pct=allocation,initial_capital=capital)

if bars is None:
    st.info('Use the multi-year laboratory below, or retrieve recent bars in the sidebar for single-period comparisons.')
else:
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


def archive_config():
    """Read credentials from server-side secrets only. No values are displayed."""
    try:
        config = {k: str(st.secrets.get(k, '')).strip() for k in
                  ('SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'MARKET_EDGE_ADMIN_PASSWORD')}
        config['bucket'] = str(st.secrets.get('SUPABASE_BUCKET', 'market-edge-history'))
    except (FileNotFoundError, KeyError):
        return None
    if not all(config[k] for k in ('SUPABASE_URL', 'SUPABASE_SECRET_KEY','MARKET_EDGE_ADMIN_PASSWORD')):
        return None
    if len(config['MARKET_EDGE_ADMIN_PASSWORD']) < 12:
        return None
    return config

# Historical research runs use bounded quarterly requests instead of loading
# an eight-year raw minute-bar dataset in memory.
with st.expander('🧪 Multi-year strategy laboratory (2019 onward)', expanded=False):
    st.markdown('''**Research goal:** Test 16 predefined entry/exit configurations
    using consolidated historical SIP data. Compound a hypothetical $10,000 account
    while keeping development, validation, and final holdout years separate.

    This is a research simulation, not live trading. Reviewing holdout results
    repeatedly and modifying parameters invalidates the final test.''')
    if source != 'Alpaca historical ETF data':
        st.info('Switch Source to Alpaca historical ETF data to enable the multi-year lab.')
    else:
        last_complete = (pd.Timestamp.now(tz='America/New_York').normalize().replace(day=1) - pd.Timedelta(days=1)).date()
        available_years = list(range(2019, last_complete.year+1))
        left, right = st.columns(2)
        first_year = left.selectbox('First calendar year', available_years,
                                   index=max(0, len(available_years)-3))
        end_years = [y for y in available_years if y >= first_year]
        last_year = right.selectbox('Last calendar year', end_years, index=len(end_years)-1)
        periods = year_partitions(first_year, last_year) if last_year-first_year+1 >= 3 else {}
        if periods:
            st.caption('Research partitions: ' + ', '.join(f'{y} {phase.lower()}' for y, phase in periods.items()))
        st.caption('Suggested first run: 2024–2026. Then expand to 2019–2026. '
                   'Monthly archives will survive Streamlit restarts once private storage is configured. '
                   'Long research runs may still exceed free-hosting limits.')

        cloud_config = archive_config()
        cloud_ready = False
        if cloud_config is None:
            st.info('Permanent cloud archive is not configured yet. Backtesting still works, '
                    'but Alpaca history will be downloaded again next time. See README for Supabase setup.')
        else:
            entered = st.text_input('Research admin passphrase (only for using private archive)',
                                    type='password', key='archive_passphrase')
            cloud_ready = bool(entered) and hmac.compare_digest(
                entered, cloud_config['MARKET_EDGE_ADMIN_PASSWORD'])
            if entered and not cloud_ready:
                st.error('Passphrase is not correct. The private archive remains locked.')
            if cloud_ready:
                st.success('Private archive unlocked for this browser session. '
                           'Already archived months will be reused; missing months will be downloaded and saved.')
        reuse_cloud = st.checkbox('Use reusable Supabase archive (private, monthly files)',
                                  value=cloud_ready, disabled=not cloud_ready)

        minimum = st.number_input('Minimum development trades', min_value=1,
                                  max_value=1000, value=100, step=25)
        max_dd = st.slider('Maximum development drawdown (%)', 5, 60, 20, 5)
        st.caption(f'16 fixed candidates = 4 entry strategies × 4 take-profit/stop pairs. '
                   f'Allocation {allocation}%, slippage {slip:g} bps and fees {fees:g} bps per side.')
        if cloud_ready and reuse_cloud:
            if st.button('Archive missing historical months — no backtest', key='archive_only'):
                if not key or not secret:
                    st.error('Enter your current Alpaca API credentials in the sidebar first.')
                else:
                    begin, finish = date(first_year, 1, 1), min(last_complete, date(last_year, 12, 31))
                    windows = list(month_windows(begin, finish))
                    bar = st.progress(0)
                    status = st.empty()
                    try:
                        archive = SupabaseArchive(cloud_config['SUPABASE_URL'],
                                                  cloud_config['SUPABASE_SECRET_KEY'], cloud_config['bucket'])
                        loader = ArchivedFetcher(archive,
                            lambda a,b: fetch_bars(key, secret, a, b, feed='sip'))
                        for idx, (month_first,month_last) in enumerate(windows,1):
                            loader(month_first.isoformat(), month_last.isoformat())
                            bar.progress(idx/len(windows))
                            status.caption(f'{idx}/{len(windows)} months checked — {month_first:%Y-%m}')
                        st.success(f'Archive ready: reused {loader.cache_hits} months and saved '
                                   f'{loader.saved} previously missing months. No trades executed.')
                    except Exception as exc:
                        st.error('Archive interrupted: ' + str(exc)[:240] +
                                 '. Months saved before the interruption remain available; rerun to resume.')
        if st.button('Run multi-year backtest — no real orders', type='primary', key='run_historical_lab'):
            if last_year-first_year+1 < 3:
                st.error('Choose at least three calendar years to separate development, validation, and holdout.')
            elif not key or not secret:
                st.error('Enter your current Alpaca API credentials into the masked fields first.')
            else:
                begin = date(first_year, 1, 1)
                end = min(last_complete, date(last_year, 12, 31))
                meter = st.progress(0)
                status = st.empty()
                def progress(done, total, label):
                    meter.progress(min(1.0, done / total))
                    status.caption(f'{done}/{total} historical chunks: {label}')
                try:
                    with st.spinner('Downloading quarterly SIP data and backtesting fixed candidates...'):
                        downloader = lambda a, b: fetch_bars(key, secret, a, b, feed='sip')
                        cloud_fetcher = None
                        if reuse_cloud and cloud_ready:
                            archive = SupabaseArchive(cloud_config['SUPABASE_URL'],
                                                      cloud_config['SUPABASE_SECRET_KEY'], cloud_config['bucket'])
                            cloud_fetcher = ArchivedFetcher(archive, downloader)
                        fetcher = cloud_fetcher if cloud_fetcher is not None else downloader
                        study = run_study(fetcher, begin, end, config,
                                          candidates=default_candidates(), progress=progress)
                    study['archive_status'] = (f"Reused {cloud_fetcher.cache_hits} saved months; "
                                               f"downloaded and archived {cloud_fetcher.saved} months."
                                               if cloud_fetcher is not None else
                                               'Archive not enabled: history was downloaded without permanent caching.')
                    st.session_state['long_study'] = study
                    st.session_state['long_study_selection'] = (int(minimum), -float(max_dd))
                    st.success('Historical research finished. These results use real historical data.')
                except Exception as exc:
                    st.error(f'Research stopped: {str(exc)[:300]}')
        if 'long_study' in st.session_state:
            study = st.session_state['long_study']
            n, dd = st.session_state.get('long_study_selection', (100, -20.0))
            selected = select_development_winner(study, n, dd)
            st.divider()
            st.caption(study.get('archive_status', ''))
            st.subheader('Preselected winner — chosen ONLY on development results')
            st.write('**Selected configuration:** ' + selected['winner'])
            if not selected['qualified']:
                st.warning('No candidate met the development minimum trades and drawdown criteria. '
                           'This is an exploratory leader, not a qualified strategy.')
            view = selected['selected'][['period','trades','win_rate','total_return','net_pnl',
                                           'starting_equity','ending_equity','max_drawdown','profit_factor']]
            st.dataframe(view, use_container_width=True, hide_index=True)
            st.caption('Development determines the winner. Validation and final holdout are shown only '
                       'for that selected configuration, and must not be used to retune it.')
            st.markdown('**Development ranking of all 16 predefined candidates**')
            st.dataframe(selected['development_table'][['candidate','trades','win_rate',
                                                        'total_return','max_drawdown','profit_factor']],
                         use_container_width=True, hide_index=True)
            st.markdown('**Market-regime breakdown for the selected strategy (development only)**')
            regimes = study.get('regime_results')
            if regimes is not None and not regimes.empty:
                reg = regimes.loc[(regimes['candidate'] == selected['winner']) &
                                  (regimes['period'] == 'Development') &
                                  (regimes['regime'] != 'Insufficient history')].copy()
                if reg.empty:
                    st.info('Not enough historical QQQ sessions to calculate a regime breakdown.')
                else:
                    st.dataframe(reg[['regime','trades','win_rate','avg_trade_return_pct','pnl_dollars']],
                                 hide_index=True, use_container_width=True)
                    if (reg['trades'] < 30).any():
                        st.warning('Some regimes have fewer than 30 trades. Treat differences as exploratory, not predictive.')
                    st.caption('Regimes use only PREVIOUS days’ QQQ closes: 50-day trend and 20-day realized volatility. '
                               'No future data is used in the classification. These results do not automatically filter trades.')
                st.download_button('Download all regime summaries CSV',regimes.to_csv(index=False),
                                   file_name='market_edge_regime_summary.csv',mime='text/csv')
            st.download_button('Download strategy research results CSV',
                               study['results'].to_csv(index=False),
                               file_name=f"market_edge_study_{study['start']}_{study['end']}.csv", mime='text/csv')
            st.download_button('Download market-data coverage CSV',
                               study['coverage'].to_csv(index=False),
                               file_name='market_edge_coverage.csv', mime='text/csv')
            st.caption('Caution: this is a bar-based simulation, not a brokerage fill model. '
                       'Minute bars, slippage assumptions, corporate actions, and model selection all create uncertainty.')

if bars is None:
    st.stop()

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