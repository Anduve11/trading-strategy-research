"""Automatic NFL + FBS ten-pick slate dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
import os
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

from sports_pool_model import (
    FEATURES, add_pregame_features, fetch_current_odds, fetch_forecast_weather, load_cfb_history,
    _cfbd_venues, load_nfl_history, make_current_board, resolve_team_name, walk_forward_model,
)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_nfl_history(start: int, end: int) -> pd.DataFrame:
    return load_nfl_history(start, end)


@st.cache_data(ttl=30*86400, show_spinner=False)
def cached_cfb_venues(key: str) -> pd.DataFrame:
    return _cfbd_venues(key)


@st.cache_data(ttl=30*86400, show_spinner=False)
def cached_completed_cfb_year(year: int, key: str, venues: pd.DataFrame) -> pd.DataFrame:
    return load_cfb_history(year, year, key, venues)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_current_cfb_year(year: int, key: str, venues: pd.DataFrame) -> pd.DataFrame:
    return load_cfb_history(year, year, key, venues)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_cfb_history(start: int, end: int, key: str) -> pd.DataFrame:
    venues=cached_cfb_venues(key)
    parts=[]
    for year in range(start,end+1):
        part=cached_current_cfb_year(year,key,venues) if year==end else cached_completed_cfb_year(year,key,venues)
        if not part.empty:parts.append(part)
    return pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def cached_odds(key: str, sport: str, refresh_nonce: int) -> pd.DataFrame:
    return fetch_current_odds(key, [sport])


@st.cache_data(ttl=1800, show_spinner=False)
def cached_forecasts(game_keys: tuple) -> pd.DataFrame:
    frame=pd.DataFrame(game_keys,columns=["game_id","game_date","venue_lat","venue_lon","venue_dome"])
    return fetch_forecast_weather(frame)


@st.cache_resource(show_spinner=False)
def cached_model(sport: str, games: pd.DataFrame):
    study=add_pregame_features(games)
    pred,metrics,selected,fit=walk_forward_model(study)
    return study,pred,metrics,selected,fit


def secret(key: str) -> str:
    try:
        value = st.secrets.get(key, "")
    except Exception:
        value = ""
    return str(value or os.getenv(key, "")).strip()


def display_line(row: pd.Series) -> str:
    if row.best_side == row.home_team:
        return f"{row.home_team} {row.home_line:+.1f}"
    return f"{row.away_team} {row.away_line:+.1f}"


def display_open_line(row: pd.Series) -> str:
    value=pd.to_numeric(pd.Series([row.get("home_line_open")]),errors="coerce").iloc[0]
    if pd.isna(value):return "Unavailable"
    side_line=value if row.best_side==row.home_team else -value
    return f"{row.best_side} {side_line:+.1f}"


def pick_explanation(row: pd.Series) -> str:
    side="home" if row.best_side==row.home_team else "away"
    other="away" if side=="home" else "home"
    other_team=row.away_team if side=="home" else row.home_team
    parts=[f"The selected model estimates {row.best_cover_probability:.1%} ATS cover probability; {int(round(row.model_agreement*9))} of 9 models favor this side."]
    margin=pd.to_numeric(pd.Series([row.get(f"{side}_margin3")]),errors="coerce").iloc[0]
    opp_margin=pd.to_numeric(pd.Series([row.get(f"{other}_margin3")]),errors="coerce").iloc[0]
    games_seen=pd.to_numeric(pd.Series([row.get(f"{side}_games_seen")]),errors="coerce").iloc[0]
    opp_games_seen=pd.to_numeric(pd.Series([row.get(f"{other}_games_seen")]),errors="coerce").iloc[0]
    if pd.notna(margin) and pd.notna(opp_margin) and games_seen>0 and opp_games_seen>0:
        parts.append(f"Last-three scoring margin: {row.best_side} {margin:+.1f}/game vs {other_team} {opp_margin:+.1f}/game.")
    cover=pd.to_numeric(pd.Series([row.get(f"{side}_ats_cover3")]),errors="coerce").iloc[0]
    ats_n=pd.to_numeric(pd.Series([row.get(f"{side}_ats_games3")]),errors="coerce").iloc[0]
    if pd.notna(cover) and pd.notna(ats_n) and ats_n>0:parts.append(f"Recent ATS cover rate: {cover:.0%} over {int(ats_n)} lined game(s).")
    rest=pd.to_numeric(pd.Series([row.get(f"{side}_rest_days")]),errors="coerce").iloc[0]
    bye=pd.to_numeric(pd.Series([row.get(f"{side}_bye_return")]),errors="coerce").iloc[0]
    if pd.notna(bye) and bye>=1:parts.append("Coming off a same-season bye week.")
    elif pd.notna(rest):parts.append(f"Rest: {rest:.0f} days since its previous game.")
    travel=pd.to_numeric(pd.Series([row.get(f"{side}_travel_miles")]),errors="coerce").iloc[0]
    if pd.notna(travel) and travel>0:parts.append(f"Estimated trip from its prior game site: {travel:,.0f} miles.")
    coach=pd.to_numeric(pd.Series([row.get(f"{side}_coach_win10")]),errors="coerce").iloc[0]
    coach_n=pd.to_numeric(pd.Series([row.get(f"{side}_coach_games")]),errors="coerce").iloc[0]
    if pd.notna(coach) and pd.notna(coach_n) and coach_n>0:parts.append(f"Coach's prior-game win rate in the data: {coach:.0%}.")
    weather=row.get("forecast_summary")
    if isinstance(weather,str) and weather:parts.append(weather)
    return " ".join(parts)


def current_week_slate(board: pd.DataFrame) -> tuple[pd.DataFrame,str]:
    """Keep recommendations on the current Monday–Sunday Mountain-time slate."""
    local_now=pd.Timestamp.now(tz=ZoneInfo("America/Denver"))
    kickoffs=pd.to_datetime(board.game_date,errors="coerce",utc=True).dt.tz_convert("America/Denver")
    start=local_now.normalize()-pd.Timedelta(days=local_now.weekday())
    end=start+pd.Timedelta(days=7)
    keep=(kickoffs>=local_now)&(kickoffs<end)
    label=f"{start.strftime('%b %-d')}–{(end-pd.Timedelta(seconds=1)).strftime('%b %-d')} Mountain time"
    if not keep.any():
        keep=(kickoffs>=local_now)&(kickoffs<local_now+pd.Timedelta(days=7))
        label="Next 7 days (no remaining games this Monday–Sunday week)"
    return board.loc[keep].copy(),label


def calibration_table(pred: pd.DataFrame, selected: str) -> pd.DataFrame:
    d=pred[pred.model==selected].copy()
    if d.empty:return pd.DataFrame()
    d["probability_bin"]=pd.cut(d.p_home_cover,bins=np.linspace(0,1,11),include_lowest=True)
    return d.groupby("probability_bin",observed=False).agg(games=("home_cover","size"),mean_probability=("p_home_cover","mean"),actual_cover_rate=("home_cover","mean")).dropna().reset_index()


def importance_table(fit: dict, selected: str) -> pd.DataFrame:
    model=fit.get("models",{}).get(selected)
    if model is None:return pd.DataFrame()
    inner=model.steps[-1][1] if hasattr(model,"steps") else model
    if hasattr(inner,"feature_importances_"):
        values=inner.feature_importances_
    elif hasattr(inner,"coef_"):
        values=np.abs(inner.coef_[0])
    else:return pd.DataFrame()
    return pd.DataFrame({"Feature":fit["feature_columns"][selected],"Importance":values}).sort_values("Importance",ascending=False)


def pool_holdout_test(model_results: dict) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Compare selected model versus market-only model on held-out weekly cards."""
    chunks=[]
    for sport,(_,pred,_,selected,fit) in model_results.items():
        holdout=fit.get("holdout_season")
        sel=pred[(pred.model==selected)&(pred.season==holdout)].copy()
        market=pred[(pred.model=="Market-only logistic")&(pred.season==holdout)].copy()
        if sel.empty or market.empty:continue
        keys=["season","week","game_date","home_team","away_team","home_line"]
        sel=sel[keys+["home_cover","p_home_cover"]].rename(columns={"p_home_cover":"model_p_home"})
        market=market[keys+["p_home_cover"]].rename(columns={"p_home_cover":"market_p_home"})
        g=sel.merge(market,on=keys,how="inner")
        calibrator=fit.get("calibrator")
        if calibrator is not None:
            p=np.clip(g.model_p_home.to_numpy(),1e-5,1-1e-5)
            g["model_p_home"]=calibrator.predict_proba(np.log(p/(1-p)).reshape(-1,1))[:,1]
        g["sport"]=sport
        gd=pd.to_datetime(g.game_date)
        g["week_start"]=gd.dt.normalize()-pd.to_timedelta(gd.dt.weekday,unit="D")
        chunks.append(g)
    if not chunks:return pd.DataFrame(),pd.DataFrame()
    games=pd.concat(chunks,ignore_index=True)
    selections=[]
    for method,pcol in [("Selected ML","model_p_home"),("Market-only","market_p_home")]:
        g=games.copy()
        g["pick_home"]=g[pcol]>=.5
        g["pick_probability"]=np.maximum(g[pcol],1-g[pcol])
        g["correct"]=np.where(g.pick_home,g.home_cover,1-g.home_cover).astype(int)
        chosen=g.sort_values("pick_probability",ascending=False).groupby(["season","week_start"],group_keys=False).head(10)
        chosen["strategy"]=method
        selections.append(chosen)
    picks=pd.concat(selections,ignore_index=True)
    from scipy.stats import binomtest
    summary=[]
    for strategy,g in picks.groupby("strategy"):
        n=len(g);wins=int(g.correct.sum());rate=wins/n if n else np.nan
        z=1.96;den=1+z*z/n;center=(rate+z*z/(2*n))/den;radius=z*np.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/den
        summary.append({"Strategy":strategy,"Holdout picks":n,"Weeks":g.week_start.nunique(),"Correct":wins,"Cover rate":rate,"95% Wilson low":center-radius,"95% Wilson high":center+radius,"One-sided p vs 50%":float(binomtest(wins,n,.5,alternative="greater").pvalue),"Mean predicted confidence":g.pick_probability.mean()})
    return pd.DataFrame(summary),picks


def main() -> None:
    st.set_page_config(page_title="Weekly Ten-Pick Model",page_icon="🏈",layout="wide")
    st.title("🏈 Weekly Ten-Pick Model")
    st.caption("NFL + FBS · current market lines · walk-forward machine-learning rankings")
    odds_key=secret("ODDS_API_KEY")
    cfbd_key=secret("CFBD_API_KEY")
    if not odds_key:
        st.error("This Streamlit app cannot see ODDS_API_KEY. Add it under this app's Settings → Secrets, save, then reboot the app.")
        st.stop()

    now=datetime.now(timezone.utc)
    first_year=now.year-5
    last_year=now.year
    refresh_nonce=st.session_state.get("refresh_nonce",0)
    if st.button("Refresh current lines now",help="Bypasses the 15-minute odds cache."):
        st.session_state["refresh_nonce"]=int(time.time())
        refresh_nonce=st.session_state["refresh_nonce"]
        cached_odds.clear()

    st.info(f"Loading six season labels ({first_year}–{last_year}): five prior seasons plus current-season results for live team form. NFL history is generally closing-line data; the college feed also supplies opening spreads when available. Current picks use today's bookmaker consensus.")

    with st.spinner("Loading five-year NFL and college history, fitting walk-forward models, and fetching this week's odds…"):
        try:
            nfl=cached_nfl_history(first_year,last_year)
        except Exception as exc:
            st.error(f"NFL history could not be loaded: {exc}")
            st.stop()
        cfb=pd.DataFrame()
        cfb_error=""
        if cfbd_key:
            try:
                cfb=cached_cfb_history(first_year,last_year,cfbd_key)
            except Exception as exc:
                cfb_error=str(exc)
        odds_parts=[]
        odds_errors=[]
        for sport in ["NFL","NCAAF"]:
            try:
                part=cached_odds(odds_key,sport,refresh_nonce)
                if not part.empty:odds_parts.append(part)
            except Exception as exc:
                odds_errors.append(f"{sport}: {exc}")
        odds=pd.concat(odds_parts,ignore_index=True) if odds_parts else pd.DataFrame()

    if not cfbd_key:
        st.warning("CFBD_API_KEY is missing from this app's Secrets. NFL recommendations can still run; add the college data key to enable FBS history and rankings.")
    elif cfb_error:
        if "rejected its key" in cfb_error.lower() or "401" in cfb_error:
            st.warning("CollegeFootballData returned 401. In this app's Settings → Secrets, set CFBD_API_KEY to your CollegeFootballData key (not the Odds API key). Enter only the key value; the app adds the Bearer header itself. Save and reboot the app.")
        else:
            st.warning(f"College history could not be loaded: {cfb_error}")
    for error in odds_errors:st.warning(error)
    if odds.empty:
        st.error("No current odds returned. Check the odds API key, plan, and league coverage.")
        st.stop()

    histories={"NFL":nfl}
    if not cfb.empty:histories["NCAAF"]=cfb
    model_results={}
    training_errors={}
    with st.spinner("Training nine model candidates and grading them with season-by-season holdouts…"):
        for sport,games in histories.items():
            try:
                model_results[sport]=cached_model(sport,games)
            except Exception as exc:
                training_errors[sport]=str(exc)

    boards=[]
    for sport,(_,_,_,selected,fit) in model_results.items():
        live=odds[odds.sport==sport].copy()
        if live.empty:continue
        try:
            boards.append(make_current_board(live,histories[sport],fit["models"],selected,fit.get("calibrator"),fit.get("feature_columns")))
        except Exception as exc:
            training_errors[sport]=f"Could not create live predictions: {exc}"
    for sport,error in training_errors.items():st.warning(f"{sport} model: {error}")
    board_all=pd.concat(boards,ignore_index=True) if boards else pd.DataFrame()
    if board_all.empty:
        st.error("The models did not produce a ranked board. Confirm that each league has historical scores and closing spreads.")
        st.stop()
    board,week_label=current_week_slate(board_all)
    if board.empty:
        st.warning("No upcoming games with current spread quotes were found in this week's slate.")
        st.stop()
    forecast_error=""
    try:
        game_keys=tuple((str(r.game_id),pd.to_datetime(r.game_date).isoformat(),float(r.venue_lat),float(r.venue_lon),bool(r.get("venue_dome",False)) if pd.notna(r.get("venue_dome")) else False) for _,r in board.iterrows() if pd.notna(r.get("venue_lat")) and pd.notna(r.get("venue_lon")))
        if game_keys:
            fc=cached_forecasts(game_keys)
            if not fc.empty:board=board.merge(fc,on="game_id",how="left")
    except Exception as exc:
        forecast_error=str(exc)
    for c in ["forecast_temp_c","forecast_wind_kmh","forecast_precip_mm","forecast_precip_probability"]:
        if c not in board:board[c]=np.nan
    def weather_summary(r: pd.Series) -> str:
        dome=r.get("venue_dome",False)
        if pd.notna(dome) and bool(dome):return "Indoor/dome venue; outdoor weather minimized."
        t=r.get("forecast_temp_c");w=r.get("forecast_wind_kmh");p=r.get("forecast_precip_probability")
        if pd.isna(t) and pd.isna(w):return "Forecast unavailable."
        bits=[]
        if pd.notna(t):bits.append(f"{float(t)*9/5+32:.0f}°F")
        if pd.notna(w):bits.append(f"wind {float(w)*0.621371:.0f} mph")
        if pd.notna(p) and p>=30:bits.append(f"precipitation chance {float(p):.0f}%")
        return "Kickoff forecast: "+", ".join(bits)+"."
    board["forecast_summary"]=board.apply(weather_summary,axis=1)

    latest=pd.to_datetime(odds.updated,errors="coerce",utc=True).max()
    last_seen=latest.strftime("%b %d, %I:%M %p UTC") if pd.notna(latest) else "provider time unavailable"
    st.success(f"This week's slate ({week_label}): {len(board)} games with current spread quotes. Latest provider quote: {last_seen}. Lines refresh automatically every 15 minutes; use Refresh current lines now for an immediate update.")
    if forecast_error:st.caption(f"Kickoff forecast could not be loaded: {forecast_error}")

    top=board.head(10).copy()
    top.insert(0,"Rank",range(1,len(top)+1))
    top["Recommended pick"]=top.apply(lambda r:r.best_side,axis=1)
    top["Open / Tuesday spread"]=top.apply(display_open_line,axis=1)
    top["Current line"]=top.apply(display_line,axis=1)
    top["Cover probability"]=top.best_cover_probability
    top["Model agreement"]=top.model_agreement
    top["Confidence score"]=top.rank_score
    cols=["Rank","sport","game_date","away_team","home_team","Recommended pick","Open / Tuesday spread","Current line","Cover probability","Model agreement"]

    top_tab,analysis_tab,data_tab=st.tabs(["Top 10 this week","Model performance","Data coverage"])
    with top_tab:
        st.subheader("Best ten games by predicted cover probability")
        st.caption("Every game in the current Monday–Sunday slate with a current spread is ranked. Open / Tuesday lines are shown where a source provides them; the free Odds API plan does not provide its historical snapshots.")
        st.dataframe(top[cols].style.format({"Cover probability":"{:.1%}","Model agreement":"{:.0%}","Confidence score":"{:.3f}"}),use_container_width=True,hide_index=True)
        st.download_button("Download ranked slate",top[cols].to_csv(index=False),"weekly_top_10.csv","text/csv")
        st.markdown("#### Why each game ranks here")
        st.caption("These are observable model inputs and recent-game facts, not claims that any single factor caused the prediction.")
        for _,r in top.iterrows():
            summary=pick_explanation(r)
            heading=escape(f"#{int(r.Rank)} · {r.best_side} {display_line(r)} · {r.away_team} at {r.home_team}")
            st.markdown(f"<div style='text-align:center;padding:12px 18px;margin:8px 0;border:1px solid #e6e8eb;border-radius:10px'><strong>{heading}</strong><br><span>{escape(summary)}</span></div>",unsafe_allow_html=True)
        st.markdown("#### All games with current lines")
        rest=board.copy()
        rest["Recommended pick"]=rest.best_side
        rest["Open home spread"]=rest.home_line_open
        rest["Current home spread"]=rest.home_line
        all_cols=["sport","game_date","away_team","home_team","Open home spread","Current home spread","Recommended pick","best_cover_probability","model_agreement","total_line","forecast_summary","line_updated"]+[c for c in ["venue","home_coach","away_coach","home_travel_miles","away_travel_miles","home_bye_return","away_bye_return"] if c in rest]
        st.dataframe(rest[all_cols].style.format({"best_cover_probability":"{:.1%}","model_agreement":"{:.0%}"}),use_container_width=True,hide_index=True)
        with st.expander("Top ten game details"):
            detail_cols=[c for c in ["sport","game_date","away_team","home_team","venue","home_coach","away_coach","temperature","wind","humidity","precipitation","forecast_summary","home_travel_miles","away_travel_miles","home_time_zone_shift","away_time_zone_shift","home_altitude_change","away_altitude_change","home_margin2","away_margin2","home_margin3","away_margin3","home_ats_cover3","away_ats_cover3","home_bye_return","away_bye_return"] if c in top]
            st.dataframe(top[detail_cols],use_container_width=True,hide_index=True)
        local_now=pd.Timestamp.now(tz="UTC").tz_convert(None)
        missing=[]
        for sport,games in histories.items():
            upcoming=games[(pd.to_datetime(games.game_date,errors="coerce")>=local_now-pd.Timedelta(hours=3))&(pd.to_datetime(games.game_date,errors="coerce")<=local_now+pd.Timedelta(days=8))&games.home_score.isna()]
            names=list(set(games.home_team.astype(str))|set(games.away_team.astype(str)))
            have=board[board.sport==sport] if not board.empty else pd.DataFrame()
            for _,game in upcoming.iterrows():
                h=resolve_team_name(str(game.home_team),names,sport);a=resolve_team_name(str(game.away_team),names,sport)
                if not have.empty and ((have.home_team_model==h)&(have.away_team_model==a)).any():continue
                missing.append({"League":sport,"Kickoff UTC":game.game_date,"Game":f"{game.away_team} @ {game.home_team}","Venue":game.get("venue",""),"Home coach":game.get("home_coach",""),"Away coach":game.get("away_coach",""),"Status":"Schedule found; spread not returned by odds provider"})
        if missing:
            st.markdown("#### Scheduled games without current spread quotes")
            st.dataframe(pd.DataFrame(missing),use_container_width=True,hide_index=True)
        st.caption("Whole-number lines are shifted by 0.5 points away from zero (for example, -3 becomes -3.5 and +3 becomes +3.5). Opening lines come from CFBD's spreadOpen field for college games when available; nflverse provides NFL closing lines. NFL Tuesday snapshots require paid historical odds access. Current recommendations use current consensus spreads.")

    with analysis_tab:
        st.subheader("Out-of-sample model comparison")
        st.write("Nine candidates include a market-only logistic baseline and two settings each for regularized logistic regression, random forest, extra trees, and histogram gradient boosting. Each test season is fit only on earlier seasons. Candidate selection uses development seasons; the latest complete season is reserved as the holdout.")
        for sport,(_,pred,metrics,selected,fit) in model_results.items():
            st.markdown(f"#### {sport} · selected: **{selected}**")
            st.caption(f"Training games: {fit['history_rows']:,} · seasons: {', '.join(map(str,fit['seasons']))} · untouched holdout: {fit['holdout_season']}")
            st.dataframe(metrics.style.format({"Development Brier":"{:.3f}","OOS accuracy":"{:.1%}","OOS Brier":"{:.3f}","OOS log loss":"{:.3f}","Holdout accuracy":"{:.1%}","Holdout Brier":"{:.3f}","Holdout log loss":"{:.3f}"}),use_container_width=True,hide_index=True)
            cal=calibration_table(pred,selected)
            if not cal.empty:
                st.markdown("**Selected model reliability by probability band**")
                st.dataframe(cal.style.format({"mean_probability":"{:.1%}","actual_cover_rate":"{:.1%}"}),use_container_width=True,hide_index=True)
            imp=importance_table(fit,selected)
            if not imp.empty:
                st.markdown("**Selected-model feature importance**")
                st.dataframe(imp,use_container_width=True,hide_index=True)
            st.download_button(f"Download {sport} out-of-sample predictions",pred.to_csv(index=False),f"{sport.lower()}_walk_forward.csv","text/csv",key=f"download_{sport}")
        summary,picks=pool_holdout_test(model_results)
        if not summary.empty:
            st.markdown("#### Pool-specific holdout: rank games and pick ten per Monday–Sunday week")
            st.dataframe(summary.style.format({"Cover rate":"{:.1%}","95% Wilson low":"{:.1%}","95% Wilson high":"{:.1%}","One-sided p vs 50%":"{:.3f}","Mean predicted confidence":"{:.1%}"}),use_container_width=True,hide_index=True)
            st.caption("The p-value checks whether held-out picks covered more than half the time. It is descriptive and does not correct for repeated strategy exploration.")
            st.download_button("Download holdout ten-pick cards",picks.to_csv(index=False),"holdout_top10_cards.csv","text/csv")
        st.warning("The holdout estimates historical spread-cover prediction, not a guaranteed pool edge. Historical NFL/college lines are commonly closing snapshots and do not recreate your 10 a.m. board. Prospective lock-time line snapshots are needed to measure your exact pool strategy.")

    with data_tab:
        st.subheader("Historical data coverage")
        coverage=[]
        for sport,g in histories.items():
            spread=pd.to_numeric(g["home_spread"],errors="coerce") if "home_spread" in g else pd.Series(np.nan,index=g.index)
            venue=g["venue"] if "venue" in g else pd.Series(index=g.index,dtype=object)
            weather=(g["temperature"].notna().sum() if "temperature" in g else 0)
            coaches=(g[[c for c in ["home_coach","away_coach"] if c in g]].notna().any(axis=1).sum() if any(c in g for c in ["home_coach","away_coach"]) else 0)
            coverage.append({"Sport":sport,"Schedule rows":len(g),"Completed games":int(g[["home_score","away_score"]].notna().all(axis=1).sum()),"Games with spread":int(spread.notna().sum()),"Games with venue":int(venue.notna().sum()),"Games with weather":int(weather),"Games with coach data":int(coaches),"Years":f"{int(g.season.min())}–{int(g.season.max())}"})
        st.dataframe(pd.DataFrame(coverage),use_container_width=True,hide_index=True)
        st.markdown("**Point-in-time rules:** last-two/last-three and rolling form, prior ATS results, coach form, rest, bye returns, travel miles, time-zone shift, and altitude change are built only from earlier completed games. Historical kickoff weather and current kickoff forecasts are shown as context but not used as model features: the historical weather is hindsight, and archived pregame forecasts are needed for a fair backtest.")
        st.markdown("**Sources:** nflverse schedule history for NFL results/closing spreads/coaches/weather; CollegeFootballData for FBS schedules, opening and closing lines, weather, coaches, and venue coordinates; The Odds API for current bookmaker spreads and totals; Open-Meteo for live kickoff forecast context.")


if __name__=="__main__":
    main()
