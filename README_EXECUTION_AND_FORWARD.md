# Observed execution refinements and prospective paper signals

User preference: use **100% of current account equity on each qualifying trade**
in research. All jobs here are paper only. They contain only market-data reads
and private archive/report writes, with no order or broker-account mutation API.
Each pair and timing scenario is a separate hypothetical account.

The preceding historical searches found large later-period winners, but earlier
losses, sensitivity to a few days, and hypothetical vendor fills still prevent a
validated-edge claim. This change investigates execution assumptions and starts
a prospective record instead of only expanding the historical parameter count.

## Historical execution batch

Four pairs: SOXL/SOXS, USD/SSG, TNA/TZA, TQQQ/SQQQ. Keep the existing frozen
volume-reversal signals, thresholds 0.75/1/1.25 and both/bull-only restrictions.
Enter at the regular-session open or after 1, 5 or 15 minutes. Compare time-only
exit at the last regular minute close against target/stop percentages 2/2,
4/2 and 6/3. Budget: **4 x 6 x 4 x 4 = 384 configurations**. All allocations
are full current equity, costs 10/20/50bps per side, no account borrowing.

Read the exact sizing source commit
`c599c70dda70af030e7f0627712e30ab4287ee98` and verify snapshot SHA256. Fetch
SIP split-adjusted 1-minute bars only on dates on which any frozen signal trades;
cache actual tickers, request parameters, retrieval timestamp and payload hash.
No secrets are written to provenance. Pagination follows all symbols, since the
API sorts by symbol before timestamp. Schedule comes from exchange-calendars,
including official half-days. Do not interpolate any prices or sessions.

An endpoint audit compares the daily-label net return with the exact regular
first-open/last-minute-close net return. Save price levels and differences even
if the rest of the path is incomplete, including the largest daily winners.
Daily bars and regular-session minutes can aggregate different trade intervals;
a discrepancy is evidence to investigate, not automatic proof of a bad price.
This is **same-vendor cross-resolution validation**, not independent-vendor,
auction, executable-quote, or size-impact verification.

Path-dependent strategy replay requires every scheduled minute for the actual
ETF traded. All delays/exits share that complete-path cohort for a signal.
Stop-first when target and stop both touch; stops can gap through, targets use
conservative touched-price assumptions. These remain hypothetical order fills.
Minute-low adverse excursion is recorded per trade, without claiming to infer
exact account-wide intraday drawdown from OHLC ordering.

Missing trade outcomes are never replaced with cash or prices. Preserve them
as missing dates and label any reported partial result
`INCOMPLETE_OBSERVED_SUBSET_ONLY`. A complete replay is separately labeled.
Any missing development trade makes that configuration ineligible for selection.
Rank using full-equity mean daily log growth at 20bps during 2021-2023 only;
40 trades total, five each year, positive score required. Report 2024,
2025-September 2026 and combined 2024-September 2026 separately. Those periods
have already been inspected; no fresh historical holdout is claimed.

## Prospective paper ledger

Freeze `volume_reversal_forward_v1`: prior proxy return beyond 0.75 daily
volatility, proxy volume above its trailing 20-session mean by more than 25%,
prior close below/above midpoint of its trailing 20-close range for bull/inverse.
Use actual prior data and a 0.1% daily volatility floor. Track the same four
pairs with two fixed timing scenarios, 0/5-minute entry and last regular-minute
close. Cash is explicitly recorded when no signal qualifies. The candidate was
chosen after inspecting history and starts **unvalidated**.

Workflow `.github/workflows/paper_signal_ledger.yml` runs weekdays at 13:00 UTC,
before the US regular open in both standard and daylight time. GitHub schedules
can run late; the timestamp/deadline check, not the cron label, determines
prospective eligibility. It also runs on an explicit dispatch or relevant push.

Choose the next exchange session at least five minutes after current time. If
the immediately preceding daily bar has not passed New York midnight plus a
90-minute finality buffer, skip prediction creation. Never substitute an older
bar, use an unfinished current-day bar, or backfill a past prediction. Demand
all 60 scheduled historical proxy sessions with no extra dates or missing rows.
All features use that completed history; record cash when range/volume gives
no usable signal. The finality buffer is an operational convention, not a
guarantee that the vendor will never revise a bar.

Save one prediction per strategy version/pair/target date to a private path with
POST-only writes. Existing records are left unchanged. Records include created
time, source first-seen time, source snapshot/hash, code SHA, manifest/hash,
prediction ID, prior session, target open/close, direction and allocation.
Creation after the deadline is rejected. A next-session source snapshot that
changes the expected target during a delayed request is rejected as well.

Later runs reconcile only existing pre-entry records after that session closes
plus 30 minutes, using exact 0/5-minute and closing endpoints. A missing endpoint
produces a retained incomplete attempt and no invented return. Completed
outcomes are written separately with the prediction hash and observed-data
snapshot/hash; they never overwrite a prediction. Returns are **observed-endpoint
hypothetical fills**, not executed trades or evidence of executable spreads.
No-signal outcomes are recorded as cash, not missing data. Forward performance
must begin only with successfully stored pre-entry signals. Nothing in the
historical archive is relabeled prospective.

Private reports use model types `execution_refinement_v1` and
`paper_signal_ledger_v1`. Reports, predictions, prices and credentials are never
printed in Actions logs. Source/checksum/authentication failures fail explicitly.
The recurring historical weekly review still exists; it is separate from this
new weekday pre-entry ledger. No actual trading is enabled by either workflow.

Primary API documentation:

- https://docs.alpaca.markets/us/reference/stockbars
- https://docs.alpaca.markets/us/docs/market-data-faq
- https://alpaca.markets/learn/stock-minute-bars
