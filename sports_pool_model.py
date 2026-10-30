"""Data loading, point-in-time features, model selection, and slate ranking."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import math
import re
import requests
import numpy as np
import pandas as pd

NFL_SCHEDULES = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
CFBD = "https://api.collegefootballdata.com"
ODDS = "https://api.the-odds-api.com/v4"
SPORT_KEYS = {"NFL": "americanfootball_nfl", "NCAAF": "americanfootball_ncaaf"}


def api_get(url: str, params: dict[str, Any], token: str = "") -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(url, params=params, headers=headers, timeout=45)
    if r.status_code == 401:
        raise RuntimeError(f"{r.url.split('?')[0]} returned HTTP 401 Unauthorized.")
    if r.status_code == 429:
        raise RuntimeError(f"{r.url.split('?')[0]} returned HTTP 429 (rate limit).")
    r.raise_for_status()
    return r.json()


def load_nfl_history(start_year: int, end_year: int) -> pd.DataFrame:
    d = pd.read_csv(NFL_SCHEDULES, low_memory=False)
    d = d[d.season.between(start_year, end_year)].copy()
    d["game_date"] = pd.to_datetime(d.gameday, errors="coerce")
    d["sport"] = "NFL"
    # nflverse uses positive values when the home team is favored. This model
    # stores the handicap from the home team's perspective (favorite is negative).
    d["home_spread"] = -pd.to_numeric(d.spread_line, errors="coerce")
    d["total_line"] = pd.to_numeric(d.total_line, errors="coerce")
    d["home_score"] = pd.to_numeric(d.home_score, errors="coerce")
    d["away_score"] = pd.to_numeric(d.away_score, errors="coerce")
    d["home_team"] = d.home_team.astype(str)
    d["away_team"] = d.away_team.astype(str)
    d["neutral_site"] = d.location.eq("neutral") if "location" in d else False
    d["venue"] = d.get("stadium", "")
    d["temperature"] = pd.to_numeric(d.get("temp"), errors="coerce")
    d["wind"] = pd.to_numeric(d.get("wind"), errors="coerce")
    d["home_coach"] = d.get("home_coach", "")
    d["away_coach"] = d.get("away_coach", "")
    d["home_spread_open"] = np.nan  # nflverse's public schedule field is closing spread only.
    d["venue_lat"], d["venue_lon"], d["venue_elevation"] = _nfl_venue_columns(d)
    d["venue_dome"] = d.home_team.astype(str).isin(NFL_DOME)
    return d


# Approximate venue coordinates for regular NFL home stadiums. Used to estimate
# trip distance and altitude changes; historic international/neutral venues
# remain missing unless their coordinates are supplied by another source.
NFL_VENUES = {
    "ARI": (33.5276,-112.2626,331), "ATL": (33.7554,-84.4008,320),
    "BAL": (39.2780,-76.6227,45), "BUF": (42.7738,-78.7870,183),
    "CAR": (35.2258,-80.8528,229), "CHI": (41.8623,-87.6167,181),
    "CIN": (39.0954,-84.5160,147), "CLE": (41.5061,-81.6995,199),
    "DAL": (32.7473,-97.0945,170), "DEN": (39.7439,-105.0201,1609),
    "DET": (42.3400,-83.0456,177), "GB": (44.5013,-88.0622,177),
    "HOU": (29.6847,-95.4107,13), "IND": (39.7601,-86.1639,218),
    "JAX": (30.3239,-81.6373,5), "KC": (39.0489,-94.4841,266),
    "LA": (33.9535,-118.3392,36), "LAC": (33.9535,-118.3392,36),
    "MIA": (25.9580,-80.2389,2), "MIN": (44.9738,-93.2575,256),
    "NE": (42.0909,-71.2643,33), "NO": (29.9511,-90.0812,1),
    "NYG": (40.8135,-74.0745,2), "NYJ": (40.8135,-74.0745,2),
    "PHI": (39.9008,-75.1675,5), "PIT": (40.4468,-80.0158,225),
    "SF": (37.4033,-121.9700,6), "SEA": (47.5952,-122.3316,17),
    "TB": (27.9759,-82.5033,11), "TEN": (36.1665,-86.7713,135),
    "WAS": (38.9077,-76.8645,8), "LV": (36.0909,-115.1833,615),
}

NFL_DOME = {"ARI","ATL","DAL","DET","HOU","IND","LA","LAC","LV","MIN","NO"}


def _nfl_venue_columns(d: pd.DataFrame) -> tuple[pd.Series,pd.Series,pd.Series]:
    def get(team: Any, pos: int) -> float:
        return float(NFL_VENUES[str(team)][pos]) if str(team) in NFL_VENUES else np.nan
    return (d.home_team.map(lambda x:get(x,0)),d.home_team.map(lambda x:get(x,1)),d.home_team.map(lambda x:get(x,2)))


def _cfbd_games(year: int, token: str) -> pd.DataFrame:
    payload = api_get(f"{CFBD}/games", {"year": year, "seasonType": "both", "classification": "fbs"}, token)
    d = pd.json_normalize(payload, sep="_").rename(columns={
        "homeTeam": "home_team", "awayTeam": "away_team", "homePoints": "home_score",
        "awayPoints": "away_score", "startDate": "game_date", "neutralSite": "neutral_site",
    })
    # CFBD's current schema nests team and venue objects; legacy-compatible
    # flat names are still accepted so cached/exported payloads keep working.
    for dst,candidates in {
        "home_team":["homeTeam_name","homeTeam"],
        "away_team":["awayTeam_name","awayTeam"],
        "home_score":["homeTeam_points","homePoints","home_points","homeScore"],
        "away_score":["awayTeam_points","awayPoints","away_points","awayScore"],
        "game_date":["startDate","start_date","startTime","start_time"],
        "venue_id":["venue_id","venueId"],
        "venue":["venue_name","venue"],
    }.items():
        if dst not in d:
            for src in candidates:
                if src in d:
                    d[dst]=d[src];break
    # pandas can produce both venue_id and venueId when a nested venue object
    # is normalized alongside a legacy flat identifier. Keep one join key.
    d=d.loc[:,~d.columns.duplicated()].copy()
    d["season"] = year
    d["sport"] = "NCAAF"
    if "venue_id" not in d and "venueId" in d:d=d.rename(columns={"venueId":"venue_id"})
    if "venue_name" in d and "venue" not in d:d=d.rename(columns={"venue_name":"venue"})
    d["game_date"] = pd.to_datetime(d.get("game_date"), errors="coerce", utc=True).dt.tz_convert(None)
    for c in ("home_score", "away_score"):
        if c not in d: d[c] = np.nan
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if "home_team" not in d:d["home_team"]=""
    if "away_team" not in d:d["away_team"]=""
    d["home_team"] = d["home_team"].astype(str)
    d["away_team"] = d["away_team"].astype(str)
    d["neutral_site"] = d.get("neutral_site", False)
    if "venue" not in d:d["venue"] = ""
    d["venue"] = d["venue"].map(lambda v: v.get("name","") if isinstance(v,dict) else v)
    return d


def _cfbd_lines(year: int, token: str) -> pd.DataFrame:
    payload = api_get(f"{CFBD}/lines", {"year": year}, token)
    rows = []
    for game in payload:
        # Standard CFBD lines responses have one game with nested provider
        # quotes. Accept a flattened provider row too, as exporters and schema
        # revisions may expose those fields directly.
        quotes = game.get("lines") or [game]
        vals = []
        opens = []
        totals = []
        for q in quotes:
            try:
                vals.append(float(q.get("spread")))
            except (TypeError, ValueError):
                pass
            try:
                if q.get("spreadOpen") is not None: opens.append(float(q.get("spreadOpen")))
            except (TypeError, ValueError):
                pass
            try:
                totals.append(float(q.get("overUnder")))
            except (TypeError, ValueError):
                pass
        if vals:
            rows.append({"id": game.get("id"), "home_spread": float(np.median(vals)), "home_spread_open": float(np.median(opens)) if opens else np.nan, "total_line": float(np.median(totals)) if totals else np.nan})
    return pd.DataFrame(rows, columns=["id", "home_spread", "home_spread_open", "total_line"])


def _cfbd_venues(token: str) -> pd.DataFrame:
    payload=api_get(f"{CFBD}/venues",{},token)
    d=pd.json_normalize(payload,sep="_")
    ren={"id":"venue_id","latitude":"venue_lat","longitude":"venue_lon","elevation":"venue_elevation","dome":"venue_dome","name":"venue"}
    d=d.rename(columns={k:v for k,v in ren.items() if k in d})
    if "venue_id" not in d:return pd.DataFrame()
    return d.drop_duplicates("venue_id",keep="last")


def _cfbd_weather(year: int, token: str) -> pd.DataFrame:
    payload = api_get(f"{CFBD}/games/weather", {"year": year}, token)
    d = pd.json_normalize(payload, sep="_")
    rename = {"temperature": "temperature", "windSpeed": "wind"}
    d = d.rename(columns={k:v for k,v in rename.items() if k in d})
    return d[[c for c in ["id", "temperature", "wind", "humidity", "precipitation", "snowfall"] if c in d]]


def _cfbd_coaches(year: int, token: str) -> pd.DataFrame:
    payload=api_get(f"{CFBD}/coaches",{"year":year},token)
    d=pd.json_normalize(payload,sep="_")
    school=next((c for c in ["school","team"] if c in d),None)
    if not school:return pd.DataFrame(columns=["school","coach"])
    first=next((c for c in ["firstName","first_name"] if c in d),None)
    last=next((c for c in ["lastName","last_name"] if c in d),None)
    d["coach"]=(d[first].fillna("") if first else "")+" "+(d[last].fillna("") if last else "")
    d["coach"]=d.coach.str.strip()
    if "games" in d:
        d["games"]=pd.to_numeric(d.games,errors="coerce").fillna(0)
        d=d.sort_values("games").drop_duplicates(school,keep="last")
    else:d=d.drop_duplicates(school,keep="last")
    return d[[school,"coach"]].rename(columns={school:"school"})


def _cfbd_team_game_stats(year: int, token: str) -> pd.DataFrame:
    """Pivot CFBD per-game team box scores into one joined row per game."""
    payload=api_get(f"{CFBD}/games/teams",{"year":year,"seasonType":"both","classification":"fbs"},token)
    rows=[]
    wanted={"totalYards":"yards","passingYards":"pass_yards","rushingYards":"rush_yards","turnovers":"turnovers","sacks":"sacks","thirdDownEff":"third_down_eff","redZoneEff":"red_zone_eff","firstDowns":"first_downs"}
    for item in payload:
        gid=item.get("gameId",item.get("id"))
        for team in item.get("teams",[]) if isinstance(item.get("teams"),list) else [item]:
            side=str(team.get("homeAway",team.get("home_away",""))).lower()
            if side not in ("home","away"):continue
            stats=team.get("stats",[])
            if isinstance(stats,list):stats={str(s.get("category")):s.get("stat") for s in stats if isinstance(s,dict)}
            row={"id":gid}
            for source,target in wanted.items():
                val=stats.get(source)
                if isinstance(val,str) and "/" in val and target in ("third_down_eff","red_zone_eff"):
                    try:
                        made,att=map(float,val.split("/",1));val=made/att if att else np.nan
                    except (TypeError,ValueError):val=np.nan
                row[f"{side}_{target}"]=pd.to_numeric(pd.Series([val]),errors="coerce").iloc[0]
            rows.append(row)
    d=pd.DataFrame(rows)
    if d.empty:return pd.DataFrame(columns=["id"])
    return d.groupby("id",as_index=False).first()


def load_cfb_history(start_year: int, end_year: int, token: str, venues: pd.DataFrame | None = None) -> pd.DataFrame:
    frames = []
    venue_error=""
    if venues is None:
        try:venues=_cfbd_venues(token)
        except Exception as exc:
            venues=pd.DataFrame();venue_error=str(exc)
    for year in range(start_year, end_year + 1):
        games = _cfbd_games(year, token)
        notes=[]
        if venue_error:notes.append(f"Venue metadata unavailable: {venue_error}")
        if "venue_id" in games and not venues.empty:
            games=games.merge(venues,on="venue_id",how="left",suffixes=("","_venue"))
        if "venue" not in games:games["venue"]=games.get("venue_name","")
        for c in ["venue_lat","venue_lon","venue_elevation","venue_dome","city","state","timezone"]:
            if c not in games:games[c]=np.nan
        for loader in (_cfbd_lines, _cfbd_weather, _cfbd_team_game_stats):
            try:
                extra = loader(year, token)
                if "id" in games and "id" in extra:
                    games = games.merge(extra, on="id", how="left", suffixes=("", "_extra"))
            except Exception as exc:
                # Keep valid schedules/results when a separate supplemental
                # endpoint has different access, coverage, or rate limits.
                notes.append(f"{loader.__name__}: {exc}")
        try:
            coaches=_cfbd_coaches(year,token)
            if not coaches.empty:
                coach_map={normalize_team(r.school):r.coach for r in coaches.itertuples() if str(r.coach).strip()}
                games["home_coach"]=games.home_team.map(lambda x:coach_map.get(normalize_team(x),np.nan))
                games["away_coach"]=games.away_team.map(lambda x:coach_map.get(normalize_team(x),np.nan))
        except Exception as exc:
            notes.append(f"Coach data unavailable: {exc}")
        games["cfbd_data_notes"]="; ".join(notes)
        frames.append(games)
    out=pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if "id" in out:out["game_id"]=out.id.astype(str)
    return out


def half_line(value: Any) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return np.nan
    if not np.isfinite(x): return np.nan
    if math.isclose(x % 1, 0, abs_tol=1e-9):
        return x - 0.5 if x < 0 else x + 0.5
    return x


def _coach_name(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def add_pregame_features(games: pd.DataFrame) -> pd.DataFrame:
    """Create point-in-time form, rest, travel, and coaching features.

    Every value is assembled before the target game's result is added. Observed
    kickoff weather is retained for context but deliberately excluded from the
    pregame model to avoid leaking information unavailable at the pool lock.
    """
    d=games.copy().sort_values("game_date").reset_index(drop=True)
    for c in ["home_score","away_score","home_spread","home_spread_open","total_line","venue_lat","venue_lon","venue_elevation"]:
        if c not in d:d[c]=np.nan
    d["season"]=pd.to_numeric(d.get("season"),errors="coerce")
    d["home_line_raw"]=pd.to_numeric(d.home_spread,errors="coerce")
    d["home_line"]=d.home_line_raw.map(half_line)
    d["home_line_open"]=pd.to_numeric(d.home_spread_open,errors="coerce").map(half_line)
    d["total_line"]=pd.to_numeric(d.total_line,errors="coerce")
    d["home_margin"]=pd.to_numeric(d.home_score,errors="coerce")-pd.to_numeric(d.away_score,errors="coerce")
    d["home_cover"]=((d.home_margin+d.home_line)>0).astype(float)
    d.loc[d.home_margin.isna()|d.home_line.isna(),"home_cover"]=np.nan
    d["line_move_home"]=d.home_line-d.home_line_open

    def dist_miles(lat1: float,lon1: float,lat2: float,lon2: float) -> float:
        if not np.isfinite([lat1,lon1,lat2,lon2]).all():return np.nan
        r=3958.7613
        p1,p2=np.radians(lat1),np.radians(lat2)
        dp=np.radians(lat2-lat1);dl=np.radians(lon2-lon1)
        a=np.sin(dp/2)**2+np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
        return float(2*r*np.arcsin(np.sqrt(min(1.,a))))

    state:dict[str,list[dict[str,Any]]]={}
    coach_state:dict[str,list[tuple[float,float]]]={}
    elo_state:dict[str,list[tuple[pd.Timestamp,float]]]={}
    last_coach:dict[str,str]={}
    feature_rows=[]
    for _,g in d.iterrows():
        day=pd.to_datetime(g.game_date,errors="coerce")
        season=int(g.season) if pd.notna(g.season) else None
        lat=pd.to_numeric(pd.Series([g.get("venue_lat")]),errors="coerce").iloc[0]
        lon=pd.to_numeric(pd.Series([g.get("venue_lon")]),errors="coerce").iloc[0]
        elev=pd.to_numeric(pd.Series([g.get("venue_elevation")]),errors="coerce").iloc[0]
        pair=[]
        elo_pair={}
        for side,opposite in (("home","away"),("away","home")):
            team=str(g.get(f"{side}_team",""));coach=_coach_name(g.get(f"{side}_coach",""))
            prior=[x for x in state.get(team,[]) if pd.isna(day) or x["date"]<day]
            recent=prior[-10:]
            wins=np.array([x["win"] for x in recent],dtype=float)
            margins=np.array([x["margin"] for x in recent],dtype=float)
            points_for=np.array([x["pf"] for x in recent],dtype=float)
            points_against=np.array([x["pa"] for x in recent],dtype=float)
            ats=np.array([x["ats_margin"] for x in recent if np.isfinite(x["ats_margin"])],dtype=float)
            rest=max(0,(day-prior[-1]["date"]).days) if prior and pd.notna(day) else 7
            prior_this_season=[x for x in prior if season is not None and x["season"]==season]
            bye=bool(prior_this_season and 13<=((day-prior_this_season[-1]["date"]).days)<=24) if pd.notna(day) else False
            cp=coach_state.get(coach,[])[-10:] if coach else []
            cwin=np.mean([x[0] for x in cp]) if cp else .5
            cats=np.mean([x[1] for x in cp]) if cp else 0.
            last=prior[-1] if prior else {}
            prior_elo=[x for x in elo_state.get(team,[]) if pd.isna(day) or x[0]<day]
            elo=prior_elo[-1][1] if prior_elo else 1500.
            if prior_elo and season is not None and int(prior_elo[-1][0].year)!=season:
                elo=1500.+.75*(elo-1500.)
            elo_pair[side]=float(elo)
            travel=dist_miles(last.get("lat",np.nan),last.get("lon",np.nan),lat,lon) if last else np.nan
            tz_shift=(lon-last.get("lon",lon))/15. if last and np.isfinite(lon) and np.isfinite(last.get("lon",np.nan)) else np.nan
            alt_change=elev-last.get("elev",elev) if last and np.isfinite(elev) and np.isfinite(last.get("elev",np.nan)) else np.nan
            n2=min(2,len(recent));n3=min(3,len(recent));n5=min(5,len(recent))
            stats={
                "win5":float(wins[-5:].mean()) if len(wins) else .5,
                "margin5":float(margins[-5:].mean()) if len(margins) else 0.,
                "points_for5":float(points_for[-5:].mean()) if len(points_for) else 21.,
                "points_against5":float(points_against[-5:].mean()) if len(points_against) else 21.,
                "win10":float(wins.mean()) if len(wins) else .5,
                "margin10":float(margins.mean()) if len(margins) else 0.,
                "margin2":float(margins[-2:].mean()) if n2 else 0.,
                "margin3":float(margins[-3:].mean()) if n3 else 0.,
                "points_for2":float(points_for[-2:].mean()) if n2 else 21.,
                "points_for3":float(points_for[-3:].mean()) if n3 else 21.,
                "points_against2":float(points_against[-2:].mean()) if n2 else 21.,
                "points_against3":float(points_against[-3:].mean()) if n3 else 21.,
                "win_pct3":float(wins[-3:].mean()) if n3 else .5,
                "ats_margin3":float(np.mean(ats[-3:])) if len(ats) else 0.,
                "ats_cover3":float(np.mean(np.array(ats[-3:])>0)) if len(ats) else .5,
                "ats_games3":float(min(3,len(ats))),"games_seen":float(len(recent)),
                "momentum":float(margins[-3:].mean()-margins[-5:].mean()) if n3 and n5 else 0.,
                "rest_days":float(min(rest,21)),"bye_return":float(bye),
                "travel_miles":float(travel) if np.isfinite(travel) else np.nan,
                "time_zone_shift":float(tz_shift),"altitude_change":float(alt_change),
                "coach_win10":float(cwin),"coach_ats10":float(cats),"coach_games":float(len(coach_state.get(coach,[]))) if coach else 0.,
                "coach_changed":float(bool(coach and last_coach.get(team) and last_coach[team]!=coach)),
                "elo":float(elo),
            }
            # Rolling CFBD box-score efficiency. These are computed from each
            # team's prior games only; the current game's stats enter afterward.
            for key in ["yards","pass_yards","rush_yards","turnovers","sacks","third_down_eff","red_zone_eff"]:
                vals=np.array([pd.to_numeric(pd.Series([x.get(key,np.nan)]),errors="coerce").iloc[0] for x in recent],dtype=float)
                vals=vals[np.isfinite(vals)]
                stats[f"{key}3"]=float(np.mean(vals[-3:])) if len(vals) else np.nan
            pair.append(stats)
        feature_rows.append(pair)
        hs,as_=g.get("home_score"),g.get("away_score")
        if pd.notna(hs) and pd.notna(as_) and pd.notna(day):
            home,away=str(g.home_team),str(g.away_team)
            hline=float(g.home_line) if pd.notna(g.home_line) else np.nan
            line_res=float(hs-as_+hline) if np.isfinite(hline) else np.nan
            for team,side,pf,pa,margin,win,ats_margin in (
                (home,"home",float(hs),float(as_),float(hs-as_),float(hs>as_),line_res),
                (away,"away",float(as_),float(hs),float(as_-hs),float(as_>hs),-line_res),
            ):
                coach=_coach_name(g.get(f"{side}_coach",""))
                record={"date":day,"season":season,"pf":pf,"pa":pa,"margin":margin,"win":win,"ats_margin":ats_margin,"lat":lat,"lon":lon,"elev":elev}
                for key in ["yards","pass_yards","rush_yards","turnovers","sacks","third_down_eff","red_zone_eff"]:
                    record[key]=pd.to_numeric(pd.Series([g.get(f"{side}_{key}",np.nan)]),errors="coerce").iloc[0]
                state.setdefault(team,[]).append(record)
                if coach:
                    coach_state.setdefault(coach,[]).append((win,ats_margin if np.isfinite(ats_margin) else 0.))
                    last_coach[team]=coach
            # Append Elo after deriving features. The strict date filter above
            # prevents games on the same day from leaking results into one another.
            expected=1./(1.+10.**((elo_pair["away"]-elo_pair["home"]-55.)/400.))
            actual=float(hs>as_)+.5*float(hs==as_)
            mov=float(hs-as_)
            k=20.*np.log1p(abs(mov))/np.log1p(14.)
            delta=k*(actual-expected)
            elo_state.setdefault(home,[]).append((day,elo_pair["home"]+delta))
            elo_state.setdefault(away,[]).append((day,elo_pair["away"]-delta))
    metrics=list(feature_rows[0][0]) if feature_rows else []
    for metric in metrics:
        d[f"home_{metric}"]=[p[0][metric] for p in feature_rows]
        d[f"away_{metric}"]=[p[1][metric] for p in feature_rows]
    for metric in ["margin5","win5","margin2","margin3","win_pct3","ats_cover3","momentum","travel_miles","time_zone_shift","rest_days","bye_return","coach_win10","coach_ats10","altitude_change","elo"]:
        d[f"{metric}_diff"]=d[f"home_{metric}"]-d[f"away_{metric}"]
    d["form_margin_diff"]=d.margin5_diff
    d["form_win_diff"]=d.win5_diff
    d["points_allowed_diff"]=d.away_points_against5-d.home_points_against5
    d["rest_diff"]=d.home_rest_days-d.away_rest_days
    d["coach_form_diff"]=d.home_coach_win10-d.away_coach_win10
    neutral=d["neutral_site"].fillna(False).astype(bool) if "neutral_site" in d else pd.Series(False,index=d.index)
    d["home_advantage"]=(~neutral).astype(int)
    d["venue_dome_flag"]=d.get("venue_dome",pd.Series(False,index=d.index)).fillna(False).astype(float)
    return d


FEATURES = ["home_line","home_line_open","line_move_home","total_line","home_advantage","form_margin_diff","form_win_diff","points_allowed_diff","rest_diff","home_margin5","away_margin5","home_win5","away_win5","home_margin2","away_margin2","home_points_for2","away_points_for2","home_points_for3","away_points_for3","home_points_against2","away_points_against2","home_points_against3","away_points_against3","home_win_pct3","away_win_pct3","home_ats_margin3","away_ats_margin3","home_ats_cover3","away_ats_cover3","home_ats_games3","away_ats_games3","home_games_seen","away_games_seen","home_margin3","away_margin3","home_momentum","away_momentum","home_bye_return","away_bye_return","home_rest_days","away_rest_days","home_travel_miles","away_travel_miles","time_zone_shift_diff","altitude_change_diff","home_coach_win10","away_coach_win10","home_coach_ats10","away_coach_ats10","coach_form_diff","home_coach_games","away_coach_games","home_coach_changed","away_coach_changed","venue_dome_flag","home_elo","away_elo","elo_diff","home_yards3","away_yards3","home_pass_yards3","away_pass_yards3","home_rush_yards3","away_rush_yards3","home_turnovers3","away_turnovers3","home_sacks3","away_sacks3","home_third_down_eff3","away_third_down_eff3","home_red_zone_eff3","away_red_zone_eff3"]
MARKET_FEATURES=["home_line","home_line_open","line_move_home","total_line","home_advantage"]


def walk_forward_model(study: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, str, dict[str, Any]]:
    from sklearn.ensemble import AdaBoostClassifier, ExtraTreesClassifier, GradientBoostingClassifier, HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    models = {
        "Market-only logistic": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), StandardScaler(), LogisticRegression(C=.2, max_iter=1200)),
        "Logistic C=.05": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), StandardScaler(), LogisticRegression(C=.05, max_iter=1200)),
        "Logistic C=.5": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), StandardScaler(), LogisticRegression(C=.5, max_iter=1200)),
        "Random forest leaf=8": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), RandomForestClassifier(n_estimators=200, min_samples_leaf=8, max_features=.8, class_weight="balanced_subsample", random_state=17, n_jobs=-1)),
        "Random forest leaf=20": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), RandomForestClassifier(n_estimators=200, min_samples_leaf=20, max_features=.8, class_weight="balanced_subsample", random_state=18, n_jobs=-1)),
        "Extra trees leaf=8": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), ExtraTreesClassifier(n_estimators=200, min_samples_leaf=8, max_features=.8, class_weight="balanced", random_state=23, n_jobs=-1)),
        "Extra trees leaf=20": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), ExtraTreesClassifier(n_estimators=200, min_samples_leaf=20, max_features=.8, class_weight="balanced", random_state=24, n_jobs=-1)),
        "Hist gradient leaves=6": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), HistGradientBoostingClassifier(max_iter=140, learning_rate=.05, l2_regularization=2., max_leaf_nodes=6, random_state=31)),
        "Hist gradient leaves=12": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), HistGradientBoostingClassifier(max_iter=140, learning_rate=.05, l2_regularization=2., max_leaf_nodes=12, random_state=32)),
        "Gradient boost depth=1": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), GradientBoostingClassifier(n_estimators=100,learning_rate=.03,max_depth=1,min_samples_leaf=12,random_state=41)),
        "Gradient boost depth=2": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), GradientBoostingClassifier(n_estimators=100,learning_rate=.03,max_depth=2,min_samples_leaf=12,random_state=42)),
        "AdaBoost stumps": make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True), AdaBoostClassifier(n_estimators=100,learning_rate=.03,random_state=43)),
    }
    feature_map={name:(MARKET_FEATURES if name=="Market-only logistic" else FEATURES) for name in models}
    d = study.dropna(subset=["home_cover", "home_line", "season"]).copy()
    years = sorted(d.season.astype(int).unique())
    predictions = []
    if len(years) < 3:
        return pd.DataFrame(), pd.DataFrame(), "Not enough seasons", {}
    min_train_years = 2
    for year in years[min_train_years:]:
        tr, te = d[d.season < year], d[d.season == year]
        if len(tr) < 250 or te.empty: continue
        for name, model in models.items():
            m = model
            cols=feature_map[name]
            m.fit(tr[cols], tr.home_cover.astype(int))
            p = m.predict_proba(te[cols])[:, 1]
            out = te[["sport","season","week","game_date","home_team","away_team","home_line","home_margin","home_cover"]].copy()
            out["model"] = name
            out["p_home_cover"] = p
            out["p_away_cover"] = 1-p
            predictions.append(out)
    if not predictions: return pd.DataFrame(), pd.DataFrame(), "No valid folds", {}
    pred = pd.concat(predictions, ignore_index=True)
    # Model choice uses development seasons only. The most recent season remains a holdout.
    completed=[]
    for yr,g in study.groupby("season"):
        scheduled=g[["home_score","away_score"]].notna().all(axis=1).mean()
        if scheduled>=.98:completed.append(int(yr))
    holdout_year=max(completed) if completed else years[-1]
    dev = pred[pred.season < holdout_year]
    metrics = []
    for name, g in pred.groupby("model"):
        y = g.home_cover.astype(float).to_numpy()
        p = np.clip(g.p_home_cover.to_numpy(), 1e-6, 1-1e-6)
        h=g[g.season==holdout_year]
        hy=h.home_cover.astype(float).to_numpy();hp=np.clip(h.p_home_cover.to_numpy(),1e-6,1-1e-6)
        dg=g[g.season<holdout_year];dy=dg.home_cover.astype(float).to_numpy();dp=np.clip(dg.p_home_cover.to_numpy(),1e-6,1-1e-6)
        metrics.append({"Model":name,"Development Brier":float(np.mean((dp-dy)**2)) if len(dg) else np.nan,"OOS games":len(g),"OOS accuracy":float(((p>=.5)==y).mean()),"OOS Brier":float(np.mean((p-y)**2)),"OOS log loss":float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),"Holdout year":holdout_year,"Holdout games":len(h),"Holdout accuracy":float(((hp>=.5)==hy).mean()) if len(h) else np.nan,"Holdout Brier":float(np.mean((hp-hy)**2)) if len(h) else np.nan,"Holdout log loss":float(-np.mean(hy*np.log(hp)+(1-hy)*np.log(1-hp))) if len(h) else np.nan})
    metric_df = pd.DataFrame(metrics).sort_values("Development Brier")
    if dev.empty:
        selected = metric_df.iloc[0]["Model"]
    else:
        scored=[]
        for name,g in dev.groupby("model"):
            y=g.home_cover.astype(float).to_numpy();p=np.clip(g.p_home_cover.to_numpy(),1e-6,1-1e-6)
            scored.append((float(np.mean((p-y)**2)),name))
        selected=sorted(scored)[0][1]
    # Refit chosen model on all completed history for the current slate.
    bank={}
    for name,model in models.items():
        model.fit(d[feature_map[name]],d.home_cover.astype(int))
        bank[name]=model
    dev_selected=pred[(pred.model==selected)&(pred.season<holdout_year)]
    calibrator=None
    if len(dev_selected)>=100 and dev_selected.home_cover.nunique()>1:
        from sklearn.linear_model import LogisticRegression
        raw=np.clip(dev_selected.p_home_cover.to_numpy(),1e-5,1-1e-5)
        logit=np.log(raw/(1-raw)).reshape(-1,1)
        calibrator=LogisticRegression(C=1.,max_iter=500).fit(logit,dev_selected.home_cover.astype(int))
    return pred, metric_df, selected, {"models": bank, "calibrator":calibrator, "feature_columns": feature_map, "history_rows":len(d), "seasons":years, "holdout_season":holdout_year}


def fetch_current_odds(api_key: str, sports: list[str]) -> pd.DataFrame:
    rows=[]
    for sport in sports:
        payload=api_get(f"{ODDS}/sports/{SPORT_KEYS[sport]}/odds/", {"apiKey":api_key,"regions":"us","markets":"spreads,totals","oddsFormat":"american","dateFormat":"iso"})
        for game in payload:
            for book in game.get("bookmakers",[]):
                for market in book.get("markets",[]):
                    if market.get("key") not in ("spreads","totals"): continue
                    for outcome in market.get("outcomes",[]):
                        rows.append({"sport":sport,"game_id":game.get("id"),"start_time":game.get("commence_time"),"home_team":game.get("home_team"),"away_team":game.get("away_team"),"book":book.get("title"),"updated":book.get("last_update"),"market":market.get("key"),"name":outcome.get("name"),"point":outcome.get("point"),"price":outcome.get("price")})
    return pd.DataFrame(rows)


def fetch_forecast_weather(board: pd.DataFrame) -> pd.DataFrame:
    """Fetch kickoff-hour forecast context for live outdoor games via Open-Meteo.

    This is displayed with the live slate. Historical observed weather is not
    substituted for archived forecasts in model training, which would leak
    information that was not available at pick time.
    """
    cols=["game_id","forecast_temp_c","forecast_wind_kmh","forecast_precip_mm","forecast_precip_probability"]
    if board.empty or not {"venue_lat","venue_lon","game_date"}.issubset(board.columns):return pd.DataFrame(columns=cols)
    d=board[["game_id","game_date","venue_lat","venue_lon"]+[c for c in ["venue_dome"] if c in board]].copy()
    d["venue_lat"]=pd.to_numeric(d.venue_lat,errors="coerce");d["venue_lon"]=pd.to_numeric(d.venue_lon,errors="coerce")
    d=d.dropna(subset=["venue_lat","venue_lon","game_date"])
    if d.empty:return pd.DataFrame(columns=cols)
    coords=d[["venue_lat","venue_lon"]].drop_duplicates().reset_index(drop=True)
    resp=requests.get("https://api.open-meteo.com/v1/forecast",params={
        "latitude":",".join(f"{x:.4f}" for x in coords.venue_lat),
        "longitude":",".join(f"{x:.4f}" for x in coords.venue_lon),
        "hourly":"temperature_2m,wind_speed_10m,precipitation,precipitation_probability",
        "forecast_days":16,"timezone":"UTC",
    },timeout=45)
    resp.raise_for_status();payload=resp.json()
    responses=payload if isinstance(payload,list) else [payload]
    forecast_map={}
    for _,loc in coords.iterrows():
        key=(round(float(loc.venue_lat),4),round(float(loc.venue_lon),4))
        match=next((r for r in responses if round(float(r.get("latitude",0)),4)==key[0] and round(float(r.get("longitude",0)),4)==key[1]),None)
        if match is None and len(responses)==len(coords):match=responses[len(forecast_map)]
        forecast_map[key]=match
    rows=[]
    for _,r in d.iterrows():
        dome=r.get("venue_dome",False)
        if pd.notna(dome) and bool(dome):
            rows.append({"game_id":r.game_id,"forecast_temp_c":np.nan,"forecast_wind_kmh":0.,"forecast_precip_mm":0.,"forecast_precip_probability":0.})
            continue
        key=(round(float(r.venue_lat),4),round(float(r.venue_lon),4));fc=forecast_map.get(key)
        if not fc or "hourly" not in fc:continue
        hourly=fc["hourly"];times=pd.to_datetime(hourly.get("time",[]),utc=True,errors="coerce")
        target=pd.to_datetime(r.game_date,utc=True,errors="coerce")
        if pd.isna(target) or len(times)==0:continue
        idx=int(np.argmin(np.abs((times-target).total_seconds())))
        item={"game_id":r.game_id}
        for source,dest in [("temperature_2m","forecast_temp_c"),("wind_speed_10m","forecast_wind_kmh"),("precipitation","forecast_precip_mm"),("precipitation_probability","forecast_precip_probability")]:
            vals=hourly.get(source,[]);item[dest]=float(vals[idx]) if idx<len(vals) and vals[idx] is not None else np.nan
        rows.append(item)
    return pd.DataFrame(rows,columns=cols)


def normalize_team(value: Any) -> str:
    s=re.sub(r"[^a-z0-9 ]"," ",str(value).lower())
    s=re.sub(r"\b(university|college|the|of)\b"," ",s)
    return " ".join(s.split())


NFL_ALIAS={
    "arizona cardinals":"ARI","atlanta falcons":"ATL","baltimore ravens":"BAL","buffalo bills":"BUF",
    "carolina panthers":"CAR","chicago bears":"CHI","cincinnati bengals":"CIN","cleveland browns":"CLE",
    "dallas cowboys":"DAL","denver broncos":"DEN","detroit lions":"DET","green bay packers":"GB",
    "houston texans":"HOU","indianapolis colts":"IND","jacksonville jaguars":"JAX","kansas city chiefs":"KC",
    "las vegas raiders":"LV","los angeles chargers":"LAC","los angeles rams":"LA","miami dolphins":"MIA",
    "minnesota vikings":"MIN","new england patriots":"NE","new orleans saints":"NO","new york giants":"NYG",
    "new york jets":"NYJ","philadelphia eagles":"PHI","pittsburgh steelers":"PIT","san francisco 49ers":"SF",
    "seattle seahawks":"SEA","tampa bay buccaneers":"TB","tennessee titans":"TEN","washington commanders":"WAS",
}


def resolve_team_name(name: str, history_names: list[str], sport: str) -> str:
    if sport=="NFL":
        key=NFL_ALIAS.get(normalize_team(name))
        if key and key in history_names:return key
    normalized=normalize_team(name)
    by_normalized={normalize_team(n):n for n in history_names}
    if normalized in by_normalized:return by_normalized[normalized]
    prefix=[n for n in history_names if normalize_team(n).startswith(normalized) or normalized.startswith(normalize_team(n))]
    if prefix:return sorted(prefix,key=lambda n:len(normalize_team(n)),reverse=True)[0]
    from difflib import get_close_matches
    match=get_close_matches(normalized,list(by_normalized),n=1,cutoff=.68)
    return by_normalized[match[0]] if match else name


def make_current_board(odds: pd.DataFrame, history: pd.DataFrame, model_bank: dict[str,Any], selected: str, calibrator: Any = None, feature_map: dict[str,list[str]] | None = None) -> pd.DataFrame:
    if odds.empty: return pd.DataFrame()
    spread=odds[odds.market=="spreads"].copy()
    totals=odds[odds.market=="totals"].copy()
    rows=[]
    for gid,g in spread.groupby("game_id"):
        home,away=g.iloc[0].home_team,g.iloc[0].away_team
        hp=pd.to_numeric(g.loc[g["name"]==home,"point"],errors="coerce").dropna()
        ap=pd.to_numeric(g.loc[g["name"]==away,"point"],errors="coerce").dropna()
        if hp.empty or ap.empty: continue
        home_line=half_line(hp.median()); away_line=-home_line
        total=totals[(totals.game_id==gid)&(totals["name"]=="Over")].point
        tot=float(pd.to_numeric(total,errors="coerce").median()) if not total.empty else np.nan
        updated=pd.to_datetime(g.updated,errors="coerce",utc=True).max()
        rows.append({"sport":g.iloc[0].sport,"game_id":gid,"start_time":g.iloc[0].start_time,"home_team":home,"away_team":away,"home_line":home_line,"away_line":away_line,"home_spread":home_line,"total_line":tot,"line_updated":updated,"home_score":np.nan,"away_score":np.nan,"neutral_site":False})
    board=pd.DataFrame(rows)
    if board.empty:return board
    board["game_date"]=pd.to_datetime(board.start_time,errors="coerce",utc=True).dt.tz_convert(None)
    board["season"]=board.game_date.dt.year
    hist=history[history.sport==board.iloc[0].sport].copy()
    hist_names=list(set(hist.home_team.astype(str))|set(hist.away_team.astype(str)))
    board["home_team_model"]=board.home_team.map(lambda n:resolve_team_name(n,hist_names,board.iloc[0].sport))
    board["away_team_model"]=board.away_team.map(lambda n:resolve_team_name(n,hist_names,board.iloc[0].sport))
    meta_cols=[c for c in ["game_date","home_team","away_team","venue","home_coach","away_coach","temperature","wind","humidity","precipitation","home_spread_open","venue_lat","venue_lon","venue_elevation","venue_dome","city","state","timezone"] if c in hist]
    if len(meta_cols)>3:
        meta=hist[meta_cols].dropna(subset=["game_date"]).copy()
        lookup=[]
        for _,r in board.iterrows():
            q=meta[(meta.home_team.astype(str)==r.home_team_model)&(meta.away_team.astype(str)==r.away_team_model)]
            if q.empty:lookup.append({"game_id":r.game_id});continue
            q=q.assign(_delta=(pd.to_datetime(q.game_date)-pd.to_datetime(r.game_date)).abs().dt.total_seconds())
            best=q.sort_values("_delta").iloc[0]
            item={"game_id":r.game_id}
            for c in ["venue","home_coach","away_coach","temperature","wind","humidity","precipitation","home_spread_open","venue_lat","venue_lon","venue_elevation","venue_dome","city","state","timezone"]:
                if c in best:item[c]=best[c]
            lookup.append(item)
        board=board.merge(pd.DataFrame(lookup),on="game_id",how="left",suffixes=("","_meta"))
    live_cols=["game_id","sport","season","game_date","home_team_model","away_team_model","home_line","home_spread_open","total_line","home_spread","home_score","away_score","neutral_site","venue_lat","venue_lon","venue_elevation","venue_dome"]
    for c in live_cols:
        if c not in board:board[c]=np.nan
    if board.iloc[0].sport=="NFL":
        board["venue_lat"],board["venue_lon"],board["venue_elevation"]=_nfl_venue_columns(board.assign(home_team=board.home_team_model))
        board["venue_dome"]=board.home_team_model.astype(str).isin(NFL_DOME)
    live_cols += [c for c in ["home_coach","away_coach"] if c in board]
    live=board[live_cols].rename(columns={"home_team_model":"home_team","away_team_model":"away_team"}).copy()
    live["game_id"]="live_"+live.game_id.astype(str)
    combined=pd.concat([hist,live],ignore_index=True,sort=False)
    enriched=add_pregame_features(combined)
    live_ids=set(live.game_id)
    board_features=enriched[enriched.game_id.isin(live_ids)].copy()
    board_features["game_id"]=board_features.game_id.str.replace("^live_","",regex=True)
    board=board.merge(board_features[["game_id"]+FEATURES],on="game_id",how="left",suffixes=("","_features"))
    for c in FEATURES:
        if c+"_features" in board:
            board[c]=pd.to_numeric(board[c+"_features"],errors="coerce").fillna(0)
            board=board.drop(columns=[c+"_features"])
        elif c not in board:
            board[c]=0
    probs=[]
    for name,model in model_bank.items():
        cols=(feature_map or {}).get(name,FEATURES)
        probs.append(model.predict_proba(board[cols])[:,1])
        board[f"p_home_{name}"]=probs[-1]
    chosen_p=board[f"p_home_{selected}"].clip(1e-5,1-1e-5).to_numpy()
    if calibrator is not None:
        logit=np.log(chosen_p/(1-chosen_p)).reshape(-1,1)
        board["p_home_cover"]=calibrator.predict_proba(logit)[:,1]
    else:
        board["p_home_cover"]=chosen_p
    board["p_away_cover"]=1-board.p_home_cover
    board["best_side"]=np.where(board.p_home_cover>=.5,board.home_team,board.away_team)
    board["best_cover_probability"]=np.maximum(board.p_home_cover,board.p_away_cover)
    board["model_confidence"]=np.abs(board.p_home_cover-.5)*2
    # Ranking currently uses probability + bookmaker agreement; market edge is included as a separate transparency field.
    sides=np.where(board.p_home_cover>=.5,"home","away")
    board["model_agreement"]=[float(np.mean([(p[i]>=.5)==(board.p_home_cover.iloc[i]>=.5) for p in probs])) for i in range(len(board))]
    board["model_count"]=len(probs)
    board["selected_model_probability"]=[float(board.loc[i,f"p_home_{selected}"] if sides[i]=="home" else 1-board.loc[i,f"p_home_{selected}"]) for i in range(len(board))]
    board["rank_score"]=board.best_cover_probability+0.005*board.model_agreement
    return board.sort_values(["rank_score","line_updated"],ascending=[False,False]).reset_index(drop=True)
