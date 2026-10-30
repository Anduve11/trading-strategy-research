"""NFL + FBS weekly pick-pool research dashboard.

Historical sources are useful for model research, but historical closing lines are
not the same thing as the user's 10:00 a.m. lock snapshot. The app therefore keeps
the lock-line ledger separate and supports importing the actual pool slate.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import math
import os
from zoneinfo import ZoneInfo
from typing import Any

import numpy as np
import pandas as pd
import requests
import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "sports_pool"
DATA.mkdir(parents=True, exist_ok=True)
NFL_SCHEDULE_URL = "https://github.com/nflverse/nfldata/releases/download/schedules/games.csv"
CFBD_BASE = "https://api.collegefootballdata.com"
TIMEOUT = 35
POOL_TZ = ZoneInfo("America/Denver")


def get_secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, ""))
    except Exception:
        return ""


def even_line_to_half(line: float | None, team_is_favorite: bool | None = None) -> float | None:
    """Move an integer spread to a half point, away from zero.

    Spread is stored from the selected team's perspective: negative=favorite,
    positive=underdog. A -3 favorite becomes -3.5; a +3 underdog becomes +3.5.
    The two sides remain opposite, with no push at that exact margin.
    """
    if line is None or pd.isna(line):
        return None
    value = float(line)
    if math.isclose(value % 1, 0.0, abs_tol=1e-9):
        if team_is_favorite is None:
            team_is_favorite = value < 0
        value += -0.5 if team_is_favorite else 0.5
    return value


def read_lock_ledger() -> pd.DataFrame:
    p = DATA / "lock_lines.csv"
    if not p.exists():
        return pd.DataFrame(columns=["sport", "season", "week", "game_id", "game_date", "home_team", "away_team", "home_line", "away_line", "home_moneyline", "away_moneyline", "captured_at", "source"])
    df = pd.read_csv(p)
    for col in ("game_id", "away_line", "source"):
        if col not in df:
            df[col] = "" if col != "away_line" else np.nan
    missing_away = df.away_line.isna() & df.home_line.notna()
    df.loc[missing_away, "away_line"] = -pd.to_numeric(df.loc[missing_away, "home_line"], errors="coerce")
    return df


def save_lock_ledger(df: pd.DataFrame) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA / "lock_lines.csv", index=False)


def read_picks() -> pd.DataFrame:
    p = DATA / "pool_picks.csv"
    if not p.exists():
        return pd.DataFrame(columns=["sport", "season", "week", "game_id", "captured_at", "pick_side", "team", "opponent", "raw_line", "pool_line", "saved_at"])
    return pd.read_csv(p)


def save_picks(df: pd.DataFrame) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA / "pool_picks.csv", index=False)


@st.cache_data(ttl=3600, show_spinner=False)
def load_nfl_schedules() -> pd.DataFrame:
    """nflverse schedules contain game results, spread, venue, coaches, and weather."""
    d = pd.read_csv(NFL_SCHEDULE_URL, low_memory=False)
    d = d.rename(columns={"season_type": "season_type", "week": "week"})
    return d


def cfbd_get(endpoint: str, params: dict[str, Any], token: str) -> Any:
    resp = requests.get(
        f"{CFBD_BASE}/{endpoint.lstrip('/')}", params=params,
        headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT,
    )
    if resp.status_code == 401:
        raise RuntimeError("CollegeFootballData rejected the token. Check API access and token in Streamlit secrets.")
    if resp.status_code == 429:
        raise RuntimeError("CollegeFootballData rate limit reached. Wait before trying again.")
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=3600, show_spinner=False)
def load_cfbd_games(season: int, token: str) -> pd.DataFrame:
    games = cfbd_get("games", {"year": season, "seasonType": "both", "classification": "fbs"}, token)
    df = pd.json_normalize(games, sep="_")
    # Endpoint response fields have varied over time; normalize stable columns.
    aliases = {"homeTeam": "home_team", "awayTeam": "away_team", "homePoints": "home_score", "awayPoints": "away_score", "startDate": "game_date", "startTime": "game_date", "neutralSite": "neutral_site", "venue": "venue", "week": "week"}
    df = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns})
    df["season"] = season
    return df


@st.cache_data(ttl=86400, show_spinner=False)
def load_cfbd_season_detail(season: int, token: str) -> dict[str, pd.DataFrame]:
    # Keep separate endpoints so a missing supplemental source never blocks games.
    data: dict[str, pd.DataFrame] = {}
    for key, endpoint, params in [
        ("lines", "lines", {"year": season}),
        ("weather", "games/weather", {"year": season}),
        ("stats", "stats/season", {"year": season}),
        ("coaches", "coaches", {"year": season}),
        ("ratings", "ratings/sp", {"year": season}),
        ("elo", "ratings/elo", {"year": season}),
    ]:
        try:
            payload = cfbd_get(endpoint, params, token)
            data[key] = pd.json_normalize(payload, sep="_") if isinstance(payload, list) else pd.DataFrame()
        except Exception as exc:
            data[key] = pd.DataFrame()
            data[f"{key}_error"] = pd.DataFrame([{"message": str(exc)}])
    return data


def cfbd_lines_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Reduce CFBD's nested provider quotes to one median home spread per game."""
    if raw.empty:
        return pd.DataFrame(columns=["id", "home_spread"])
    rows = []
    for _, game in raw.iterrows():
        quotes = game.get("lines", [])
        if not isinstance(quotes, list):
            quotes = []
        values = []
        for quote in quotes:
            if not isinstance(quote, dict):
                continue
            spread = quote.get("spread")
            if spread is None:
                continue
            try:
                value = float(spread)
            except (TypeError, ValueError):
                continue
            # CFBD spread is the home team's handicap in the lines response.
            values.append(value)
        if values:
            rows.append({"id": game.get("id"), "home_spread": float(np.median(values))})
    return pd.DataFrame(rows, columns=["id", "home_spread"])


def prepare_cfbd_games(games: pd.DataFrame, details: dict[int, dict[str, pd.DataFrame]]) -> pd.DataFrame:
    """Normalize game rows and attach the per-game median available spread."""
    d = games.copy()
    for col in ("home_score", "away_score"):
        if col in d:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    d["game_date"] = pd.to_datetime(d.get("game_date"), errors="coerce", utc=True).dt.tz_convert(None)
    d["home_win"] = (d.home_score > d.away_score).astype(float)
    d.loc[d.home_score.isna() | d.away_score.isna(), "home_win"] = np.nan
    d["sport"] = "NCAAF"
    all_lines = []
    for season, blocks in details.items():
        lines = cfbd_lines_frame(blocks.get("lines", pd.DataFrame()))
        if not lines.empty:
            lines["season"] = season
            all_lines.append(lines)
    if all_lines and "id" in d:
        d = d.merge(pd.concat(all_lines).drop_duplicates(["season", "id"]), how="left", on=["season", "id"], suffixes=("", "_market"))
    elif "home_spread" not in d:
        d["home_spread"] = np.nan
    d["neutral_site"] = d.get("neutral_site", False)
    return d


def parse_nfl_rows(games: pd.DataFrame, season_min: int, season_max: int) -> pd.DataFrame:
    d = games[(games.season >= season_min) & (games.season <= season_max)].copy()
    if "game_type" in d:
        d = d[d.game_type.isin(["REG", "POST"])].copy()
    # nflverse spread_line is the home team's closing spread; convert to our team-perspective rows.
    d["game_date"] = pd.to_datetime(d.get("gameday"), errors="coerce")
    d["sport"] = "NFL"
    d["home_score"] = pd.to_numeric(d.get("home_score"), errors="coerce")
    d["away_score"] = pd.to_numeric(d.get("away_score"), errors="coerce")
    d["home_spread"] = pd.to_numeric(d.get("spread_line"), errors="coerce")
    d["home_total"] = pd.to_numeric(d.get("total_line"), errors="coerce")
    d["home_win"] = (d.home_score > d.away_score).astype(float)
    d.loc[d.home_score.isna() | d.away_score.isna(), "home_win"] = np.nan
    return d


def build_team_history(games: pd.DataFrame) -> pd.DataFrame:
    """Leak-resistant pregame team-form rows from final scores, sorted chronologically."""
    rows = []
    for _, g in games.sort_values("game_date").iterrows():
        for side in ("home", "away"):
            team = g.get(f"{side}_team")
            opp = g.get("away_team" if side == "home" else "home_team")
            score = g.get(f"{side}_score")
            opp_score = g.get("away_score" if side == "home" else "home_score")
            if pd.isna(team) or pd.isna(score) or pd.isna(opp_score):
                continue
            season = g.get("season", pd.Timestamp(g.game_date).year)
            rows.append({"date": g.game_date, "season": season, "team": str(team), "opponent": str(opp), "points": float(score), "points_allowed": float(opp_score), "win": float(score > opp_score), "margin": float(score - opp_score)})
    hist = pd.DataFrame(rows)
    if hist.empty:
        return hist
    hist = hist.sort_values("date")
    hist["games_before"] = hist.groupby("team").cumcount()
    for col in ("win", "margin", "points", "points_allowed"):
        hist[f"{col}_last5"] = hist.groupby("team")[col].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
        hist[f"{col}_season"] = hist.groupby(["team", "season"])[col].transform(lambda s: s.shift(1).expanding(min_periods=1).mean())
    return hist


def make_model_frame(games: pd.DataFrame, line_col: str = "home_spread") -> pd.DataFrame:
    """Join pregame form. Home is modeled; training/testing splits must be by season."""
    d = games.copy().sort_values("game_date")
    h = build_team_history(d)
    if h.empty:
        return pd.DataFrame()
    cols = ["date", "team"] + [c for c in h if c.endswith(("_last5", "_season"))]
    hf = h[cols].rename(columns={"date": "game_date"})
    af = hf.rename(columns={c: f"away_{c}" for c in hf.columns if c not in ("game_date", "team")}).rename(columns={"team": "away_team"})
    hf = hf.rename(columns={c: f"home_{c}" for c in hf.columns if c not in ("game_date", "team")}).rename(columns={"team": "home_team"})
    d = d.merge(hf, how="left", on=["game_date", "home_team"], suffixes=("", "_hist")).merge(af, how="left", on=["game_date", "away_team"])
    d["home_advantage"] = (~d.get("neutral_site", pd.Series(False, index=d.index)).fillna(False)).astype(int)
    if line_col not in d: d[line_col] = np.nan
    d["home_line_raw"] = pd.to_numeric(d[line_col], errors="coerce")
    d["home_line"] = d.home_line_raw.map(even_line_to_half)
    d["form_margin_diff"] = d.get("home_margin_last5", 0) - d.get("away_margin_last5", 0)
    d["form_win_diff"] = d.get("home_win_last5", 0) - d.get("away_win_last5", 0)
    d["season_margin_diff"] = d.get("home_margin_season", 0) - d.get("away_margin_season", 0)
    d["season_win_diff"] = d.get("home_win_season", 0) - d.get("away_win_season", 0)
    d["home_win"] = pd.to_numeric(d.get("home_win"), errors="coerce")
    return d


def walk_forward(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Year-by-year walk-forward evaluation with a transparent, no-fit baseline."""
    def fit_predict(train_x: pd.DataFrame, train_y: pd.Series, test_x: pd.DataFrame, penalty: float) -> np.ndarray:
        # Small, deterministic L2 logistic regression using only NumPy.
        medians = train_x.median().fillna(0.0)
        tx = train_x.fillna(medians).to_numpy(dtype=float)
        vx = test_x.fillna(medians).to_numpy(dtype=float)
        means, scales = tx.mean(axis=0), tx.std(axis=0)
        scales[scales == 0] = 1.0
        tx, vx = (tx-means)/scales, (vx-means)/scales
        tx = np.column_stack([np.ones(len(tx)), tx])
        vx = np.column_stack([np.ones(len(vx)), vx])
        y = train_y.to_numpy(dtype=float)
        beta = np.zeros(tx.shape[1], dtype=float)
        reg = np.eye(tx.shape[1]) * penalty
        reg[0, 0] = 0.0
        for _ in range(1800):
            z = np.clip(tx @ beta, -25, 25)
            p = 1.0 / (1.0 + np.exp(-z))
            grad = (tx.T @ (p-y)) / len(y) + reg @ beta
            beta -= 0.08 * grad
        z = np.clip(vx @ beta, -25, 25)
        return 1.0 / (1.0 + np.exp(-z))
    features = ["home_line", "home_advantage", "form_margin_diff", "form_win_diff", "season_margin_diff", "season_win_diff"]
    d = frame.dropna(subset=["home_win", "game_date", "home_line"]).copy()
    if "season" not in d:
        d["season"] = pd.to_datetime(d.game_date).dt.year
    out = []
    seasons = sorted(d.season.unique())
    for yr in seasons:
        train = d[d.season < yr]
        test = d[d.season == yr]
        if len(train) < 100 or test.empty or train.home_win.nunique() < 2:
            continue
        test = test.copy()
        test["p_home_model"] = fit_predict(train[features], train.home_win.astype(int), test[features], penalty=0.04)
        # Spread-only baseline is still a probabilistic reference, with logistic fit to prior seasons.
        test["p_home_spread"] = fit_predict(train[["home_line", "home_advantage"]], train.home_win.astype(int), test[["home_line", "home_advantage"]], penalty=0.02)
        out.append(test)
    if not out:
        return pd.DataFrame(), pd.DataFrame()
    pred = pd.concat(out, ignore_index=True)
    summary = []
    for label, pcol in [("Spread + home", "p_home_spread"), ("Pregame form + spread", "p_home_model")]:
        p = pred[pcol].clip(1e-6, 1-1e-6)
        y = pred.home_win
        summary.append({"model": label, "games": len(pred), "accuracy": float(((p >= .5) == y).mean()), "log_loss": float(-(y*np.log(p)+(1-y)*np.log(1-p)).mean()), "brier_score": float(((p-y)**2).mean())})
    return pred, pd.DataFrame(summary)


def load_current_odds(sport_key: str, api_key: str) -> pd.DataFrame:
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    r = requests.get(url, params={"apiKey": api_key, "regions": "us", "markets": "spreads,totals,h2h", "oddsFormat": "american", "dateFormat": "iso"}, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    rows = []
    for game in payload:
        for book in game.get("bookmakers", []):
            for market in book.get("markets", []):
                for outcome in market.get("outcomes", []):
                    rows.append({"game_id": game.get("id"), "sport_key": game.get("sport_key"), "commence_time": game.get("commence_time"), "home_team": game.get("home_team"), "away_team": game.get("away_team"), "bookmaker": book.get("title"), "last_update": book.get("last_update"), "market": market.get("key"), "team_or_outcome": outcome.get("name"), "point": outcome.get("point"), "price": outcome.get("price")})
    return pd.DataFrame(rows)


def odds_to_lock_rows(odds: pd.DataFrame, sport: str, season: int, week: int, bookmaker: str) -> pd.DataFrame:
    """Convert a fetched spread snapshot into the pool's home/away line ledger."""
    expected_key = "americanfootball_nfl" if sport == "NFL" else "americanfootball_ncaaf"
    d = odds[(odds.market == "spreads") & (odds.sport_key == expected_key)].copy()
    if bookmaker != "Median across books":
        d = d[d.bookmaker == bookmaker]
    result = []
    for game_id, g in d.groupby("game_id", dropna=False):
        home = g.iloc[0].home_team
        away = g.iloc[0].away_team
        home_points = pd.to_numeric(g.loc[g.team_or_outcome == home, "point"], errors="coerce").dropna()
        away_points = pd.to_numeric(g.loc[g.team_or_outcome == away, "point"], errors="coerce").dropna()
        if home_points.empty or away_points.empty:
            continue
        book_names = ", ".join(sorted(g.bookmaker.dropna().unique())) if bookmaker == "Median across books" else bookmaker
        provider_updates = pd.to_datetime(g.last_update, errors="coerce", utc=True).dropna()
        provider_time = provider_updates.max().isoformat() if not provider_updates.empty else "unknown"
        result.append({"sport":sport,"season":season,"week":week,"game_id":game_id,"game_date":pd.to_datetime(g.iloc[0].commence_time, utc=True).date().isoformat(),"home_team":home,"away_team":away,"home_line":float(home_points.median()),"away_line":float(away_points.median()),"captured_at":datetime.now(POOL_TZ).isoformat(timespec="seconds"),"source":f"The Odds API · {book_names} · provider updated {provider_time}"})
    return pd.DataFrame(result)


def main() -> None:
    st.set_page_config(page_title="Sunday Slate Lab", page_icon="🏈", layout="wide")
    st.title("🏈 Sunday Slate Lab")
    st.caption("NFL + FBS college football weekly pool research · pick 10 · historical data and live slate tools")
    st.info("Research support only. Historical close lines are not 10:00 a.m. lock lines. Save actual lock snapshots prospectively before using them to judge the model.")
    page = st.sidebar.radio("Workspace", ["Weekly slate", "5-year research", "Lock-line archive", "Data guide"])

    if page == "Weekly slate":
        st.subheader("This week's board")
        st.write("Set the lock time to **10:00 a.m. America/Denver**. Capture or import the lines at that moment, then the app applies the half-point pool rule to integer spreads.")
        st.caption("We can retrieve current market odds through The Odds API when a key is configured. Snapshot timing is controlled by you: the returned timestamp must be at or before the pool lock.")
        odds_key = get_secret("ODDS_API_KEY") or os.getenv("ODDS_API_KEY", "")
        if odds_key:
            sports = st.multiselect("Leagues", ["NFL", "NCAAF"], default=["NFL", "NCAAF"])
            keys = {"NFL": "americanfootball_nfl", "NCAAF": "americanfootball_ncaaf"}
            if st.button("Fetch current odds", type="primary"):
                gathered = []
                for sport in sports:
                    try:
                        gathered.append(load_current_odds(keys[sport], odds_key))
                    except Exception as exc:
                        st.warning(f"{sport}: {exc}")
                odds = pd.concat(gathered, ignore_index=True) if gathered else pd.DataFrame()
                if not odds.empty:
                    st.session_state["current_odds"] = odds
            odds = st.session_state.get("current_odds", pd.DataFrame())
            if not odds.empty:
                st.dataframe(odds, use_container_width=True, hide_index=True)
                st.download_button("Download current odds CSV", odds.to_csv(index=False), "current_odds.csv", "text/csv")
                st.markdown("##### Save this market snapshot to your pool board")
                available_books = sorted(odds.bookmaker.dropna().unique())
                book_choice = st.selectbox("Sportsbook snapshot", ["Median across books"] + available_books)
                c1,c2,c3 = st.columns(3)
                board_sport = c1.selectbox("Board sport", ["NFL","NCAAF"], key="odds_board_sport")
                board_season = c2.number_input("Board season", 2000, 2100, date.today().year, key="odds_board_season")
                board_week = c3.number_input("Board week", 1, 30, 1, key="odds_board_week")
                if st.button("Save current spread snapshot to lock archive"):
                    new_rows = odds_to_lock_rows(odds, board_sport, int(board_season), int(board_week), book_choice)
                    if new_rows.empty:
                        st.warning("No complete spread quotes found for that league and sportsbook.")
                    else:
                        saved = read_lock_ledger()
                        save_lock_ledger(pd.concat([saved, new_rows], ignore_index=True))
                        st.success(f"Saved {len(new_rows)} games. Check provider update time against your 10:00 a.m. lock.")
        else:
            st.warning("Add ODDS_API_KEY to Streamlit secrets for live NFL/NCAAF odds. You can still import your pool lines in Lock-line archive.")
        st.markdown("#### Make your ten picks")
        ledger = read_lock_ledger()
        if ledger.empty:
            st.info("Import or enter the pool board in Lock-line archive first. The selection card uses those saved lock lines.")
        else:
            choices = ledger[["sport", "season", "week"]].drop_duplicates().sort_values(["season", "week", "sport"], ascending=[False, False, True])
            choice_labels = [f"{r.sport} · {int(r.season)} · Week {int(r.week)}" for r in choices.itertuples(index=False)]
            selected_label = st.selectbox("Pool week", choice_labels)
            sel = choices.iloc[choice_labels.index(selected_label)]
            board = ledger[(ledger.sport == sel.sport) & (ledger.season == sel.season) & (ledger.week == sel.week)].copy()
            if "captured_at" in board:
                board = board.sort_values("captured_at").drop_duplicates(["game_id", "home_team", "away_team"], keep="last")
            board = board.reset_index(drop=True)
            board["Game"] = board["away_team"].astype(str) + " @ " + board["home_team"].astype(str)
            if "away_line" not in board:
                board["away_line"] = -pd.to_numeric(board.home_line, errors="coerce")
            board["home_pool_line"] = board.home_line.map(even_line_to_half)
            board["away_pool_line"] = board.away_line.map(even_line_to_half)
            board["Pick"] = "Home"
            board["Select"] = False
            prior = read_picks()
            key = (prior.sport == sel.sport) & (prior.season == sel.season) & (prior.week == sel.week) if not prior.empty else pd.Series(dtype=bool)
            prior_week = prior[key] if not prior.empty else pd.DataFrame()
            if not prior_week.empty:
                for i, row in board.iterrows():
                    match = prior_week[(prior_week.game_id.astype(str) == str(row.get("game_id", ""))) & (prior_week.team.isin([row.home_team, row.away_team]))]
                    if not match.empty:
                        p = match.iloc[-1]
                        board.loc[i, "Select"] = True
                        board.loc[i, "Pick"] = "Home" if p.team == row.home_team else "Away"
            editable = board[["Select", "Game", "Pick", "home_pool_line", "away_pool_line", "captured_at", "source"]].copy()
            selection = st.data_editor(
                editable, hide_index=True, use_container_width=True,
                column_config={"Select": st.column_config.CheckboxColumn("Pick this game"), "Game": st.column_config.TextColumn(disabled=True), "Pick": st.column_config.SelectboxColumn(options=["Home", "Away"]), "home_pool_line": st.column_config.NumberColumn("Home pool line", format="%+.1f", disabled=True), "away_pool_line": st.column_config.NumberColumn("Away pool line", format="%+.1f", disabled=True), "captured_at": st.column_config.TextColumn(disabled=True), "source": st.column_config.TextColumn(disabled=True)},
            )
            count = int(selection["Select"].fillna(False).sum())
            st.write(f"Selected: **{count} / 10**")
            if st.button("Save ten-pick card", type="primary", disabled=count != 10):
                picked = []
                for i, row in selection[selection["Select"].fillna(False)].iterrows():
                    src = board.loc[i]
                    side = row["Pick"]
                    is_home = side == "Home"
                    team = src.home_team if is_home else src.away_team
                    opponent = src.away_team if is_home else src.home_team
                    raw_line = src.get("home_line") if is_home else src.get("away_line")
                    if pd.isna(raw_line) and pd.notna(src.get("home_line")):
                        raw_line = src.home_line if is_home else -float(src.home_line)
                    adjusted = even_line_to_half(raw_line)
                    picked.append({"sport":sel.sport,"season":int(sel.season),"week":int(sel.week),"game_id":src.get("game_id", ""),"captured_at":src.get("captured_at", ""),"pick_side":side,"team":team,"opponent":opponent,"raw_line":raw_line,"pool_line":adjusted,"saved_at":datetime.now(POOL_TZ).isoformat(timespec="seconds")})
                prior = prior[~((prior.sport == sel.sport) & (prior.season == sel.season) & (prior.week == sel.week))] if not prior.empty else prior
                save_picks(pd.concat([prior, pd.DataFrame(picked)], ignore_index=True))
                st.success("Saved all 10 picks with their lock lines.")
            if not prior_week.empty:
                st.markdown("#### Saved card")
                st.dataframe(prior_week, use_container_width=True, hide_index=True)

    elif page == "5-year research":
        sport = st.radio("Sport", ["NFL", "College football (FBS)"], horizontal=True)
        season_max = date.today().year
        season_min = st.slider("First season", min_value=season_max-10, max_value=season_max-1, value=season_max-5)
        if sport == "NFL":
            if st.button("Load NFL data and run walk-forward study", type="primary"):
                with st.spinner("Loading nflverse schedules and fitting season-by-season models..."):
                    try:
                        raw = load_nfl_schedules()
                        games = parse_nfl_rows(raw, season_min, season_max)
                        # Prepare home/away names and expected neutral-site field.
                        games["home_team"] = games.get("home_team")
                        games["away_team"] = games.get("away_team")
                        games["neutral_site"] = games.get("location", "home").eq("neutral") if isinstance(games.get("location"), pd.Series) else False
                        frame = make_model_frame(games)
                        pred, summary = walk_forward(frame)
                        st.session_state["study_games"] = games
                        st.session_state["study_pred"] = pred
                        st.session_state["study_summary"] = summary
                    except Exception as exc:
                        st.error(f"NFL research failed: {exc}")
            if "study_summary" in st.session_state:
                summary = st.session_state["study_summary"]
                if summary.empty:
                    st.warning("There was not enough clean historical data to run the walk-forward study.")
                else:
                    st.dataframe(summary.style.format({"accuracy":"{:.1%}","log_loss":"{:.3f}","brier_score":"{:.3f}"}), use_container_width=True, hide_index=True)
                    st.caption("Each test season is predicted using only earlier seasons. Accuracy alone is not evidence of an edge; compare log loss and Brier score against the spread baseline.")
                    pred = st.session_state["study_pred"]
                    st.download_button("Download out-of-sample game predictions", pred.to_csv(index=False), "nfl_walk_forward_predictions.csv", "text/csv")
                    st.dataframe(pred[[c for c in ["season","week","game_date","away_team","home_team","home_spread","home_score","away_score","p_home_spread","p_home_model"] if c in pred]], use_container_width=True, hide_index=True)
                    games = st.session_state["study_games"]
                    st.markdown("#### Pregame context available in nflverse schedule source")
                    avail = [c for c in ["week","gameday","gametime","stadium","location","roof","surface","temp","wind","home_coach","away_coach","spread_line","total_line"] if c in games]
                    st.dataframe(games[avail].head(30), use_container_width=True, hide_index=True)
        else:
            token = st.text_input("CollegeFootballData API token", value=(get_secret("CFBD_API_KEY") or os.getenv("CFBD_API_KEY", "")), type="password", help="Stored only in your session unless you add it to Streamlit secrets.")
            if not token:
                st.warning("CFBD API token is needed for historical FBS games, lines, ratings, coaches, and game weather. Set CFBD_API_KEY in Streamlit secrets.")
            if st.button("Load college football seasons", type="primary", disabled=not bool(token)):
                frames = []
                detail = {}
                errors = []
                for yr in range(season_min, season_max+1):
                    try:
                        frames.append(load_cfbd_games(yr, token))
                        detail[yr] = load_cfbd_season_detail(yr, token)
                    except Exception as exc:
                        errors.append(f"{yr}: {exc}")
                if frames:
                    st.session_state["cfb_games"] = pd.concat(frames, ignore_index=True)
                    st.session_state["cfb_detail"] = detail
                for msg in errors: st.warning(msg)
            if "cfb_games" in st.session_state:
                cg = prepare_cfbd_games(st.session_state["cfb_games"], st.session_state["cfb_detail"])
                st.metric("Games loaded", len(cg))
                if st.button("Run college walk-forward study", type="primary"):
                    try:
                        frame = make_model_frame(cg)
                        pred, summary = walk_forward(frame)
                        st.session_state["cfb_pred"] = pred
                        st.session_state["cfb_summary"] = summary
                    except Exception as exc:
                        st.error(f"College walk-forward research failed: {exc}")
                if "cfb_summary" in st.session_state:
                    summary = st.session_state["cfb_summary"]
                    if summary.empty:
                        st.warning("Not enough clean games with results and spreads to run a walk-forward comparison.")
                    else:
                        st.dataframe(summary.style.format({"accuracy":"{:.1%}","log_loss":"{:.3f}","brier_score":"{:.3f}"}), use_container_width=True, hide_index=True)
                        st.caption("The model tests each season using only earlier seasons. CFBD provider lines are a historical market proxy, not proof they match your 10 a.m. pool board.")
                        pred = st.session_state["cfb_pred"]
                        cols = [c for c in ["season","week","game_date","away_team","home_team","home_spread","home_score","away_score","p_home_spread","p_home_model"] if c in pred]
                        st.dataframe(pred[cols], use_container_width=True, hide_index=True)
                        st.download_button("Download college out-of-sample predictions", pred.to_csv(index=False), "college_walk_forward_predictions.csv", "text/csv")
                st.dataframe(cg.head(50), use_container_width=True, hide_index=True)
                if st.button("Show supplemental data coverage"):
                    for yr, blocks in st.session_state["cfb_detail"].items():
                        st.write(f"**{yr}**", {k: len(v) for k,v in blocks.items() if not k.endswith("_error")})
                st.download_button("Download college schedule", cg.to_csv(index=False), "college_football_games.csv", "text/csv")

    elif page == "Lock-line archive":
        st.subheader("Capture the lines your pool actually receives")
        st.write("Import a CSV after lines lock, or add a snapshot manually. Save odds with source timestamp and bookmaker. Half-point adjusted lines are computed consistently in the display.")
        ledger = read_lock_ledger()
        template = pd.DataFrame(columns=["sport","season","week","game_id","game_date","home_team","away_team","home_line","away_line","home_moneyline","away_moneyline","captured_at","source"])
        st.download_button("Download CSV template", template.to_csv(index=False), "pool_lock_line_template.csv", "text/csv")
        upload = st.file_uploader("Import lock-line CSV", type="csv")
        if upload:
            incoming = pd.read_csv(upload)
            required = {"sport","season","week","game_date","home_team","away_team","home_line","captured_at","source"}
            missing = required - set(incoming.columns)
            if missing:
                st.error("Missing columns: " + ", ".join(sorted(missing)))
            elif st.button("Append imported lock lines"):
                ledger = pd.concat([ledger, incoming], ignore_index=True).drop_duplicates(subset=["sport","season","week","game_id","captured_at","home_team","away_team"], keep="last")
                save_lock_ledger(ledger)
                st.success(f"Saved {len(incoming)} rows.")
        st.markdown("#### Manual line entry")
        with st.form("manual_line"):
            c1,c2,c3,c4 = st.columns(4)
            sport = c1.selectbox("Sport", ["NFL","NCAAF"])
            season = c2.number_input("Season", 2000, 2100, date.today().year, step=1)
            week = c3.number_input("Week", 1, 30, 1, step=1)
            game_date = c4.date_input("Game date", date.today())
            c5,c6,c7,c8 = st.columns(4)
            home = c5.text_input("Home team")
            away = c6.text_input("Away team")
            hline = c7.number_input("Home spread (e.g. -3 favorite, +3 dog)", value=0.0, step=0.5)
            aline = c8.number_input("Away spread", value=0.0, step=0.5)
            captured = st.text_input("Captured at (include timezone)", value=datetime.now(POOL_TZ).isoformat(timespec="minutes"))
            source = st.text_input("Source/bookmaker", value="Pool board")
            submit = st.form_submit_button("Save game line")
        if submit:
            row = {"sport":sport,"season":int(season),"week":int(week),"game_id":"","game_date":game_date.isoformat(),"home_team":home,"away_team":away,"home_line":hline,"away_line":aline,"captured_at":captured,"source":source}
            ledger = pd.concat([ledger, pd.DataFrame([row])], ignore_index=True)
            save_lock_ledger(ledger)
            st.success("Saved lock-line record.")
        if not ledger.empty:
            shown = ledger.copy()
            shown["home_pool_line"] = shown.home_line.map(lambda x: even_line_to_half(x, float(x)<0 if pd.notna(x) else None))
            if "away_line" in shown:
                shown["away_pool_line"] = shown.away_line.map(lambda x: even_line_to_half(x, float(x)<0 if pd.notna(x) else None))
            st.dataframe(shown.sort_values("game_date", ascending=False), use_container_width=True, hide_index=True)
            st.download_button("Download archive", ledger.to_csv(index=False), "pool_lock_lines.csv", "text/csv")

    else:
        st.subheader("Data and modeling notes")
        st.markdown("""
**What the first release does**
- NFL schedules, final scores, closing spread/total, venue, surface, roof, weather observations, and head coaches from nflverse.
- FBS games and optional betting lines, team statistics, SP+ / Elo ratings, coach data, and weather from CollegeFootballData (CFBD).
- Year-by-year out-of-sample NFL and FBS model comparison: spread-only baseline versus spread + pregame rolling team form. Training uses earlier seasons only.
- CSV ledger and exact ten-pick card for the pool lines captured at 10 a.m.; integer lines are shifted half a point to remove pushes.

**Data caveats to resolve before claiming an edge**
- Public NFL spread fields are generally closing market lines; they do not reconstruct a historical 10 a.m. price. Record your pool's lines prospectively or import a licensed odds-history feed.
- Weather observations at kickoff are not the forecast known at 10 a.m. They may be explored only in a separate hindsight analysis, never in the production pick model.
- CFBD's data coverage and endpoints vary by season and subscription; missing lines/weather remain missing rather than being fabricated.
- Coaches, schedule strength, player availability, injuries, travel, altitude, and line movement can be added after source and timestamp coverage is confirmed.
- The current model is a baseline research tool. Validate calibration, log loss, Brier score, market comparison, and pool-specific 10-pick outcomes before relying on its picks.
""")
        st.markdown("**Sources:** [nflverse schedule data](https://nflreadr.nflverse.com/reference/load_schedules.html) · [CollegeFootballData API](https://api.collegefootballdata.com/) · [The Odds API](https://the-odds-api.com/)")


if __name__ == "__main__":
    main()
