"""Backfill Tuesday 10 a.m. Mountain spread snapshots from The Odds API.

Requires a paid historical-odds plan and these environment variables:
  ODDS_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

Example:
  python scripts/backfill_odds_snapshots.py --start 2021-01-01 --end 2026-10-30

This makes one historical request per league per Tuesday, for spreads only.
Historical requests consume paid quota; inspect your plan before a large run.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, time as daytime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sports_pool_model import SPORT_KEYS, archive_odds_snapshot

API="https://api.the-odds-api.com/v4"
MOUNTAIN=ZoneInfo("America/Denver")


def tuesdays(start: date, end: date):
    day=start+timedelta(days=(1-start.weekday())%7)
    while day<=end:
        yield day
        day+=timedelta(days=7)


def flatten_spreads(payload: dict, sport: str) -> pd.DataFrame:
    rows=[]
    for event in payload.get("data",[]):
        for book in event.get("bookmakers",[]):
            for market in book.get("markets",[]):
                if market.get("key")!="spreads":continue
                for outcome in market.get("outcomes",[]):
                    rows.append({
                        "sport":sport,"game_id":event.get("id"),"start_time":event.get("commence_time"),
                        "home_team":event.get("home_team"),"away_team":event.get("away_team"),
                        "book":book.get("key",book.get("title")),"updated":book.get("last_update"),
                        "market":"spreads","name":outcome.get("name"),
                        "point":outcome.get("point"),"price":outcome.get("price"),
                    })
    return pd.DataFrame(rows)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start",required=True,help="First date to include (YYYY-MM-DD)")
    parser.add_argument("--end",required=True,help="Last date to include (YYYY-MM-DD)")
    args=parser.parse_args()
    api_key=os.environ.get("ODDS_API_KEY","")
    db_url=os.environ.get("SUPABASE_URL","")
    db_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
    if not all((api_key,db_url,db_key)):
        raise SystemExit("Set ODDS_API_KEY, SUPABASE_URL, and SUPABASE_SERVICE_ROLE_KEY in the shell environment first.")
    start=date.fromisoformat(args.start);end=date.fromisoformat(args.end)
    total=0;requests_made=0
    for day in tuesdays(start,end):
        snapshot=datetime.combine(day,daytime(10,0),MOUNTAIN).astimezone(timezone.utc)
        for sport,sport_key in SPORT_KEYS.items():
            response=requests.get(f"{API}/historical/sports/{sport_key}/odds",params={
                "apiKey":api_key,"regions":"us","markets":"spreads","oddsFormat":"american",
                "date":snapshot.isoformat(timespec="seconds").replace("+00:00","Z"),
            },timeout=45)
            response.raise_for_status()
            payload=response.json()
            quotes=flatten_spreads(payload,sport)
            actual_snapshot=payload.get("timestamp",snapshot.isoformat())
            if not quotes.empty:
                total+=archive_odds_snapshot(quotes,db_url,db_key,actual_snapshot)
            requests_made+=1
            print(f"{day} {sport}: {len(quotes):,} quote rows at {actual_snapshot}")
            time.sleep(.15)
    print(f"Finished: {requests_made:,} API requests; {total:,} quote rows submitted to Supabase.")


if __name__=="__main__":
    main()
