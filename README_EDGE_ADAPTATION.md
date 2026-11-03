# Past-opportunity edge controllers (paper only)

The observed minute audit reproduced large later semiconductor returns, but
the earlier period remains weak and sometimes lacks complete minute paths.
This batch tests whether a rule's previous completed outcomes can identify
when to pause it or use the opposite ETF. It does not assume that a previously
losing reversal will become profitable, or that inversion is free of costs.

## Declared experiment

Four existing pairs: semiconductors, semiconductors2, smallcap, nasdaq3.
For each use the frozen volume-reversal base at 0.75/1/1.25 volatility units.
Its qualifying event dates are known from lagged price and volume only.

For each base rule and entry delay (0/5/15 minutes), keep a history of the
paired ETFs' actual hypothetical net outcomes, oriented as base/opposite.
At an event, compute mean log growth over the last 5/10/20 completed paired
opportunities at 20bps costs per side. **Emit today's decision before reading
today's outcomes**, then update the history after the session.

- `pause_base`: trade the base direction only when its past mean log growth
  is positive, otherwise cash.
- `choose_orientation`: trade the base or opposite ETF with larger positive
  past log growth; no positive score or a tie means cash.
- `bull_only` further restricts the chosen ETF to the bull fund; inverse
  choices become cash. `both` allows either ETF. No signal means cash.

All qualifying opportunities can update history, including when the controller
stays in cash, because both funds' past endpoints are observable after that
session. A missing pair does not become a zero return and does not update
history. Each decision audit records earlier opportunity count and both scores.

Budget: **4 pairs x 3 thresholds x 3 history windows x 2 modes x 2 direction
restrictions x 3 entry delays = 432 policy configurations**. Nine unfiltered
base/delay controls per pair retain the same endpoint definitions.
Use 100% current equity on qualifying trades, no borrowing, independent paper
accounts per pair. Costs 10/20/50bps per side. There are no stops or targets in
this batch; exit at the last regular-session minute close.

## Data and temporal controls

Use exact sizing source commit
`c599c70dda70af030e7f0627712e30ab4287ee98`, verify its snapshot SHA256 and
reuse the execution-v1 SIP/split minute cache, preserving its hashes. A missing
cache can be downloaded via the same bounded read-only market-data API.
Exact entry and exit bars are required for the actual fund chosen. Intervening
bars are not needed for a time-only endpoint return. No missing prices, paths,
or targets are inferred. Exchange half-days retain their scheduled close.

The controller learns from past opportunities during 2021. Select settings
using 2022-2023 only, at 20bps and full equity, requiring 20 development trades,
five in each year, no missing planned development trade, and a positive mean
daily log-growth score. Sparse samples limit confidence. Report 2024,
2025-September 2026 and combined 2024-September 2026 separately.

If a planned trade lacks an endpoint, it stays a planned trade with unknown
outcome. It is never retroactively turned into cash. Observed-subset results
list missing dates and cannot claim a complete replay. Choices themselves
are emitted without knowing whether today's endpoints will be available.

Retain all rankings, individual results, baseline comparisons, decision logs,
manifest/hash and source provenance privately. A missing or corrupt archive
fails explicitly. Logs print progress only, not prices, predictions or returns.

## Limits and paper-log reliability

This controller was proposed after inspecting historical period differences.
All evaluation years have already been inspected. No fresh historical holdout,
post-selection significance, independent-vendor verification, executable quotes,
intraday drawdown or order-size evidence is claimed. A gate based on past PnL
can lag a changing regime and miss the winning days. No live trading is enabled.

The separate forward ledger retains its frozen candidate and version. Its
signal logic is unchanged by these controller experiments. November 3 has no
pre-entry records in the reviewed data; it is a missed observation, not a
paper performance result. New schedule attempts use 12:17/12:47 UTC weekdays
and 23:17 UTC reconciliation. A heartbeat reports record counts for the
upcoming target and latest started session. Late runs still cannot backfill.

GitHub documents that scheduled jobs can be delayed or dropped, especially at
the start of an hour. This motivates off-hour attempts but does not establish
the cause of this particular missing run:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
