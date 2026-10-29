# Leveraged ETF comparison, batches v1 and v2

## Batch v2: observed execution windows and interpolation sensitivity

The v1 full-day grid restriction is replaced by **complete observed entry-to-
exit windows** for both bull and bear ETFs. The proxy must have every bar in
the opening-to-decision feature prefix, actual label endpoints and a verified
session close for lag history. Missing unrelated minutes no longer discard
an otherwise usable trade. Missing proxy prices remain missing, never filled.
Each timing/exit policy needs sufficient observations in every required year;
one well-covered clock cannot hide missing data at another clock.

At the user's request, a separate sensitivity analysis linearly interpolates
at most two internal missing minutes per ETF from surrounding closes. Those
rows have explicit flags, zero artificial volume and hypothetical point OHLC.
Entry/exit timestamps, signals and training data are never interpolated.
Future-bracketed interpolation is hindsight-based and cannot establish a
tradable path or stop/limit fill. It is evaluated only after the model is
selected and fitted using observed windows, on separate previously excluded
2024+ dates; results never enter ranking or primary returns. Point OHLC cannot
recover missing high/low extremes. A positive sensitivity result is not alpha.
Immutable original archives are preserved, and both datasets are saved privately.

Batch v2 adds three predeclared pairs: XLK/TECL/TECS (technology), XLF/FAS/FAZ
(financials), and XBI/LABU/LABD (biotech). These are proxy-based experiments;
historical benchmark changes remain a limitation. Issuer catalog:
https://www.direxion.com/all-etfs.
Eight pairs yield a maximum of 4,320 configurations including matched Nasdaq
controls. Expansion is logged in discrete batches: keep all failures and do
not keep adding tickers until a lucky historical winner appears. Any promising
strategy still needs first-seen data/executable-fill checks and prospective
predictions on genuinely new future sessions. No model submits orders.

## Original batch v1 specification (preserved for comparison)

Paper research only; no orders. Extends the same frozen 2019–September 2026
research period to real ETF prices, not simulated leverage multiples.

| Pair | Signal proxy | Daily leverage target |
| --- | --- | --- |
| TQQQ / SQQQ control | QQQ | +3 / -3 |
| QLD / QID | QQQ | +2 / -2 |
| UPRO / SPXU | SPY | +3 / -3 |
| TNA / TZA | IWM | +3 / -3 |
| SOXL / SOXS | SOXX sector proxy | +3 / -3 |

SOXX is not asserted to be the exact historical index of SOXL/SOXS. Proxy
and fund benchmarks have changed; this is an exploratory transfer test. Daily
leverage objectives are not guaranteed multiples over longer holding periods.
Issuer sources: https://www.proshares.com/our-etfs/leveraged-and-inverse/qld,
https://www.proshares.com/our-etfs/leveraged-and-inverse/qid,
https://www.proshares.com/our-etfs/leveraged-and-inverse/upro,
https://www.proshares.com/our-etfs/leveraged-and-inverse/spxu,
https://www.direxion.com/product/daily-small-cap-bull-bear-3x-etfs,
https://www.direxion.com/product/daily-semiconductor-bull-bear-3x-etfs.

The new workflow archives full months using the existing Alpaca SIP credentials
and private Supabase bucket. Original ticker identities remain in the archive;
internal simulator column aliases are explicitly recorded. Immutable monthly
caches resume on retries. No new subscription or credentials are configured.
Two workers maximum with request pacing/backoff limit shared API pressure.

Each candidate pair uses its own unlevered proxy's pre-entry price features and
its real bull/bear minute prices for outcomes. Tests use the existing 24 timing/
exit policies, two feature sets (price / price plus prior-day macro), ridge and
shallow Extra Trees, and three post-cost profit cushions: 288 configurations.
The Nasdaq control is independently tested on **exactly matching dates and
trading windows**, adding 288 configurations for each non-control pair. The
baseline Nasdaq pair is tested once. Batch maximum: 2,592 configurations,
including matched controls; no cross-pair winner is picked on later returns.

Selection uses expanding-window 2021, 2022 and 2023 predictions; 2024 and
2025–September 2026 are already inspected historical diagnostics, never clean
holdouts. Ten percent capital allocation, conservative stop-first bar fills,
and 5/10 bps-per-side adverse slippage are kept fixed. Equal capital is not equal
volatility risk across different markets or leverage levels. Compare net
returns, drawdowns, trade counts, baseline performance and cost sensitivity.

Exact full-session minute grids are required. Thinly traded instruments may
fail the predeclared minimum of 100 eligible sessions in every 2019–2025 year
and 60 in 2026. Report insufficient coverage rather than interpolate prices,
infer fills from a proxy, shorten the test period, or silently drop the bear
fund. Result snapshots, full candidate lists and numeric reports stay private.
No broad-market/sector ETF edge is a validated QQQ forecasting edge by itself.
