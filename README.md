# Market Edge v0.5 — Intraday QQQ / TQQQ / SQQQ Research

[**Open the Streamlit application**](https://trading-strategy-research-m28fia7syvi6jd5ganw6ch.streamlit.app/) · [Source code](https://github.com/Anduve11/trading-strategy-research)

**Research only. No live brokerage orders, no background trading, and no evidence of profitable signals yet.** The app simulates buying TQQQ on bullish QQQ signals and SQQQ on bearish signals, subject to stops, profit targets, costs, position allocation, and mandatory same-day exit.

## What v0.4 adds

- **One-time historical archive** in a **private Supabase Storage bucket**. Monthly compressed CSV files, keyed by source/feed/adjustment/symbols/year-month. The archive **reuses previously saved months** on future experiments. Unfinished downloads are resumable because completed months are already saved.
- **Dedicated archival job**: `Archive missing historical months — no backtest` populates the archive without running strategy simulations. There is no automatic daily fetch yet; rerun to add completed months.
- **First market-regime study**: previous-session 50-day QQQ moving-average trend (±1% neutral zone) and 20-day realized volatility (<25% / ≥25% annualized). No current-day or future closing prices are used for classification. Reports show each strategy's regime results on development data only.
- **Multi-year 16-candidate research engine** is unchanged in trading logic. The archive accelerates repeated experiments; it does not claim better predictions or improved returns.
- The **Multi-year strategy laboratory** works even when a short-period Alpaca download has not been completed.

The classification is a **descriptive research feature, not a regime-based trading rule yet**. Macro announcements, VIX, options, news sentiment, fundamentals, market breadth, and AI are **not integrated yet**. We must establish clean baseline results before expanding the feature set.

## Deploy and test

1. The app is automatically deployed from `main` on GitHub to Streamlit Community Cloud.
2. The synthetic demo exercises the UI; its results have **no real-market meaning**.
3. For actual backtests, choose `Alpaca historical ETF data`, the historical **SIP** feed, and enter your *rotated* paper-market-data credentials into the masked fields. Do not post keys in screenshots, chats or GitHub.
4. Without cloud storage, studies still run but redownload all missing price history each time. For permanent storage, follow the instructions below.

## One-time setup: private Supabase historical archive

**Supabase and Streamlit secrets must be configured by the account owner. Do not send their keys in chat or commit them to GitHub.**

1. Create a project in [Supabase](https://supabase.com/dashboard). In **Storage**, create a bucket exactly named `market-edge-history` and set it to **Private**. Do not create a public bucket.
2. In Supabase **Project Settings → API Keys**, create/copy a **server-side Secret key** (`sb_secret_...`). Do **not** use a browser-safe publishable key. Secret keys bypass Row Level Security; keep them private. A separately scoped backend service would provide stronger production isolation than a general project secret.
3. Open [Streamlit Community Cloud](https://share.streamlit.io). Select the existing Market Edge app → `...` → **Settings** → **Secrets**. Add the following TOML with **your own real values**, then save:

   ```toml
   SUPABASE_URL = "https://YOURPROJECT.supabase.co"
   SUPABASE_SECRET_KEY = "sb_secret_YOUR_PRIVATE_KEY"
   SUPABASE_BUCKET = "market-edge-history"
   MARKET_EDGE_ADMIN_PASSWORD = "CHOOSE_A_LONG_UNIQUE_PASSPHRASE"
   ```

   Use a unique strong passphrase (minimum 12 characters) saved to your password manager. These values go **only** into the Streamlit Secrets page, not into the Python source or repository.
4. In the app, select Alpaca as the source. Expand **Multi-year strategy laboratory**. Enter the research admin passphrase in its **masked** field. Check **Use reusable Supabase archive**. The stored server-side key is used only after the passphrase matches.
5. For a first download choose 2024–2026 and **Archive missing historical months — no backtest**. Later choose 2019–2026 and repeat. Each completed month is saved individually. If hosting interrupts the task, run it again: stored months will be reused.
6. Finally, choose **Run multi-year backtest — no real orders**. The model reads from cached monthly files, downloads missing months if needed, and exports research results. Continue using the same archived history for later experiments without pulling it all again.

**Storage details:** monthly regular-session QQQ, TQQQ, SQQQ minute bars are compressed with gzip. The `alpaca/sip/split/1min` namespace separates this particular price history from other providers or adjustments. The current code keeps archives **immutable**; it will not silently replace existing months. Future ticker splits and revised historical bars may require an explicit, audited refresh or archive version change. Keep a backup: free-tier storage is not a substitute for an independent long-term backup.

**Security:** This is a research prototype hosted at a publicly reachable URL. The admin passphrase gates archival read/write operations, but a production system should use stronger authentication and restricted backend credentials. Never include API secrets in screenshots or copy them into public GitHub. Rotate any exposed keys.

## Our baseline trading simulation

Four entry signals: **Momentum + VWAP**, **Opening range breakout**, **EMA trend**, **VWAP reversion**. Four predeclared exit pairs: `(target 1%, stop 1%)`, `(1.5%, 1%)`, `(2%, 1.5%)`, `(3%, 2%)` → **16 configurations**. One trade at most per session, next-minute open entry, conservative stop-first when both levels are hit within a bar, exit before the regular session ends. Costs and allocation are adjustable. No live orders. Intrabar dynamics, bid/ask quotes, liquidity and market impact remain unmodeled.

Example research partition for 2019–2026: **2019–2023 development**, **2024 validation**, and **2025–2026 final holdout**. Only development chooses a candidate; the final holdout should remain untouched for subsequent tuning. Costs, regime thresholds, and execution assumptions must be frozen before interpreting holdout results.

### Regime methodology

At the *start* of each historical session, using only **prior completed daily QQQ closing prices**:

- Compare the prior close with the SMA of the last **50** completed sessions: >1% above = uptrend, >1% below = downtrend, otherwise sideways.
- Compute standard deviation of the last **20** close-to-close log returns, annualize by √252; ≥25% = high-volatility regime.
- First 50 sessions are **insufficient history** and excluded from the displayed conditional analysis.
- Labels are assigned to that session's simulated trade. They are **not yet used to choose or block trades**.

This avoids obvious forward-looking leakage, but does **not** prove causal predictability or provide a trading advantage. Very small regime groups are flagged as exploratory.

## Research limitations

- Alpaca's **historical SIP bars** are consolidated trade bars, not full order-book quotes or guaranteed executable fills; free real-time data is different.
- Dataset quality warnings assume 390-minute days; special sessions require a proper market calendar and comprehensive adjustment for missing minutes. This is a **research-quality gap** before considering live orders.
- Free Streamlit hosting can restart, time out or run out of resources; monthly cloud archive objects persist once saved, but the in-progress study and its summary don't automatically survive restarting the app.
- Alpaca data availability, usage quotas and storage pricing should be reviewed before a long archival run. We have not completed the 2019–2026 import on your account yet.
- Seek compliance clearance before enabling any automated trading, especially with leveraged ETFs and workplace trading restrictions.

## Development

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
streamlit run app.py
```

`trade_lab/archive.py` is the private cloud archive; `trade_lab/regimes.py` is the leak-resistant regime classifier; `trade_lab/research.py` orchestrates multi-year tests; `trade_lab/engine.py` is the execution simulator; `trade_lab/alpaca.py` loads consolidated historical bars. Streamlit app secrets are intentionally never committed.


## Archive-only research and annual results (v0.5)

After creating a complete Supabase monthly archive, select **Alpaca historical ETF data** as source without entering any Alpaca credentials. Unlock the archive using your research admin passphrase, select **Use reusable Supabase archive** and **Use archived data ONLY**, choose first year 2019 and last year 2026, then click **Run multi-year backtest**. This mode makes no Alpaca API requests and fails clearly on any missing archived month. Only the server reads private compressed archive objects.

The study simulates all 16 *predeclared* candidate strategies, selects a configuration from development years, then displays that configuration's development, validation, and final historical holdout. It now shows yearly returns, starting/ending balance, trade counts, drawdowns, and the selected strategy's daily realized-equity curve. Export yearly results and the equity curve as CSV; the saved price archive is not modified during a read-only backtest.

**Important:** These results are *bar-based research estimates*, not audited profits. The model currently has four simple technical indicators and a descriptive market-regime table; it does **not** use fundamentals, news sentiment, real quote spreads, or trade execution data. We must validate the full archive for exchange-calendar and split-adjustment anomalies, compare against proper benchmarks, and perform prospective paper trading before enabling live trading.