# Sunday Slate Lab

Separate Streamlit research app for a weekly ten-pick NFL + college football pool.

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

Never commit secrets. Environment variables with the same names are also supported. Local line and pick CSVs are ignored by Git. Hosted Streamlit storage may reset, so download archives periodically or add durable storage before relying on long-term history.

## What's included

- NFL five-year schedule/results, closing spread and total, venue, surface/roof, weather and coaches from nflverse.
- CFBD historical FBS game loader plus optional lines, weather, team statistics, SP+ / Elo ratings and coach datasets.
- NFL and FBS walk-forward model comparison by season against a spread-only baseline. Pregame form is calculated using prior games and earlier seasons only.
- CSV template/import and lock-line archive for the actual pool board at 10:00 a.m.
- Weekly pick card that requires exactly ten picks and records each selected side with its lock line.
- Integer spread adjustment by 0.5 points (favorites -3 become -3.5; underdogs +3 become +3.5).
- Current odds fetch via The Odds API when configured; returned provider update timestamps are shown for lock-time review.

## Critical methodology boundary

Closing odds and kickoff weather cannot stand in for the pool's 10 a.m. lines or 10 a.m. forecast. Store the actual lock snapshot with its timestamp. Until several seasons of actual lock snapshots exist, historical backtests that use closing spreads are proxies and must be labeled as such. The present model is a research baseline, not a validated edge or betting recommendation.

## Next increments

1. Add final-score entry and automatic grading for saved weekly pick cards.
2. Add forecast-at-lock weather snapshots and injury/player-availability sources with archived timestamps.
3. Add pregame rating, line-movement, travel/rest and coach-tenure features after confirming point-in-time availability.
4. Evaluate pool scoring rules and compare ten-pick cards to spread consensus and random/market baselines.
