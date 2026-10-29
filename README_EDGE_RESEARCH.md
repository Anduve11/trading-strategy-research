# Expected-profit research, batch v1

Paper simulation only. No brokerage orders. No validated edge is claimed.

The earlier direction classifier predicts the next hour's sign but allows ETF
positions to last until the afternoon. This batch instead learns each ETF's
**net profit for the exact trading window and exit policy being tested**.
That is a new hypothesis, not a promise of better returns.

## Fixed hypotheses before seeing results

- Entries: 10:00, 11:00, 14:30 ET, after the preceding one-minute bar completes.
- Maximum holding times: 30 or 60 minutes.
- Paired target/stop percentages: time-only, .25/.25, .50/.50, .75/.50.
- Models: strongly regularized ridge and shallow Extra Trees regressors trained
  to predict net TQQQ and SQQQ position returns separately.
- Trade only if the better predicted net profit exceeds 0%, .05%, or .10%.
- Features: opening gap normalized by prior volatility; price-path efficiency;
  acceleration/reversal; gap/opening disagreement; VWAP distance; relative
  same-time volume; position within current and prior ranges; lagged returns.
- Macro: prior VIX and Treasury yields/spreads, with .5/1/2 relative weights
  **after standardization**, changing ridge's group penalty. Rescaling tree
  inputs does not change splits, so duplicate tree hypotheses are excluded.
- Optional official Cboe daily VIX9D/VIX ratio, VVIX and changes, and an
  implied/realized volatility ratio. These primarily describe SPX risk, not
  a QQQ options surface. Source: https://www.cboe.com/tradable-products/vix/vix-historical-data/
- Optional FRED dollar/euro, WTI oil and high-yield credit spreads, delayed
  two business days, with no shared forward-filled availability clock.
  Source groups must each cover at least 95% of historical sessions; a
  truncated credit feed does not remove well-covered currency or oil inputs.
- Scheduled early closes remain valid lagged daily-close observations using
  the exchange calendar. A missing intraday bar excludes execution that day
  without erasing 51 days of known closing prices. Missing closing bars still
  invalidate the lag sequence; intraday volume baselines use complete prefixes.
- All included feature sets use identical eligible sessions. Optional source
  failures and missing coverage are reported explicitly in private diagnostics.

## Evaluation and comparison

Expanding fits predict 2021, 2022 and 2023 separately using only earlier years,
with a two-session training embargo. Candidate ranking uses those predictions,
requiring 75 trades overall and at least 10 in each fold, and penalizes fold
instability and drawdown. No 2024+ outcome selects the winning configuration.
The same frozen model fit through 2023 evaluates 2024 and 2025–September 2026.
Those years are already inspected at project level: **not a fresh holdout**.

The experiment registers at most 1,000 configurations (864 with all optional
sources). Every trade uses its own ETF's archived bars, 10% allocation, next
minute entry, conservative stop-first ambiguity, gap-through-stop loss and
5 bps adverse slippage per side. Re-simulating at 10 bps per side stresses the
selected strategy with identical predicted directions. Cash and always-TQQQ/
always-SQQQ within the same intraday window provide diagnostic baselines;
they are not equivalent to multi-year buy-and-hold benchmarks. Five-session
block bootstrap intervals include cash days and are **not** corrected for
selecting among many tests.

The new GitHub workflow runs on source push or manual dispatch. It uses only
existing encrypted Supabase credentials; no new paid service or API keys.
Feature/outcome snapshots, checksums, the top 100 candidates, all tested count,
source errors, and selected results remain private in Supabase. No raw returns
are printed in public Actions logs. Snapshots support independent replay.

Daily downloaded histories are not perfect first-seen vintages. Real quote
spreads, limit-order queues, execution latency and future prospective testing
remain necessary. The news workflow continues separately; this batch includes
neither sentiment nor SEC statements, and does not backfit 2026 holdings weights.
Future work should test scheduled release surprises, historical breadth and
time-varying issuer weights only after their historical availability is verified.
