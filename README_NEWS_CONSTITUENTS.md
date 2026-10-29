# Market Edge: constituent news & financial filings research (v0.9)

**Paper simulation only. No live orders. No model has demonstrated a reproducible edge.**

## What is implemented

- A monthly, resumable **news-derived** archive based on the existing Alpaca News API keys. It pulls published article metadata for a *fixed research watchlist* and stores only numerical daily features (counts and predeclared headline keyword polarity) in the existing private `market-edge-history` bucket. It does not republish full article text or save news-provider API keys.
- Four model variants on identical eligible dates: (1) price-only; (2) price + prior-day VIX/yields; (3) price + news-derived features; (4) price + macro + news. Each trains on 2019–2022, selects model and abstention threshold in 2023, evaluates in 2024, and reports 2025–Sep 2026 as *previously inspected* diagnostics.
- Optional SEC XBRL historical financial filings via the official SEC EDGAR API and an identifying User-Agent. Aggregates latest *filed-before-trade* issuer profit margins and reporting activity across an exploratory static basket (two additional model variants).
- Private numeric model summaries in `public.market_edge_research_runs`. Public Streamlit app is not given the news API keys or research results.

## Very important historical caveat

The company watchlist is the **top ten security positions of QQQ reported by Invesco as of October 16, 2026**, not a backfilled list of the historical top ten: NVDA, AAPL, MSFT, MU, AMZN, AMD, META, GOOGL, TSLA, GOOG. It represents **nine distinct issuers** because GOOGL and GOOG belong to the same company. Source: https://www.invesco.com/us/en/financial-products/etfs/invesco-qqq-trust-series-1.html

Selection from a 2026 holdings list **creates survivorship/look-ahead bias** for 2019–2025 historical analysis even if each article/filing timestamp is handled carefully. Consequently, these tests are **diagnostic feature experiments**, not defensible historical proof of alpha. We must subsequently procure holdings snapshots that were actually published before each test date, *including their publication timestamps* and historical constituent identifiers. Do not apply 2026 weights in 2019.

**Headline risk:** the vendor's `created_at` is treated as an article first-created time with a 5-minute delay, but we have not established whether that is exactly when a real trader first saw the article. Results are retrospective until vendor first-seen latency is verified. The lexicon scorer is transparent but rudimentary—**not FinBERT, not an LLM, not calibrated sentiment probability**. Latest-available companyfacts are filtered by SEC filing dates; they are not a perfect archival real-time vintage.

## Running this research

Use the repository's [News and constituent research (paper-only)](https://github.com/Anduve11/trading-strategy-research/actions/workflows/news_constituents.yml) workflow. On push to the relevant source files, or when manually dispatched, it:

1. Parallelizes **2019–2020 / 2021–2022 / 2023–2024 / 2025–2026** news collection (maximum 2 API requests per second per worker, moderate shared API limits), caching one compressed derived monthly file at `alpaca/sip/news-derived-lexicon-v1/static-2026-basket/YYYY-MM.csv.gz`.
2. Resumes from previously saved monthly features if interrupted. A partial month is never saved.
3. After all archive workers succeed, trains/evaluates the four model variants and persists results in the existing private Supabase table.
4. If `SEC_USER_AGENT` is set in GitHub Actions Secrets, it additionally fetches and tests historical fundamental factors; otherwise this optional layer is skipped, and reports clearly say so.

The four GitHub repository secrets `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `ALPACA_KEY_ID`, and `ALPACA_SECRET_KEY` are **already configured by the account owner**. **Do not paste these into chat or commit them.**

### Optional SEC filing data

The SEC requires a truthful identifying contact in the HTTP User-Agent. If you want the SEC filing comparison activated, create an extra GitHub Actions repository secret named `SEC_USER_AGENT`, formatted approximately as `MarketEdgeResearch/0.9 your-real-contact@example.com` (use a valid address you control). No secrets are required for basic news analysis. This is *not* an Alpaca API credential. The SEC's JSON API provides filing dates and reported financial observations, not complete point-in-time historical QQQ constituent weights. We do not turn these values into live trading decisions.

## Research discipline

- A historical return above 0 on one period is **not** proof of an edge. All results incorporate the prototype simulator's assumed fill, slippage, stops, and 10%-of-account allocation and must be stress-tested with market quotes, bad fill scenarios, corporate actions, and execution delays.
- 2025–2026 history has already been inspected many times in this project, so treat it as diagnostics, not a fresh untouched test.
- We must keep genuinely new future data prospective (time-stamped predictions before outcomes), and log failed hypotheses, selection attempts, and the total number of tests to avoid multiple-testing bias.
- The model may pick **cash/no trade** frequently. We're looking for repeatable risk-adjusted P&L, not a trade every day.

Future work: obtain historical N-PORT/Invesco constituent snapshots, SEC earnings announcement timestamps, scheduled CPI/FOMC/job-release features, price/volume for major underlying constituents, independently scored FinBERT headlines, and minute quotes to assess realistic execution.