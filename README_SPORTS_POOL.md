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

- Loads NFL history from nflverse and FBS history, opening/closing spreads, game weather, coaches, and stadium coordinates from CollegeFootballData (CFBD). CFBD line coverage begins in 2013 and varies by provider/game.
- Refreshes current NFL and college spreads and totals from The Odds API every 15 minutes; the dashboard can force an immediate refresh.
- Trains and compares twelve candidates: market-only and regularized logistic regression, random forest, extra trees, histogram gradient boosting, classic gradient boosting, and AdaBoost independently for NFL and FBS.
- Builds point-in-time features for last-two/last-three scoring and ATS form, prior-game box-score efficiency when available, Elo strength, recent momentum, points allowed, bye returns, rest, coach record/continuity, estimated travel distance, time-zone change, altitude change, venue dome, and line movement. Features use only prior completed games.
- Selects a model by development-season Brier score, reserves the latest completed season as holdout, calibrates on development out-of-sample predictions, and ranks current games by calibrated cover probability plus cross-model agreement.
- Shows this week's slate, ranks the top ten, compares an available opener with today's line, adds a concise per-game explanation, and displays kickoff weather forecasts, venue, coaches, and travel context.
- Moves integer spreads half a point away from zero (home/favorite -3 becomes -3.5; underdog +3 becomes +3.5).

## Data and methodology limits

Historical close lines do not reproduce your pool's 10 a.m. lines. CFBD provides opening spreads for college games when available; nflverse's public schedule history provides NFL closing spreads. The Odds API's timestamped historical snapshots are a paid feature, so NFL opening/Tuesday lines are unavailable on a free plan. Weather forecasts and historical observations are shown as context but excluded from the model until comparable point-in-time historical forecasts can be archived; using observed kickoff weather to train would leak hindsight. Predictions are estimates, not a demonstrated edge.

## Next increments

1. Add point-in-time NFL odds snapshots for exact 10 a.m. historical backtests if the Odds API plan supports it.
2. Add richer box-score efficiency and player/injury features with historical timestamps.
3. Archive forecast-at-lock weather and evaluate its incremental value against a locked holdout.
4. Evaluate the ten-pick strategy against market, favorite-only, and random baselines over a locked holdout.
