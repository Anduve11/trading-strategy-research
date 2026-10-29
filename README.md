# Market Edge — ETF Intraday Research Lab (v0.1)

A working, **research-only** Streamlit dashboard for testing simple intraday strategies on **QQQ signals** and **TQQQ/SQQQ execution**. No orders can be sent to a broker.

## Browser-only deployment (free)

1. Open the private GitHub repository **[Anduve11/trading-strategy-research](https://github.com/Anduve11/trading-strategy-research)**. The source code is stored in this repository.
2. Visit **https://share.streamlit.io** and sign in with GitHub. Authorize Streamlit to access this private repository if prompted.
3. Select **Create app**, choose repository `Anduve11/trading-strategy-research`, branch `main`, and entrypoint **`app.py`**. Deploy.
4. Select **Synthetic demo** to check the UI works. **Synthetic results have no trading significance.**
5. Select **Upload historical CSV** for real data, or **Alpaca historical ETF data**. The app now defaults to historical consolidated SIP data (more than 15 minutes old), which Alpaca Basic currently allows without a paid real-time plan. Select IEX only for comparison/debugging; its one-exchange coverage is not suitable for execution-quality research. API credentials are entered using masked in-session inputs and are *not saved to files*. Never commit credentials to GitHub.

The app uses free hosting without any computer remaining on. The app may sleep during inactivity; it does not continuously trade or collect market data while asleep.

## Data schema

Provide 1-minute bars with columns:

```csv
timestamp,symbol,open,high,low,close,volume
2026-06-01T13:30:00Z,QQQ,500.0,500.2,499.8,500.1,10000
2026-06-01T13:30:00Z,TQQQ,60.0,60.1,59.9,60.05,10000
2026-06-01T13:30:00Z,SQQQ,35.0,35.1,34.9,34.98,10000
```

Actual files must have many consecutive complete 9:30–15:59 ET sessions. Timestamp is the **start** of each one-minute bar. Each ETF must have its **own actual price history**. Use prices consistently split-adjusted, and align timestamps across symbols. Only regular trading hours are analyzed. A partial day, missing bars, or inaccurate corporate-action handling can materially distort results.

## Currently supported experiments

- Four distinct signals: Momentum + VWAP, Opening Range Breakout, EMA Trend, VWAP Reversion.
- Buy TQQQ on bullish QQQ signals; buy SQQQ on bearish signals; otherwise cash.
- At most one trade per day, entry next-bar open, profit/stop checks on actual ETF bars, mandatory intraday closing.
- Configurable take profit, stop loss, per-side execution friction, allocation, and capital.
- Conservative stop-first fill if the stop and target are both inside a single minute.
- Development / holdout split, equity chart, individual trade records, CSV export.
- Parameter sweep on *development-only* data, followed by separately initiated holdout evaluation.

## What this version is NOT

- Not a validated profitable strategy, live-trading bot, tick simulator, or real-time monitoring platform.
- Synthetic market data is for functionality tests ONLY; it has no historical market meaning.
- Alpaca's free IEX feed is a small subset of exchange volume; it is unsuitable for high-confidence execution analysis without validating against consolidated market data.
- The simple 70/30 split is a *first* test, not a definitive walk-forward backtest; repeat use of the holdout will make it contaminated.
- Max drawdown is measured from realized daily/trade equity, not intraday mark-to-market excursions.
- Stop orders do not guarantee maximum losses in real markets.

## Data sourcing and costs

- Streamlit Community Cloud: free personal application hosting (https://docs.streamlit.io/deploy/streamlit-community-cloud)
- Alpaca Market Data: free basic IEX research data, paid consolidated SIP feed (https://docs.alpaca.markets/us/docs/about-market-data-api)
- Historical ETF bars: (https://docs.alpaca.markets/us/reference/stockbars)

A later research-quality upgrade should obtain consolidated trades+quotes (bid/ask, timestamps), improve missing-data checks, calibrate slippage, handle exchange calendars/halts, benchmark vs simple no-trade/buy-and-hold, and use nested walk-forward train/validation/test splits.

## Optional local development

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
streamlit run app.py
```

## Initial roadmap

1. Backtest correctness, systematic bias checks, missing-bar diagnostics.
2. Reliable multi-year consolidated historical 1-minute bars and quote data.
3. Walk-forward research harness with multiple-testing adjustment and transaction-cost sensitivity.
4. Advanced signals: economic calendar, spreads, volatility, time of day, trend/regime detection.
5. Paper trading with brokerage sandbox; independent risk engine and emergency kill switch.
6. **Only after evidence and compliance approval:** consider a strictly separated live-trading service.

*Research and education only; not financial advice.*

## Repository structure

```text
app.py                  # Streamlit website
trade_lab/data.py       # Import, validation, synthetic test data
trade_lab/signals.py    # Four entry signal algorithms
trade_lab/engine.py     # Intraday trade simulation and results
trade_lab/alpaca.py     # Optional historical bar API retrieval
tests/test_engine.py    # Automated correctness checks
requirements.txt        # Hosted app dependencies
.gitignore              # Protects local secrets and temporary files
```

## Historical data quality

When loading bars, the dashboard shows rough full-session bar coverage and the percentage of minute timestamps where QQQ, TQQQ and SQQQ are all present. The count assumes 390-minute sessions; market half-days may make it misleading. The app warns when coverage or timestamp alignment falls below 98%. These are warnings, not proof of sound market data or executable fill prices. For real-money research we still need exchange calendars, quote-based spread estimates, and stricter missing-minute handling.

**Security:** Never commit Alpaca credentials to GitHub. Rotate a key immediately if it appears in a screenshot, log, or chat.