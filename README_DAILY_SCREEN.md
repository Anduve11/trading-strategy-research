# Broad daily ETF screen v1

Adds a distinct **daily-bar open-to-close simulation** to the intraday research.
It is not a repair of missing minute prices. Vendor daily opens/closes are
hypothetical fills: exact session/auction definitions, trade size, quotes and
latency need validation. Daily OHLC never establishes intraday stop/target fills.
No orders are submitted.

18 pairs (36 leveraged ETFs): the original eight, plus SSO/SDS, DDM/DXD,
UDOW/SDOW, UWM/TWM, UYG/SKF, URE/SRS, USD/SSG, UGL/GLL, UBT/TBT and TMF/TMV.
Proxies are broad-market/sector ETFs, not necessarily identical to historical
fund benchmarks; GLD differs from gold futures exposure. Current survivor
selection is a limitation. Issuer catalogs:
https://www.proshares.com/our-etfs/find-leveraged-and-inverse-etfs
https://www.direxion.com/all-etfs

Six strictly lagged price features and an optional prior-day macro set use
ridge or shallow Extra Trees expected-profit models with three trade cushions.
12 configurations per pair, 216 maximum. Fits expand through 2020/2021/2022
to predict 2021/2022/2023 with a two-session embargo. Those predictions select
the configuration; all 2024–September 2026 reports are already-inspected
historical diagnostics. No cross-pair winner is selected on later returns.

Uses actual split-adjusted daily ETF bars, 2018 warm-up, 2019–September 2026
research dates, 10% account allocation and 5/10/20bps adverse slippage per side.
Missing prices remain missing. Compare drawdowns, same-window always-bull/
always-bear controls, cash and cost sensitivity. Equal capital is not equal
volatility risk. Daily results are not directly comparable to the intraday batch.

Immutable real-ticker daily caches, replay features/outcomes and all ranked
configurations are saved privately alongside existing research reports. The
workflow uses existing encrypted credentials and two workers at most. All
failed/insufficient-data results are retained. No validated edge or future
profitability is claimed; prospective evaluation remains necessary.
