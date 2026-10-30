"""Capture the current NFL/FBS spreads for the weekly Tuesday 10 a.m. snapshot."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sports_pool_model import archive_odds_snapshot, fetch_current_odds

MOUNTAIN=ZoneInfo("America/Denver")


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force",action="store_true",help="Capture now instead of checking the scheduled lock window")
    args=parser.parse_args()
    local=datetime.now(MOUNTAIN)
    inside_window=time(9,55)<=local.time().replace(tzinfo=None)<=time(10,30)
    if not args.force and not inside_window:
        print(f"Skipped; Mountain time is {local:%Y-%m-%d %H:%M:%S}, outside the Tuesday 9:55–10:30 a.m. capture window.")
        return
    api_key=os.environ.get("ODDS_API_KEY","")
    db_url=os.environ.get("SUPABASE_URL","")
    db_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
    if not all((api_key,db_url,db_key)):
        raise SystemExit("Set ODDS_API_KEY, SUPABASE_URL, and SUPABASE_SERVICE_ROLE_KEY as GitHub Actions secrets.")
    quotes=fetch_current_odds(api_key,["NFL","NCAAF"])
    if quotes.empty:
        print("No current NFL/NCAAF spread or total quotes were returned.")
        return
    saved=archive_odds_snapshot(quotes,db_url,db_key)
    print(f"Captured {saved:,} quote rows at {datetime.now(MOUNTAIN).isoformat()} Mountain.")


if __name__=="__main__":
    main()
