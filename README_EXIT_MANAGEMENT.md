# Partial, timed, and trailing exits (paper only)

The past-opportunity controller batch did not establish stable later returns.
This batch tests a distinct question: can an exit reduce losses or lock in
part of a move while leaving some capital exposed to large winning sessions?
No broker orders, fund transfers or account settings are changed.

## Declared scope

Three liquid 3x pairs: SOXL/SOXS, TNA/TZA, TQQQ/SQQQ. USD/SSG is excluded from
this path-sensitive batch because the prior audit found no full minute paths.
Use the frozen 0.75-volatility volume reversal, with both/bull-only restrictions,
entry at 0/5/15 minutes after the regular open, and nine exit policies:

| Policy | Definition |
| --- | --- |
| close | Last regular-session minute close |
| hold30 / hold60 / hold120 | Last minute close of the chosen holding interval, capped at the scheduled session close |
| trail5 / trail8 | Trailing stop 5% or 8% below the running high, starting at the adverse entry fill |
| trail2sigma | Trail twice lagged proxy daily volatility times stated ETF leverage, clipped to 2%-12% |
| half3 / half6 | Sell half at a fixed 3% or 6% gain; hold the remaining half until close |

Budget: **3 pairs x 2 direction restrictions x 3 entry times x 9 exits = 162
configurations**. Full current equity is used on entry. A half-sale's cash stays
idle and is never reinvested during the trade. The two sale proceeds are
weighted halves of the same initial position, with adverse costs on each fill.
Report costs 10/20/50bps per side. All three costs use a common known-outcome
cohort; if any cost path is unknown, that trade remains missing for the replay.

## Intrabar uncertainty and missing data

Minute OHLC does not tell whether the high or low happened first. For trailing
stops, track the alive position and every compatible earlier stop outcome.
If the current bar's open gaps below an already-active stop, use the open.
If its low crosses a known stop, include that lower compatible exit. If a
raised trailing stop could have been touched only under one OHLC ordering,
retain both the stopped and surviving possibilities. At the end, take the
lowest compatible proceeds. These are **conservative return bounds**, not
measured or guaranteed executable stop fills. Report ambiguity counts.

A missing minute while an alive path could still trade makes its outcome
unknown. A known stop before a later missing bar can remain observed. Timed
exits need only exact entry/exit endpoints. A fixed half-target with an observed
touch fixes its modeled sale price even if other minutes are absent; without
a known touch, any missing bar leaves the partial-sale outcome unknown. No
price or path is interpolated.

Target touches still do not prove a limit order filled; queue position, bid/ask,
spread, auction eligibility, market impact, commissions beyond modeled adverse
prices and taxes remain unverified. Minute-close/daily drawdowns do not measure
all intraday losses. Proxy volatility times stated ETF leverage is approximate.

## Selection, controls and provenance

Use the immutable sizing snapshot from commit
`c599c70dda70af030e7f0627712e30ab4287ee98`, verify its SHA256 and reuse the
execution-v1 SIP/split cache with source hashes. Respect scheduled half-days.
Hold the same qualifying signals; emit no extra entries or leverage.

Select only on 2021-2023 mean daily full-equity log growth at 20bps, requiring
40 trades, five each year, complete planned-trade coverage and positive score.
Retain all failures and unknown dates. Report 2024, 2025-September 2026, and
combined 2024-September 2026. For each exit also retain the candidate and close
control on the exact intersection of known trade dates, with explicit coverage
labels. Do not compare unequal cohorts as if the exit alone caused a change.

All evaluation history has already been inspected and motivated this research.
No fresh holdout, statistical significance or validated edge is claimed.
Private artifacts preserve rankings, observed returns, ambiguity, full results,
manifest/hash and source lineage. All pair accounts are independent paper tests.

## Forward recording version 2

The existing logger's midnight-plus-90-minute requirement blocked evening
runs that actually executed, while morning triggers have not produced records.
Version 2 accepts the prior completed trading session as observed after 21:30
New York, adds a 02:47 UTC Tuesday-Saturday capture attempt, and keeps premarket
retries. It freezes first-seen inputs rather than claiming final vendor values.
The request end is capped before current time to remain compatible with delayed
SIP access. Activation is November 5, 2026, with a distinct object namespace.
The November 3-4 gaps are not erased or backfilled. Version 1 has no measured
prospective performance. Version 2 also has none until an actual pre-entry
record succeeds and later reconciles.

Alpaca's documentation distinguishes minute/daily aggregation rules and
extended-hours conditions; no guarantee of first-seen daily finality follows:
https://docs.alpaca.markets/us/docs/market-data-faq
