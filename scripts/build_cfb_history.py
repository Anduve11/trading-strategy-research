"""Normalize CollegeFootballData exporter schedules and odds CSVs for the app.

Usage: python scripts/build_cfb_history.py --input-dir /path/to/exported-csvs
The directory should contain season schedule exports plus matching per-provider
historical line exports. Game IDs are the authoritative join key.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/sports_pool"))
    args = parser.parse_args()
    inputs = sorted(args.input_dir.glob("*.csv"))
    schedules, quote_parts = [], []
    for path in inputs:
        frame = pd.read_csv(path, encoding="utf-8-sig", dtype={"Id": "string"}, low_memory=False)
        if "Season" in frame:
            schedules.append(frame)
        elif "LineProvider" in frame:
            quote_parts.append(frame)
    if not schedules or not quote_parts:
        raise SystemExit("Expected at least one schedule CSV and one LineProvider odds CSV.")

    schedule = pd.concat(schedules, ignore_index=True).drop_duplicates("Id")
    schedule["Id"] = schedule["Id"].astype("string").str.strip()
    schedule = schedule[schedule.Id.notna() & schedule.Id.ne("")].copy()
    schedule["Season"] = pd.to_numeric(schedule.Season, errors="coerce").astype("Int64")
    is_fbs = schedule.HomeClassification.fillna("").str.lower().eq("fbs") | schedule.AwayClassification.fillna("").str.lower().eq("fbs")
    schedule = schedule[is_fbs].copy()

    quotes = pd.concat(quote_parts, ignore_index=True)
    quotes["Id"] = quotes.Id.astype("string").str.strip()
    quotes = quotes[quotes.Id.notna() & quotes.Id.ne("")].copy()
    joined = quotes.merge(schedule, on="Id", how="left", validate="many_to_one", suffixes=("_line", ""), indicator=True)
    orphan_count = int(joined._merge.ne("both").sum())
    if orphan_count:
        # Keep exports for games outside the FBS schedule out of this FBS bundle.
        joined = joined[joined._merge.eq("both")].copy()
    joined = joined.drop(columns="_merge")
    for col in ["HomeTeam_line", "AwayTeam_line"]:
        if col in joined:
            other = "HomeTeam" if col.startswith("Home") else "AwayTeam"
            bad = joined[col].fillna("").str.casefold().ne(joined[other].fillna("").str.casefold())
            if bad.any():
                raise SystemExit(f"{int(bad.sum())} line rows disagree with schedule {other} names.")

    # Preserve the provider rows for future movement/consensus analysis.
    quote_cols = [
        "Id", "Season", "Week", "StartDate", "ConferenceGame", "HomeTeam", "AwayTeam",
        "HomePoints", "AwayPoints", "Venue", "LineProvider", "FormattedSpread", "Spread",
        "OpeningSpread", "OverUnder", "OpeningOverUnder", "HomeMoneyline", "AwayMoneyline",
    ]
    quote_rows = joined[[c for c in quote_cols if c in joined]].rename(columns={
        "Id": "game_id", "Season": "season", "Week": "week", "StartDate": "game_date",
        "ConferenceGame": "conference_game", "HomeTeam": "home_team", "AwayTeam": "away_team",
        "HomePoints": "home_score", "AwayPoints": "away_score", "Venue": "venue",
        "LineProvider": "line_provider", "FormattedSpread": "formatted_spread", "Spread": "home_spread",
        "OpeningSpread": "home_spread_open", "OverUnder": "total_line",
        "OpeningOverUnder": "total_line_open", "HomeMoneyline": "home_moneyline",
        "AwayMoneyline": "away_moneyline",
    })
    quote_rows["sport"] = "NCAAF"

    numeric_line_fields = ["Spread", "OpeningSpread", "OverUnder", "OpeningOverUnder", "HomeMoneyline", "AwayMoneyline"]
    for col in numeric_line_fields:
        if col in joined:
            joined[col] = pd.to_numeric(joined[col], errors="coerce")
    aggregated = joined.groupby("Id", as_index=False).agg(
        home_spread=("Spread", "median"),
        home_spread_open=("OpeningSpread", "median"),
        total_line=("OverUnder", "median"),
        total_line_open=("OpeningOverUnder", "median"),
        home_moneyline=("HomeMoneyline", "median"),
        away_moneyline=("AwayMoneyline", "median"),
        line_quote_count=("LineProvider", "count"),
        line_provider_count=("LineProvider", "nunique"),
        line_providers=("LineProvider", lambda x: ", ".join(sorted(set(x.dropna().astype(str))))),
    ).rename(columns={"Id": "id"})

    games = schedule.rename(columns={
        "Id": "id", "Season": "season", "Week": "week", "SeasonType": "season_type",
        "StartDate": "game_date", "StartTimeTBD": "start_time_tbd", "Completed": "completed",
        "NeutralSite": "neutral_site", "ConferenceGame": "conference_game", "VenueId": "venue_id",
        "Venue": "venue", "HomeId": "home_id", "HomeTeam": "home_team",
        "HomeClassification": "home_classification", "HomeConference": "home_conference",
        "HomePoints": "home_score", "HomePregameElo": "home_pregame_elo",
        "HomePostgameElo": "home_postgame_elo", "AwayId": "away_id", "AwayTeam": "away_team",
        "AwayClassification": "away_classification", "AwayConference": "away_conference",
        "AwayPoints": "away_score", "AwayPregameElo": "away_pregame_elo",
        "AwayPostgameElo": "away_postgame_elo",
    }).copy()
    games = games.merge(aggregated, on="id", how="left", validate="one_to_one")
    games["sport"] = "NCAAF"
    games["game_id"] = games.id.astype("string")
    games["game_date"] = pd.to_datetime(games.game_date, utc=True, errors="coerce").dt.tz_convert(None)
    for col in ["neutral_site", "conference_game", "completed", "start_time_tbd"]:
        if col in games:
            values = games[col].astype("string").str.strip().str.lower()
            games[col] = values.map({"true": 1.0, "1": 1.0, "yes": 1.0,
                                     "false": 0.0, "0": 0.0, "no": 0.0})
    for col in ["home_score", "away_score", "week", "home_spread", "home_spread_open", "total_line", "total_line_open"]:
        if col in games:
            games[col] = pd.to_numeric(games[col], errors="coerce")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    games.to_csv(args.output_dir / "cfb_games_2020_2025.csv.gz", index=False, compression="gzip")
    quote_rows.to_csv(args.output_dir / "cfb_line_quotes_2020_2025.csv.gz", index=False, compression="gzip")
    print(f"FBS schedule games: {len(games):,}; games with odds: {int(games.home_spread.notna().sum()):,}")
    print(f"Provider quote rows: {len(quote_rows):,}; unique games: {quote_rows.game_id.nunique():,}; "
          f"seasons: {int(games.season.min())}–{int(games.season.max())}; "
          f"non-FBS line rows omitted: {orphan_count:,}")
    print(f"Wrote {args.output_dir / 'cfb_games_2020_2025.csv.gz'} and {args.output_dir / 'cfb_line_quotes_2020_2025.csv.gz'}")


if __name__ == "__main__":
    main()
