"""Declared partial exits and conservative trailing-path bounds, paper only."""
import numpy as np
import pandas as pd
from .execution_refinement import validate_minutes,_metrics
from .research_factory import candidates,stable_hash

POLICIES=('close','hold30','hold60','hold120','trail5','trail8','trail2sigma','half3','half6')
MANIFEST={'version':'exit_management_v1','pairs':['semiconductors','smallcap','nasdaq3'],
    'base_threshold':.75,'directions':['both','bull_only'],'entry_delays_minutes':[0,5,15],
    'policies':list(POLICIES),'allocation':1.,'cost_bps_per_side':[10,20,50],
    'trailing_convention':'Worst compatible OHLC order; retain ambiguity; not a measured executable fill',
    'sigma_trail':'2 * prior proxy daily log volatility * stated ETF leverage, clipped to 2%-12%',
    'partial_exits':'Sell half at 3%/6% target, hold other half to close; no reinvestment or cash interest',
    'selection_years':[2021,2022,2023],'minimum_development_trades':40,'minimum_annual_trades':5,
    'selection_score':'Positive mean daily full-equity log growth at 20bps, complete development coverage required',
    'candidates_per_pair':54,'historical_status':'Previously inspected history; no fresh holdout'}


def path_return(prices,opening,closing,delay,policy,cost,prior_vol,leverage):
    if policy not in POLICIES:raise ValueError('Unknown exit')
    entry_time=opening+pd.Timedelta(minutes=delay)
    if prices.index.duplicated().any():raise ValueError('Duplicate price timestamps')
    if entry_time not in prices.index:return None
    slip=cost/10000;paid=float(prices.loc[entry_time,'open'])*(1+slip)
    end_time=closing-pd.Timedelta(minutes=1)
    if policy.startswith('hold'):
        end_time=min(end_time,entry_time+pd.Timedelta(minutes=int(policy[4:])-1))
    result={'ambiguous_path':False,'trailing_fraction':None,'target_touched':False}
    net=lambda exit_price:float(100*(exit_price*(1-slip)/paid-1))
    if policy=='close' or policy.startswith('hold'):
        if end_time not in prices.index:return None
        return {**result,'net_pct':net(float(prices.loc[end_time,'close']))}
    index=pd.date_range(entry_time,end_time,freq='min');path=prices.reindex(index)
    if policy.startswith('half'):
        if end_time not in prices.index:return None
        target=paid*(1+int(policy[4:])/100)
        touched=bool((path.high>=target).any());missing=path[['open','high','low','close']].isna().any(axis=1).any()
        # A known fixed-price touch fixes the half-sale proceeds even if an
        # earlier missing minute could also have touched that same target.
        if not touched and missing:return None
        closing_price=float(prices.loc[end_time,'close'])
        value=.5*net(target)+.5*net(closing_price) if touched else net(closing_price)
        return {**result,'net_pct':float(value),'target_touched':touched}
    fraction={'trail5':.05,'trail8':.08}.get(policy)
    if policy=='trail2sigma':fraction=float(np.clip(2*prior_vol/np.sqrt(252)*leverage,.02,.12))
    peak=paid;possible_exits=[];ambiguous=False;alive=True
    for values in path[['open','high','low','close']].to_numpy(dtype=float):
        if not np.isfinite(values).all():return None
        raw_open,high,low,close=map(float,values)
        old_stop=peak*(1-fraction)
        if raw_open<=old_stop:
            possible_exits.append(raw_open);alive=False;break
        peak=max(peak,raw_open);known_stop=peak*(1-fraction)
        high_peak=max(peak,high);raised_stop=high_peak*(1-fraction)
        if low<=known_stop:
            # Low first can stop at known_stop; high first may improve it.
            # The lower compatible stop is the conservative outcome.
            possible_exits.append(known_stop)
            ambiguous |= raised_stop>known_stop
            alive=False;break
        if low<=raised_stop:
            possible_exits.append(raised_stop)
            if close<=raised_stop:
                alive=False;break
            # High-before-low can stop while low-before-high can survive.
            ambiguous=True
        peak=high_peak
    if alive:possible_exits.append(float(path.iloc[-1].close))
    if not possible_exits:return None
    return {**result,'net_pct':net(min(possible_exits)),
            'ambiguous_path':bool(ambiguous),'trailing_fraction':fraction}


def run_exit_management(data,pair,calendar,day_bars):
    data=data.sort_values('date').reset_index(drop=True)
    grid=candidates(data);base=grid['volume_reversal__0.75__both']['sides']
    years=pd.to_datetime(data.date).dt.year;outcomes=[]
    for i,row in data.iterrows():
        if not base[i]:continue
        opening,closing=calendar[row.date]
        raw=day_bars.get(row.date)
        if raw is None:continue
        raw=validate_minutes(raw,{pair.bull,pair.bear},opening,closing)
        symbol=pair.bull if base[i]==1 else pair.bear
        prices=raw.loc[raw.symbol.eq(symbol)].set_index('timestamp')
        for delay in (0,5,15):
            for policy in POLICIES:
                results=[path_return(prices,opening,closing,delay,policy,c,row.prior_vol_20,pair.leverage) for c in (10,20,50)]
                if any(r is None for r in results):continue
                record={'date':row.date,'side':int(base[i]),'delay':delay,'exit':policy}
                for cost,result in zip((10,20,50),results):
                    record[f'net_{cost}bps_pct']=result['net_pct'];record[f'ambiguous_{cost}bps']=result['ambiguous_path']
                outcomes.append(record)
    execution=pd.DataFrame(outcomes,columns=['date','side','delay','exit',*[f'net_{c}bps_pct' for c in (10,20,50)],
                                            *[f'ambiguous_{c}bps' for c in (10,20,50)]])
    periods=[('development_2021_2023',years.between(2021,2023)),('inspected_2024',years.eq(2024)),
             ('inspected_2025_2026',years.ge(2025)),('inspected_2024_2026',years.ge(2024))]
    ranking=[];reports={}
    for direction in ('both','bull_only'):
        sides=base if direction=='both' else np.where(base==1,1,0)
        for delay in (0,5,15):
            baseline=execution.loc[execution.delay.eq(delay)&execution.exit.eq('close')]
            for policy in POLICIES:
                key=f'{direction}__delay{delay}__{policy}'
                rows=execution.loc[execution.delay.eq(delay)&execution.exit.eq(policy)&execution.date.isin(data.loc[sides!=0,'date'])]
                reports[key]={};score=None;counts=[];complete=False
                for period,mask in periods:
                    report,part,active=_metrics(data,rows,mask,sides)
                    common=set(rows.date)&set(baseline.date)
                    common_rows=rows.loc[rows.date.isin(common)];common_base=baseline.loc[baseline.date.isin(common)]
                    report['matched_candidate']=_metrics(data,common_rows,mask,sides)[0]
                    report['matched_close_control']=_metrics(data,common_base,mask,sides)[0]
                    report['ambiguous_trade_count_10bps']=int(rows.loc[rows.date.isin(data.loc[mask,'date']),'ambiguous_10bps'].sum())
                    reports[key][period]=report
                    if period=='development_2021_2023':
                        counts=[int((active[pd.to_datetime(part.date).dt.year.eq(y)]!=0).sum()) for y in (2021,2022,2023)]
                        complete=report['status']=='COMPLETE_COVERAGE'
                        if len(part):score=float(np.log1p(np.where(active!=0,part.tqqq_net_20bps_pct/100,0.)).mean())
                ranking.append({'candidate':key,'eligible':bool(complete and sum(counts)>=40 and min(counts)>=5),
                                'development_complete':complete,'score':score,'fold_trades':counts})
    ranking=sorted(ranking,key=lambda r:(not r['eligible'],-(r['score'] if r['score'] is not None else -1e10),r['candidate']))
    selected=next((r['candidate'] for r in ranking if r['eligible'] and r['score']>0),None)
    return {'manifest':MANIFEST,'manifest_sha256':stable_hash(MANIFEST),'selected':selected,
            'ranking':ranking,'reports':reports,'go_no_go':'NO_VALIDATED_EDGE'},execution
