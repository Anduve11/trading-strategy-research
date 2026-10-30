# Weekly Ten-Pick Model

Separate Streamlit research app that loads five years of NFL and FBS schedules, results, historical lines, and available game metadata; compares machine-learning models; and automatically ranks the current slate against today's lines.

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

Never commit secrets. Environment variables with the same names are also supported. Completed CFBD seasons are cached for 30 days, the active season for one day, and current odds for 15 minutes; keys and datasets are not written into the repository.

## What it does

- Loads NFL history from nflverse and FBS schedules, results, opening/closing spreads, conference flags, and venue coordinates from CollegeFootballData (CFBD). CFBD line coverage varies by provider/game.
- Refreshes current NFL and college spreads and totals from The Odds API every 15 minutes; the dashboard can force an immediate refresh.
- Trains and compares twelve candidates: market-only and regularized logistic regression, random forest, extra trees, histogram gradient boosting, classic gradient boosting, and AdaBoost independently for NFL and FBS.
- Builds point-in-time features for recent scoring and ATS form, current ATS streak and cumulative ATS rank, conference/division game status, Elo strength, recent momentum, points allowed, bye returns, rest, estimated travel distance, time-zone change, altitude change, venue dome, and opening-to-current line movement. Features use only earlier results; failed optional CFBD weather, coaches, and per-game box-score endpoints are not requested.
- Selects a model by development-season Brier score, reserves the latest completed season as holdout, calibrates on development out-of-sample predictions, and ranks current games by calibrated cover probability plus cross-model agreement.
- Shows this week's combined slate, ranks the top ten, compares an available college opener with today's line, adds a concise per-game explanation, and displays kickoff forecast and travel context.
- Moves integer spreads half a point away from zero (home/favorite -3 becomes -3.5; underdog +3 becomes +3.5).

## Data and methodology limits

Historical closing lines do not reproduce your pool's 10 a.m. lines. CFBD supplies opening and closing spreads for many college games, but its opener is not guaranteed to be a Tuesday or pool-lock snapshot. nflverse's public schedule history provides NFL closing spreads. The Odds API's historical snapshots are a paid feature; they cover NCAAF and NFL back to June 2020, with 10-minute snapshots through August 2022 and 5-minute snapshots from September 2022 onward. A historical backfill and ongoing lock-time archive require that paid endpoint plus persistent storage. Weather forecasts and historical observations are excluded from model inputs until comparable point-in-time weather archives exist. Predictions are estimates, not a demonstrated edge.

## Timestamped odds archive

The app can retain live bookmaker quotes in Supabase so they survive Streamlit restarts. Run `sports_pool_odds_schema.sql` once in the Supabase SQL Editor, then add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to this Streamlit app's Secrets. Keep the service-role key private. Quotes are deduplicated into five-minute snapshots; capture times from 9:55–10:05 a.m. Mountain are marked as the pool-lock window.

To backfill one Tuesday 10 a.m. Mountain snapshot per week for both leagues, use `scripts/backfill_odds_snapshots.py` with a paid historical-odds key and those Supabase credentials in local environment variables. Example: `python scripts/backfill_odds_snapshots.py --start 2021-01-01 --end 2026-10-30`. The script makes two historical API calls per week and requests spreads only, so check the paid plan's historical quota before running it. Stored snapshots are an auditable line archive; the model should use pool-lock labels only after there is consistent backfill coverage, rather than mixing lock-line results with closing-line results.

## Next increments

1. Add point-in-time NFL odds snapshots for exact 10 a.m. historical backtests if the Odds API plan supports it.
2. Add richer box-score efficiency and player/injury features with historical timestamps.
3. Archive forecast-at-lock weather and evaluate its incremental value against a locked holdout.
4. Evaluate the ten-pick strategy against market, favorite-only, and random baselines over a locked holdout.
