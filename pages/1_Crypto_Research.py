"""First-pass crypto trend study; research-only and isolated from ETF experiments."""
import pandas as pd
import streamlit as st

from trade_lab.crypto_research import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    GRANULARITIES,
    PRODUCTS,
    VALIDATION_END,
    VALIDATION_START,
    WARMUP_START,
    audit_crypto_bars,
    fetch_coinbase_candles,
    run_candidate_suite,
)


st.set_page_config(page_title="Crypto Research | Market Edge", page_icon="₿", layout="wide")
st.title("Crypto Research Lab")
st.caption("Research-only spot backtests · long or cash · no leverage, shorting, or live orders")
st.warning(
    "Crypto is highly volatile. A backtest is a historical simulation, not a guarantee of future returns. "
    "The 2024 and later sample is intentionally excluded from this first iteration and remains reserved for a later frozen test.",
    icon="⚠️",
)

st.markdown(
    "The predeclared candidates compare 20/50/100-day simple moving-average trends, 20/10-day and "
    "55/20-day Donchian breakouts, and 20/60/120/240-day time-series momentum. Signals use completed "
    "candles and execute at the next candle open. Buy-and-hold is shown as a benchmark."
)


@st.cache_data(ttl=86400, max_entries=12, show_spinner=False)
def cached_coinbase_bars(product: str, granularity: int) -> pd.DataFrame:
    # The initial frozen research windows use one fixed date range so candidate
    # changes cannot accidentally consume the later holdout in the UI.
    return fetch_coinbase_candles(
        product,
        WARMUP_START.isoformat(),
        VALIDATION_END.isoformat(),
        granularity,
        request_pause_seconds=0.12,
    )


with st.sidebar:
    st.header("Historical data")
    products = st.multiselect("Coinbase USD pairs", PRODUCTS, default=list(PRODUCTS))
    label_to_granularity = {label: seconds for seconds, label in GRANULARITIES.items()}
    granularity_label = st.selectbox("Candle size", list(label_to_granularity), index=1)
    granularity = label_to_granularity[granularity_label]
    st.caption(
        "Indicators use a 2016 warm-up; measured study windows are 2017–2023. "
        "Coinbase publishes at most 300 candles per request."
    )
    st.divider()
    st.header("Simulation assumptions")
    cost_bps = st.slider(
        "Combined fee + slippage per order side (bps)",
        min_value=5, max_value=100, value=25, step=5,
        help="One buy or sell. This is a scenario input, not a quote of your Coinbase account fee tier.",
    )
    allocation = st.slider(
        "Spot allocation while long (%)", min_value=10, max_value=100,
        value=100, step=10,
        help="100% means unlevered full-equity spot exposure; leverage is not modeled.",
    )
    capital = st.number_input(
        "Starting hypothetical capital ($)", min_value=1000, max_value=1000000,
        value=10000, step=1000,
    )
    run = st.button("Fetch data and run baseline", type="primary", disabled=not products)


if run:
    frames = []
    coverage_frames = []
    try:
        for product in products:
            with st.spinner(f"Fetching {product} candles from Coinbase..."):
                product_bars = cached_coinbase_bars(product, granularity)
            frames.append(product_bars)
            coverage_frames.append(audit_crypto_bars(
                product_bars, granularity,
                DEVELOPMENT_START.isoformat(), VALIDATION_END.isoformat(),
            ))
        bars = pd.concat(frames, ignore_index=True).sort_values(["timestamp", "symbol"])
        coverage = pd.concat(coverage_frames, ignore_index=True)
        st.session_state["crypto_bars"] = bars
        st.session_state["crypto_coverage"] = coverage
        st.session_state["crypto_run_config"] = {
            "granularity": granularity,
            "cost_bps": cost_bps,
            "allocation": allocation,
            "capital": capital,
        }
    except Exception as exc:
        st.error(f"Historical data request failed: {exc}")


bars = st.session_state.get("crypto_bars")
coverage = st.session_state.get("crypto_coverage")
run_config = st.session_state.get("crypto_run_config")

if bars is None:
    st.info("Choose the pairs and assumptions in the sidebar, then run the baseline. No account connection is used.")
else:
    st.subheader("Data coverage")
    st.dataframe(coverage, use_container_width=True, hide_index=True)
    if (
        float(coverage["coverage_pct"].min()) < 98.0
        or int(coverage["max_missing_streak_bars"].max()) > 4
        or int(coverage["unexpected_bars"].sum()) > 0
    ):
        st.warning(
            "Review candle gaps before trusting this backtest. The audit shows coverage, the longest missing run, "
            "and off-grid timestamps for each product."
        )

    # Use the latest sidebar assumptions when the user explicitly runs again;
    # preserve the run settings for a reproducible result display.
    st.subheader("Predeclared candidates")
    try:
        results = run_candidate_suite(
            bars,
            run_config["granularity"],
            cost_bps_each_side=run_config["cost_bps"],
            allocation_pct=run_config["allocation"],
            initial_capital=run_config["capital"],
        )
        st.caption(
            f"Development: {DEVELOPMENT_START}–{DEVELOPMENT_END} · "
            f"Validation: {VALIDATION_START}–{VALIDATION_END} · "
            f"Cost scenario: {run_config['cost_bps']} bps per side · "
            f"Allocation: {run_config['allocation']}% of equity"
        )
        st.dataframe(
            results.sort_values(["symbol", "phase", "candidate"]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "return_pct": st.column_config.NumberColumn(format="%.1f%%"),
                "cagr_pct": st.column_config.NumberColumn(format="%.1f%%"),
                "buy_hold_return_pct": st.column_config.NumberColumn(format="%.1f%%"),
                "max_drawdown_pct": st.column_config.NumberColumn(format="%.1f%%"),
                "exposure_pct": st.column_config.NumberColumn(format="%.1f%%"),
                "win_rate_pct": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
        st.download_button(
            "Download results CSV",
            data=results.to_csv(index=False).encode("utf-8"),
            file_name="crypto_trend_baseline_2017_2023.csv",
            mime="text/csv",
        )
        st.caption(
            "Interpret validation as a check, not another tuning set. We should freeze any candidate before "
            "opening the 2024+ holdout. Cash earns 0% in this simulation; no taxes or deposits are modeled."
        )
    except Exception as exc:
        st.error(f"The backtest could not be completed: {exc}")
