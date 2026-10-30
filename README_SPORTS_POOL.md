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

Never commit secrets. Environment variables with the same names are also supported. The app caches source data for one day and current odds for 15 minutes; it does not write API keys or datasets into the repository.

## What it does

- Loads NFL history from nflverse and FBS history, closing lines, game weather, and coach records from CollegeFootballData.
- Refreshes current NFL and college spreads and totals from The Odds API every 15 minutes; the dashboard can force an immediate refresh.
- Trains and compares nine candidates: a market-only logistic baseline plus two settings each for regularized logistic regression, random forest, extra trees, and histogram gradient boosting independently for NFL and FBS.
- Builds pregame features from line, total, home field, recent team scoring and win form, opponent scoring, rest, and previous coach performance. Rolling form uses completed games only.
- Selects a model by development-season Brier score, reserves the latest completed season as holdout, calibrates on development out-of-sample predictions, and ranks current games by calibrated cover probability plus cross-model agreement.
- Displays the top ten recommendations and the full available slate with line timestamp, venue, coaches, and historical weather context where available.
- Moves integer spreads half a point away from zero (home/favorite -3 becomes -3.5; underdog +3 becomes +3.5).

## Data and methodology limits

Historical close lines do not reproduce your pool's 10 a.m. lines. The Odds API historical snapshot endpoint is a paid feature, so this release uses historical close lines for model development and today's live consensus for the current slate. Its historical predictions are proxies until we backtest with archived 10 a.m. snapshots. Observed kickoff weather is shown as context and excluded from the pick model because it was not known at lock. Predictions are estimates, not a demonstrated edge.

## Next increments

1. Add point-in-time odds history for exact 10 a.m. historical backtests if the API plan supports it.
2. Add richer game-by-game box-score features and player/injury sources with historical timestamps.
3. Add forecast-at-lock weather snapshots and cross-validate venue, coach tenure, and travel features.
4. Evaluate the ten-pick strategy against market, favorite-only, and random baselines over a locked holdout.
