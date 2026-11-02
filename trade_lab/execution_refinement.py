"""Observed minute-path audit and declared entry/exit refinements, paper only."""
import numpy as np
import pandas as pd
from .edge_research import ExitPolicy,simulate_window
from .research_factory import candidates,stable_hash
from .full_allocation import risk_metrics

DELAYS=(0,1,5,15)
EXITS=(ExitPolicy('time_only',None,None),ExitPolicy('tp2_sl2',2.,2.),
       ExitPolicy('tp4_sl2',4.,2.),ExitPolicy('tp6_sl3',6.,3.))
MANIFEST={'version':'execution_refinement_v1','pairs':['semiconductors','semiconductors2','smallcap','nasdaq3'],
    'thresholds':[.75,1.,1.25],'directions':['both','bull_only'],
    'entry_delay_minutes':list(DELAYS),'exits':[{ 'name':p.name,'target_pct':p.target_pct,'stop_pct':p.stop_pct} for p in EXITS],
    'cost_bps_per_side':[10,20,50],'allocation':1.,'candidates_per_pair':96,
    'selection_years':[2021,2022,2023],'minimum_dev_trades':40,'minimum_annual_trades':5,
    'selection_score':'mean daily log growth at 20bps on complete-coverage development data; positive required',
    'minute_policy':'No interpolation; all regular-session minutes required for path-dependent candidate replay',
    'endpoint_audit':'Compare actual daily interval to exact regular-session first-open/last-close on observed endpoints',
    'historical_status':'All 2024-2026 data previously inspected; audit and exploratory refinements only'}


def volume_signals(data):
    return {key:row['sides'] for key,row in candidates(data).items() if row['family']=='volume_reversal'}


def validate_minutes(raw,symbols,opening,closing):
    cols=['timestamp','symbol','open','high','low','close','volume']
    if raw.empty:return pd.DataFrame(columns=cols)
    x=raw[cols].copy();x['timestamp']=pd.to_datetime(x.timestamp,utc=True,errors='raise')
    if not set(x.symbol).issubset(symbols):raise ValueError('Unexpected minute ticker')
    if x.duplicated(['symbol','timestamp']).any():raise ValueError('Duplicate minute rows')
    if not x.timestamp.eq(x.timestamp.dt.floor('min')).all():raise ValueError('Non-minute timestamps')
    if ((x.timestamp<opening)|(x.timestamp>=closing)).any():raise ValueError('Out-of-session minute data')
    x[cols[2:]]=x[cols[2:]].apply(pd.to_numeric,errors='raise')
    if not np.isfinite(x[cols[2:]].to_numpy()).all():raise ValueError('Nonfinite minute values')
    if (x[['open','high','low','close']]<=0).any().any() or (x.volume<0).any():raise ValueError('Invalid minute prices/volume')
    if (x.high<x[['open','low','close']].max(axis=1)).any() or (x.low>x[['open','high','close']].min(axis=1)).any():
        raise ValueError('Invalid minute OHLC')
    return x.sort_values(['symbol','timestamp']).reset_index(drop=True)


def trade_days(data):
    signals=volume_signals(data)
    active=np.column_stack(list(signals.values()))!=0
    return list(data.loc[active.any(axis=1),'date'])


def _metrics(data,rows,mask,signal,strict=True):
    dates=set(data.loc[mask,'date']);expected=set(data.loc[mask & (signal!=0),'date'])
    observed=rows.loc[rows.date.isin(dates)] if not rows.empty else rows
    observed_dates=set(observed.date) if not observed.empty else set()
    missing=expected-observed_dates
    # Unknown outcomes are removed from the observed-subset diagnostic, never
    # replaced with cash or prices. This cannot claim a complete replay.
    part=data.loc[mask & ~data.date.isin(missing),['date']].copy()
    net=observed.set_index('date') if not observed.empty else None
    for cost in (10,20,50):
        values=pd.Series(0.,index=part.index)
        if net is not None:values=part.date.map(net[f'net_{cost}bps_pct']).fillna(0.)
        part[f'tqqq_net_{cost}bps_pct']=values.to_numpy();part[f'sqqq_net_{cost}bps_pct']=0.
    sides=part.date.isin(observed_dates).to_numpy(dtype=int)
    result={'status':'COMPLETE_COVERAGE' if not missing else 'INCOMPLETE_OBSERVED_SUBSET_ONLY',
            'expected_trades':len(expected),'observed_trades':len(observed_dates),
            'missing_trade_dates':[str(x) for x in sorted(missing)]}
    if len(part):result['observed_subset_metrics']={f'cost_{c}bps':risk_metrics(part,sides,1.,c) for c in (10,20,50)}
    return result,part,sides


def run_execution_audit(data,pair,calendar,day_bars):
    data=data.reset_index(drop=True)
    signals=volume_signals(data);events=[];returns=[]
    years=pd.to_datetime(data.date).dt.year
    for pos,row in data.iterrows():
        active=[name for name,sides in signals.items() if sides[pos]!=0]
        if not active:continue
        directions={int(signals[name][pos]) for name in active}
        if len(directions)!=1:raise ValueError('Conflicting nested volume signals')
        side=directions.pop();symbol=pair.bull if side==1 else pair.bear
        opening,closing=calendar[row.date]
        raw=day_bars.get(row.date)
        raw=pd.DataFrame() if raw is None else validate_minutes(raw,{pair.bull,pair.bear},opening,closing)
        prices=(raw.loc[raw.symbol.eq(symbol)].set_index('timestamp') if not raw.empty else pd.DataFrame())
        expected=pd.date_range(opening,closing-pd.Timedelta(minutes=1),freq='min')
        complete=not prices.empty and prices.index.equals(expected)
        endpoints=not prices.empty and opening in prices.index and expected[-1] in prices.index
        daily=float(row['tqqq_net_10bps_pct'] if side==1 else row['sqqq_net_10bps_pct'])
        event={'date':str(row.date),'symbol':symbol,'source_daily_net_10bps_pct':daily,
               'active_rules':active,'observed_minutes':len(prices),'expected_minutes':len(expected),
               'complete_path':bool(complete),'exact_endpoints':bool(endpoints),
               'prior_return_1':float(row.prior_return_1),'prior_volume_shock':float(row.prior_volume_shock)}
        if endpoints:
            net=100*(prices.loc[expected[-1],'close']*.999/(prices.loc[opening,'open']*1.001)-1)
            event.update(minute_regular_session_net_10bps_pct=float(net),
                         minute_minus_daily_percentage_points=float(net-daily),
                         endpoint_return_difference_over_10bps=bool(abs(net-daily)>.1),
                         regular_open=float(prices.loc[opening,'open']),regular_last_minute_close=float(prices.loc[expected[-1],'close']))
        events.append(event)
        if not complete:continue
        for delay in DELAYS:
            entry=opening+pd.Timedelta(minutes=delay);horizon=len(expected)-delay
            if horizon<=0:raise ValueError('Entry beyond scheduled close')
            path=prices.loc[entry:]
            for policy in EXITS:
                record={'date':row.date,'symbol':symbol,'delay':delay,'exit':policy.name,
                        'minute_low_adverse_excursion_pct':float(100*(path.low.min()/(path.iloc[0].open*1.001)*.999-1))}
                for cost in (10,20,50):
                    value,ambiguous=simulate_window(prices,entry,horizon,policy,cost)
                    record[f'net_{cost}bps_pct']=value;record[f'ambiguous_{cost}bps']=bool(ambiguous)
                returns.append(record)
    execution=pd.DataFrame(returns)
    if execution.empty:execution=pd.DataFrame(columns=['date','symbol','delay','exit',*[f'net_{c}bps_pct' for c in (10,20,50)]])
    ranking=[];reports={}
    periods=[('development_2021_2023',years.between(2021,2023)),('inspected_2024',years.eq(2024)),
             ('inspected_2025_2026',years.ge(2025)),('inspected_2024_2026',years.ge(2024))]
    for name,signal in signals.items():
        expected_dates=set(data.loc[signal!=0,'date'])
        for delay in DELAYS:
            for policy in EXITS:
                key=f'{name}__delay{delay}__{policy.name}'
                rows=execution.loc[execution.date.isin(expected_dates)&execution.delay.eq(delay)&execution.exit.eq(policy.name)]
                reports[key]={}
                dev_score=None;counts=[];dev_complete=False
                for period,mask in periods:
                    report,part,sides=_metrics(data,rows,mask,signal)
                    reports[key][period]=report
                    if period=='development_2021_2023':
                        counts=[int((sides[pd.to_datetime(part.date).dt.year.eq(y)]!=0).sum()) for y in (2021,2022,2023)]
                        dev_complete=report['status']=='COMPLETE_COVERAGE'
                        if len(part):
                            r=np.where(sides!=0,part.tqqq_net_20bps_pct.to_numpy()/100,0.)
                            dev_score=float(np.log1p(r).mean())
                eligible=dev_complete and sum(counts)>=40 and min(counts)>=5
                ranking.append({'candidate':key,'eligible':bool(eligible),'score':dev_score,
                                'development_complete':dev_complete,'fold_trades':counts})
    ranking=sorted(ranking,key=lambda r:(not r['eligible'],-(r['score'] if r['score'] is not None else -1e10),r['candidate']))
    selected=next((r['candidate'] for r in ranking if r['eligible'] and r['score']>0),None)
    # Best daily winners remain in the audit even if their minute paths fail.
    later=[e for e in events if pd.Timestamp(e['date']).year>=2025]
    largest=sorted(later,key=lambda e:e['source_daily_net_10bps_pct'],reverse=True)[:10]
    return {'manifest':MANIFEST,'manifest_sha256':stable_hash(MANIFEST),'selected':selected,'ranking':ranking,
            'reports':reports,'event_audit':events,'largest_daily_winners_audit':largest,
            'coverage':{'requested_trade_days':len(events),'complete_paths':sum(e['complete_path'] for e in events),
                        'exact_endpoints':sum(e['exact_endpoints'] for e in events),
                        'endpoint_differences_over_10bps':sum(e.get('endpoint_return_difference_over_10bps',False) for e in events)},
            'go_no_go':'NO_VALIDATED_EDGE'},execution
