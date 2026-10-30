# Weekly Ten-Pick Model

Separate Streamlit research app that loads 2020–current NFL and FBS schedules, results, historical lines, and available game metadata; compares machine-learning models; and automatically ranks the current slate against current lines.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run sports_pool_app.py
```

Optional Streamlit secrets in `.streamlit/secrets.toml`:

```toml
CFBD_API_KEY = "your CollegeFootballData token"
ODDS_API_KEY = "your The Odds API key"
```

Never commit secrets. Environment variables with the same names are also supported. The 2020–2025 CFBD FBS schedule and line history is stored as compressed CSVs in `data/sports_pool/`; the current college season and lines refresh from CFBD once per day. NFL schedule history comes from nflverse and current NFL lines refresh from The Odds API once per day when its key is configured. No weekly file upload is needed. The historical bundle contains exporter schedule rows joined to bookmaker quotes by CFBD game ID.

## What it does

- Loads NFL history from nflverse and FBS schedules/results plus per-provider college opening/closing lines from the bundled CFBD exporter data. CFBD line coverage varies by provider/game; the bundle preserves provider quotes as well as a per-game median.
- Fetches current college schedules and spreads from CFBD and current NFL spreads/totals from The Odds API, caches live quotes for up to one day between app reruns, and offers a manual immediate refresh. The Odds API is only queried for NFL, reducing use of its monthly quota.
- Trains and compares twelve candidates: market-only and regularized logistic regression, random forest, extra trees, histogram gradient boosting, classic gradient boosting, and AdaBoost independently for NFL and FBS.
- Builds point-in-time features for recent scoring and ATS form, current ATS streak and cumulative ATS rank, conference/division game status, Elo strength, recent momentum, points allowed, bye returns, rest, estimated travel distance, time-zone change, altitude change, venue dome, and opening-to-current line movement. Features use only earlier results; failed optional CFBD weather, coaches, and per-game box-score endpoints are not requested.
- Selects a model by development-season Brier score, reserves the latest completed season as holdout, calibrates on development out-of-sample predictions, and ranks current games by calibrated cover probability plus cross-model agreement.
- Shows this week's combined slate, ranks the top ten, compares an available college opener with today's line, adds a concise per-game explanation, and displays kickoff forecast and travel context.
- Moves integer spreads half a point away from zero (home/favorite -3 becomes -3.5; underdog +3 becomes +3.5).

## Data and methodology limits

Historical closing lines do not reproduce your pool's 10 a.m. lines. CFBD supplies opening and closing spreads for many college games, but its opener is not guaranteed to be a Tuesday or pool-lock snapshot. nflverse's public schedule history provides NFL closing spreads. The Odds API's historical snapshots are a paid feature; they cover NCAAF and NFL back to June 2020. The app can update current college lines from CFBD and NFL lines from the existing Odds API key without weekly uploads, but exact 10 a.m. historical lock lines still require prospective timestamped collection. Weather forecasts and historical observations are excluded from model inputs until comparable point-in-time weather archives exist. Predictions are estimates, not a demonstrated edge.

## Timestamped odds archive

The app can retain live bookmaker quotes in Supabase so they survive Streamlit restarts. Run `sports_pool_odds_schema.sql` once in the Supabase SQL Editor, then add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to this Streamlit app's Secrets. Keep the service-role key private. Quotes are deduplicated into five-minute snapshots; capture times from 9:55–10:05 a.m. Mountain are marked as the pool-lock window.

The GitHub Actions workflow `Archive weekly pool lines` requests NFL and FBS odds every Tuesday at 10 a.m. Mountain and stores a timestamped snapshot without requiring Streamlit to be open. Add `ODDS_API_KEY`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` under GitHub repository Settings → Secrets and variables → Actions. The workflow runs at both possible UTC times for daylight/standard time and skips the off-window run. GitHub may delay scheduled jobs; the stored capture timestamp shows the actual time. GitHub only runs scheduled workflows from the repository's default branch, so merge this workflow there to enable the weekly schedule; on `sports-pool-lab`, use **Actions → Archive weekly pool lines → Run workflow** for a manual capture.

To backfill one Tuesday 10 a.m. Mountain snapshot per week for both leagues, use `scripts/backfill_odds_snapshots.py` with a paid historical-odds key and those Supabase credentials in local environment variables. Example: `python scripts/backfill_odds_snapshots.py --start 2021-01-01 --end 2026-10-30`. The script makes two historical API calls per week and requests spreads only, so check the paid plan's historical quota before running it. Stored snapshots are an auditable line archive; the model should use pool-lock labels only after there is consistent backfill coverage, rather than mixing lock-line results with closing-line results.

## Next increments

1. Add point-in-time NFL odds snapshots for exact 10 a.m. historical backtests if a free or affordable source supports it.
2. Add richer box-score efficiency and player/injury features with historical timestamps.
3. Archive forecast-at-lock weather and evaluate its incremental value against a locked holdout.
4. Evaluate the ten-pick strategy against market, favorite-only, and random baselines over a locked holdout.
