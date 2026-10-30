# Registered strategy-family research

Paper research only. No orders, account changes, or capital transfers.

This batch broadens the signal mechanisms, compares two explicit combination
policies, and saves an auditable registry of every completed trial. It is not
an exhaustive search of all possible strategies. Exhaustive unbounded search
would also make historical selection bias worse.

## Declared budget and data

18 existing ETF pairs x 6 families x 3 multipliers x 2 direction modes = **648
signal hypotheses**. Two additional policies per pair add **36 policy
comparisons**. Always-bull is a benchmark, not a selected candidate.
The previous 216 reversal candidates also receive quarterly and skip-five-best
session sensitivity checks, without reselecting a winner or counting them as
new signal hypotheses.

Each job reads the sizing-v1 replay from the exact source commit
`c599c70dda70af030e7f0627712e30ab4287ee98`, verifies its SHA256, and records its
source run ID. No new vendor request, current-session predictor, or invented
price is needed. All six families use actual observed daily ETF open-close
outcomes, with prior-session predictors. Macro credit, news or accounting
fundamentals are not newly added by this batch.

## Six hypotheses

Each family has multipliers 0.75, 1.0, 1.25 and both-direction/bull-only modes.
Daily proxy volatility is the lagged annualized measure divided by sqrt(252),
floored at 0.1%. Multi-day scaling by sqrt(horizon) is a heuristic, not a claim
of independent daily returns.

| Family | Bull condition; inverse condition mirrors it unless specified |
| --- | --- |
| Five-day reversal | Prior five-day return below minus multiplier times daily volatility times sqrt(5) |
| Volume reversal | Prior one-day loss beyond multiplier, proxy volume shock above 25%, prior close below midpoint of 20-close range; inverse uses prior gain and close above midpoint |
| Market-relative reversal | Prior five-day proxy return minus SPY return below minus multiplier times proxy volatility times sqrt(5); this is not a beta residual |
| Trend continuation | Prior 20-day return above multiplier times volatility times sqrt(20), and price above prior 50-day average |
| Compression breakout | Prior 5/20 volatility ratio below 0.8, 20-close range position at least 0.5 + 0.2 times multiplier, positive five-day return |
| Cross-asset confirmation | Positive five-day move beyond multiplier, positive SPY five-day return, nonpositive average of TLT/GLD five-day returns; inverse requires opposite signs |

## Selection and combination

Frozen family selections use 2021, 2022, 2023 only, at **20bps per side** and
10% allocation. Eligibility requires at least 75 trades total, 10 per year.
Score is worst-fold return + 0.25 mean-fold return - 0.5 worst-fold drawdown
magnitude. A family contributes only when its eligible best score is positive.
The six equal-capital family slots share a **single 10% account budget**;
unused slots stay in cash. Two slots can own bull and inverse funds
simultaneously; each uses its own real ETF outcome and costs, without netting.

The quarterly selector reranks all 36 rules before each quarter using at most
504 earlier eligible observations, excluding the two observations immediately
before the quarter. It needs 250 observations, divides training into four
chronological folds, requires 40 trades total and five in each fold, and uses
the same positive-score gate. It chooses one rule for that quarter or cash.
This is a declared adaptive policy, not a frozen 2023 selection. Previous
evaluation-quarter outcomes may inform later quarters, never the current one.

All individual hypotheses retain results at 10/20bps and 10% allocation.
Policy reports include quarters and removal of the five best winning sessions
as a hindsight sensitivity diagnostic. No later-period metric chooses the
manifest, threshold, family allocation or policy.

## Audit trail and limitations

The private full report includes the manifest/hash, all development scores,
all quarterly rankings, source checksum, full inspected outcomes, and one
deterministic trial ID per signal candidate. IDs hash code SHA, source checksum,
pair, manifest hash and settings. A second checksummed CSV preserves both
policies' daily returns and capital fractions. Failed jobs remain visible in
Actions; missing or corrupt source data fails the job rather than synthesizing
a successful result. Reports and credentials are never printed to Actions logs.

All 2024–September 2026 data have already been inspected. New rules are motivated
by that history. Causal refitting prevents direct temporal leakage but does not
remove repeated-research selection bias. No fresh holdout, corrected p-value,
or validated live edge is claimed. Vendor fills, daily-close-only drawdowns,
surviving-fund universe, benchmark differences, and unmodeled liquidity/size
impact remain material limitations.

## Next expansion gates

1. **Execution evidence:** verify regular-session opening/closing prices and
   executable quotes around entry; record bid/ask spreads, volume and delayed
   entry paths. Stop/target variants need observed intraday paths. Daily OHLC
   alone cannot establish which order filled first.
2. **Prospective paper ledger:** freeze candidate version and record signals
   before entry, with data first-seen times and immutable prediction IDs;
   reconcile intended entries against observed fills. A backfilled prediction
   must never be labeled prospective. Do not recycle October into a holdout
   after repeatedly researching later information.
3. **Distinct data:** options term structure and put/call history; point-in-time
   constituent breadth and earnings; official macro release surprises; SEC
   filings and publication timestamps. Check historical availability, licensing,
   revisions and latency before integrating a source. Current fundamentals
   must not be backfilled as though known historically.
4. **Portfolio layer:** test fixed and causal rotation among distinct underlying
   exposures, deduplicate 2x/3x pairs, and enforce a portfolio capital/risk limit
   with correlated exposure costs. Separate portfolio results from independent
   per-pair account backtests.
5. **Research accounting:** retain losing trials, count policy choices as well
   as signal variants, compare cash and passive baselines under stated costs,
   and reserve truly future observations for paper validation. More tests alone
   do not establish an edge.

These gates are a research backlog; this batch implements the six families,
two per-pair policies, registry, and historical diagnostics. It does not yet
implement new external data feeds, verified execution, a cross-pair portfolio,
or a prospective ledger.
