# Daily regime, growth, and downside models (paper only)

The user requested continued model/factor research with 100% of current equity
on each qualifying trade. This experiment adds a distinct daily learning task
and imports official Cboe volatility-index context into the daily experiment.
No order API, broker setting or capital transfer is involved.

## New daily model comparisons

- **Ridge log growth:** scaled regularized regression of actual ETF log returns,
  an interpretable baseline for the new full-equity objective.
- **Histogram gradient boosting log growth:** learns nonlinear relationships
  and interactions, targeting expected log growth at 20bps costs per side.
- **Quantile gradient boosting:** separately estimates the median and 25th
  percentile of ETF log returns. Require median above the chosen cushion and
  q25 above -0.03. These are conditional distribution estimates, not guaranteed
  loss limits. If quantiles cross, lower q25 conservatively to the median.

Models fit each bull/inverse ETF separately except multi-output ridge. Training
uses actual log1p(net returns), without clipping labels. Evaluation returns are
never clipped. Early stopping is disabled; every scaler and fitted model sees
training rows only. Tree settings are fixed: 60 iterations, 7 leaves, 60 minimum
rows per leaf, learning rate 0.05 and L2 regularization 5. Ridge alpha is 100.

## New daily factors and fair ablation

The existing daily factors include lagged returns, trend, volatility, price
location, volume behavior, cross-market moves, VIX, Treasury yields and schedule.
Nine interaction/regime features add normalized relative strength, volume/return
interaction, gap/session disagreement, bond/gold defensive flow, trend/volatility
interaction, fear/volume interaction, downside volatility, return autocorrelation,
and correlation with SPY. Rolling features count eligible observations and use
already-lagged inputs. They never read entry-day prices or volumes.

The second feature group adds Cboe **VIX9D/VIX, VVIX, five-observation VVIX change,
and implied/realized volatility ratio**. These option-index factors were explored
in earlier intraday research; this batch adds them to the daily model comparison.
They are not options chains, dealer gamma, or order-flow measures.

Official source histories:

- https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv
- https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv
- https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv
- Model API: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html

Both feature groups use the **same complete-case sample**. Option observations
must be dated strictly before the trade date and no older than seven calendar
days. Histories are retrospective, not archived first-seen vintages; real
publication latency and revisions remain unverified. No revised economic
release is asserted to have been available in real time.

## Declared budget and temporal controls

18 pairs x 3 models x 2 feature groups x 2 log-return cushions (0 and 0.001) x
2 decision filters x 2 direction restrictions = **864 candidates**. Direct
decisions choose the higher forecast if eligible, with ties in cash. Volume
confirmation instead tests the forecast on the ETF selected by the prior
0.75-volatility volume-reversal rule. Bull-only mode restricts entries from
those same decisions; it does not reinterpret a rejected inverse as a bull.

Refit before each quarter from 2021 onward on at most 756 earlier eligible
observations, two-observation embargo, 400 training rows minimum. Quarterly
predictions from 2021-2023 determine selection using realized full-equity mean
daily log growth at **20bps costs**. Require 40 development trades and five
each year, and a positive score; otherwise the selected policy remains cash.
This allows sparse signals and must not be treated as strong statistical proof.
No 2024-2026 result chooses model settings or the selected configuration.

Report all candidates at full equity, costs 10/20/50bps, for development, 2024,
2025-September 2026 and combined 2024-September 2026. The selected configuration
and matched-date unfiltered-volume/daily-bull controls also get quarter and
skip-best-winning-session diagnostics. Daily-bull is an open-close turnover
control, not a buy-and-hold investment benchmark. Each pair is an independent
paper account; no cross-pair portfolio return is implied.

## Reproducibility and limitations

Use immutable adaptive source commit
`980a62b51881793ef87a29b29f61fb18f0bb7e4e`. Verify its private snapshot hash.
Prepare Cboe histories once per workflow attempt, trim to 2018-September 2026,
save raw-source checksums, retrieval time and compressed-payload SHA256.
Dependent pair jobs consume that exact snapshot. Private artifacts preserve
matched feature rows, every forecast/signal, quarterly fit dates, all candidate
scores and results, manifest/hash and source lineage. Output is checked for
nonfinite JSON. Missing/corrupt data fails explicitly; it is never filled with
fabricated prices or silently replaced with a different source.

The rules, factor families and learning objectives were motivated by already
inspected history. Even causal refitting and matched samples do not create a
fresh holdout or remove repeated-research selection bias. Auction prices,
executable spreads, intraday drawdowns, dollar-size market impact, taxes and
prospective predictions are still unverified. This batch adds no accounting
fundamentals, new earnings feed, SEC history, options chain or new sentiment
engine. The existing headline lexicon has not established a useful edge.

Run `python scripts/regime_model_research.py --prepare --prefix PATH`, then
`python scripts/regime_model_research.py --pair semiconductors --prefix PATH`
with the existing private archive credentials. The GitHub workflow runs tests
before preparation and retains failed jobs. Logs contain progress only, never
credentials, forecasts or numeric research results.
