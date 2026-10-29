# Leveraged ETF comparison, batch v1

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
