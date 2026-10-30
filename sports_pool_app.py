"""Automatic NFL + FBS ten-pick slate dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import time

import numpy as np
import pandas as pd
import streamlit as st

from sports_pool_model import (
    FEATURES, add_pregame_features, fetch_current_odds, load_cfb_history,
    load_nfl_history, make_current_board, resolve_team_name, walk_forward_model,
)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_nfl_history(start: int, end: int) -> pd.DataFrame:
    return load_nfl_history(start, end)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_cfb_history(start: int, end: int, key: str) -> pd.DataFrame:
    return load_cfb_history(start, end, key)


@st.cache_data(ttl=900, show_spinner=False)
def cached_odds(key: str, sport: str, refresh_nonce: int) -> pd.DataFrame:
    return fetch_current_odds(key, [sport])


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

    st.info(f"Loading six season labels ({first_year}–{last_year}): five prior seasons plus current-season results for live team form. Historical spreads are generally closing lines; current recommendations use today's bookmaker consensus.")

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
    board=pd.concat(boards,ignore_index=True) if boards else pd.DataFrame()
    if board.empty:
        st.error("The models did not produce a ranked board. Confirm that each league has historical scores and closing spreads.")
        st.stop()

    latest=pd.to_datetime(odds.updated,errors="coerce",utc=True).max()
    last_seen=latest.strftime("%b %d, %I:%M %p UTC") if pd.notna(latest) else "provider time unavailable"
    st.success(f"Loaded {len(odds[odds.market=='spreads'].game_id.unique())} games with spread odds. Latest provider quote: {last_seen}. Lines refresh automatically every 15 minutes; use Refresh current lines now for an immediate update.")

    top=board.head(10).copy()
    top.insert(0,"Rank",range(1,len(top)+1))
    top["Recommended pick"]=top.apply(lambda r:r.best_side,axis=1)
    top["Pool line"]=top.apply(display_line,axis=1)
    top["Cover probability"]=top.best_cover_probability
    top["Model agreement"]=top.model_agreement
    top["Confidence score"]=top.rank_score
    cols=["Rank","sport","game_date","away_team","home_team","Recommended pick","Pool line","Cover probability","Model agreement","Confidence score","line_updated"]

    top_tab,analysis_tab,data_tab=st.tabs(["Top 10 this week","Model performance","Data coverage"])
    with top_tab:
        st.subheader("Best ten games by predicted cover probability")
        st.caption("Each recommendation is the side with the higher probability of covering its pool-adjusted spread. Ranking uses the selected model's calibrated probability, with agreement across all nine candidates as a tie-breaker.")
        st.dataframe(top[cols].style.format({"Cover probability":"{:.1%}","Model agreement":"{:.0%}","Confidence score":"{:.3f}"}),use_container_width=True,hide_index=True)
        st.download_button("Download ranked slate",top[cols].to_csv(index=False),"weekly_top_10.csv","text/csv")
        st.markdown("#### All games with current lines")
        rest=board.copy()
        rest["Recommended pick"]=rest.best_side
        rest["Pool line"]=rest.apply(display_line,axis=1)
        all_cols=["sport","game_date","away_team","home_team","home_line","away_line","Recommended pick","Pool line","best_cover_probability","model_agreement","total_line","line_updated"]+[c for c in ["venue","home_coach","away_coach"] if c in rest]
        st.dataframe(rest[all_cols].style.format({"best_cover_probability":"{:.1%}","model_agreement":"{:.0%}"}),use_container_width=True,hide_index=True)
        with st.expander("Top ten game details"):
            detail_cols=[c for c in ["sport","game_date","away_team","home_team","venue","home_coach","away_coach","temperature","wind","humidity","precipitation"] if c in top]
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
        st.caption("Whole-number lines are shifted by 0.5 points away from zero (for example, -3 becomes -3.5 and +3 becomes +3.5). These adjusted lines are used both in training labels and current recommendations.")

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
        st.markdown("**Point-in-time rules:** rolling team form, prior coach results, and rest use only earlier completed games. Venue and coach data enter the model when available. Observed game weather is retained as context but excluded from picks because it was not known at the morning line lock.")
        st.markdown("**Sources:** nflverse schedule history for NFL results/spreads/venue/coaches/weather; CollegeFootballData for FBS games, lines, and game weather; The Odds API for current bookmaker spreads and totals.")


if __name__=="__main__":
    main()
