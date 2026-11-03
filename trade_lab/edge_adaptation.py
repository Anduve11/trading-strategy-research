"""Past-opportunity growth controllers on exact observed minute endpoints."""
import numpy as np
import pandas as pd
from .execution_refinement import validate_minutes,_metrics
from .research_factory import candidates,stable_hash

MANIFEST={'version':'edge_adaptation_v1','thresholds':[.75,1.,1.25],
    'past_opportunity_windows':[5,10,20],'modes':['pause_base','choose_orientation'],
    'directions':['both','bull_only'],'entry_delays_minutes':[0,5,15],
    'allocation':1.,'cost_bps_per_side':[10,20,50],
    'score':'mean log growth at 20bps on previous completed paired ETF opportunities',
    'training_warmup_year':2021,'selection_years':[2022,2023],
    'minimum_dev_trades':20,'minimum_annual_trades':5,
    'endpoint_policy':'Exact observed entry open and last regular-minute close only, no stop or target, no price filling',
    'candidates_per_pair':108,'pairs':['semiconductors','semiconductors2','smallcap','nasdaq3'],
    'historical_status':'Previously inspected history; new controller motivated by those findings, no fresh holdout'}


def paired_endpoints(data,pair,calendar,day_bars,delay):
    columns=['date','bull_net_10bps_pct','bull_net_20bps_pct','bull_net_50bps_pct',
                    'bear_net_10bps_pct','bear_net_20bps_pct','bear_net_50bps_pct']
    records=[]
    for day in data.date:
        raw=day_bars.get(day)
        if raw is None:continue
        opening,closing=calendar[day];entry=opening+pd.Timedelta(minutes=delay);last=closing-pd.Timedelta(minutes=1)
        checked=validate_minutes(raw,{pair.bull,pair.bear},opening,closing)
        record={'date':day}
        for label,symbol in [('bull',pair.bull),('bear',pair.bear)]:
            prices=checked.loc[checked.symbol.eq(symbol)].set_index('timestamp')
            if entry not in prices.index or last not in prices.index:continue
            for cost in (10,20,50):record[f'{label}_net_{cost}bps_pct']=float(100*(prices.loc[last,'close']*(1-cost/10000)/
                                                  (prices.loc[entry,'open']*(1+cost/10000))-1))
        records.append(record)
    observed=pd.DataFrame(records,columns=columns)
    if observed.date.duplicated().any():raise ValueError('Duplicate endpoint dates')
    return data[['date']].merge(observed,on='date',how='left',validate='one_to_one')


def controller(base,paired,window,mode,direction):
    if window not in (5,10,20) or mode not in MANIFEST['modes'] or direction not in MANIFEST['directions']:
        raise ValueError('Unknown controller settings')
    base=np.asarray(base)
    if len(base)!=len(paired) or not np.isin(base,[-1,0,1]).all():raise ValueError('Invalid base signals')
    sides=np.zeros(len(base),dtype=int);history=[];audit=[]
    for i,side in enumerate(base):
        if not side:continue
        chosen=0;normal_score=flipped_score=None
        if len(history)>=window:
            normal_score,flipped_score=np.mean(history[-window:],axis=0)
            if mode=='pause_base':chosen=side if normal_score>0 else 0
            elif max(normal_score,flipped_score)>0 and normal_score!=flipped_score:
                chosen=side if normal_score>flipped_score else -side
        if direction=='bull_only' and chosen!=1:chosen=0
        # Emit the decision BEFORE reading this opportunity's realized returns.
        sides[i]=chosen
        audit.append({'date':str(paired.date.iloc[i]),'base_side':int(side),'planned_side':int(chosen),
                      'earlier_paired_opportunities':len(history),
                      'normal_score':float(normal_score) if normal_score is not None else None,
                      'opposite_score':float(flipped_score) if flipped_score is not None else None})
        bull=paired.bull_net_20bps_pct.iloc[i];bear=paired.bear_net_20bps_pct.iloc[i]
        if np.isfinite(bull) and np.isfinite(bear):
            r=np.array([bull,bear],dtype=float)/100
            if (r<=-1).any():raise ValueError('Invalid opportunity returns')
            # Past counterfactual ETF outcomes are observable after the session,
            # including when this controller stayed in cash. Missing pairs do
            # not update history and never become zero-return opportunities.
            history.append(np.log1p(r if side==1 else r[::-1]))
    return sides,audit


def actual_rows(paired,sides):
    rows=[]
    for i,side in enumerate(sides):
        if not side:continue
        label='bull' if side==1 else 'bear'
        values=[paired[f'{label}_net_{cost}bps_pct'].iloc[i] for cost in (10,20,50)]
        if not np.isfinite(values).all():continue
        row={'date':paired.date.iloc[i]}
        for cost,value in zip((10,20,50),values):row[f'net_{cost}bps_pct']=float(value)
        rows.append(row)
    return pd.DataFrame(rows,columns=['date',*[f'net_{c}bps_pct' for c in (10,20,50)]])


def run_adaptation(data,pair,calendar,day_bars):
    data=data.sort_values('date').reset_index(drop=True)
    grid=candidates(data);years=pd.to_datetime(data.date).dt.year
    reports={};ranking=[];decision_log={};baselines={}
    for delay in (0,5,15):
        paired=paired_endpoints(data,pair,calendar,day_bars,delay)
        for threshold in (.75,1.,1.25):
            base=grid[f'volume_reversal__{threshold:g}__both']['sides']
            for window in (5,10,20):
                for mode in MANIFEST['modes']:
                    for direction in MANIFEST['directions']:
                        key=f'volume{threshold:g}__last{window}__{mode}__{direction}__delay{delay}'
                        sides,log=controller(base,paired,window,mode,direction);decision_log[key]=log
                        rows=actual_rows(paired,sides);reports[key]={};score=None;counts=[];complete=False
                        for period,mask in [('warmup_2021',years.eq(2021)),('development_2022_2023',years.between(2022,2023)),
                                             ('inspected_2024',years.eq(2024)),('inspected_2025_2026',years.ge(2025)),
                                             ('inspected_2024_2026',years.ge(2024))]:
                            report,part,active=_metrics(data,rows,mask,sides)
                            reports[key][period]=report
                            if period=='development_2022_2023':
                                counts=[int((active[pd.to_datetime(part.date).dt.year.eq(y)]!=0).sum()) for y in (2022,2023)]
                                complete=report['status']=='COMPLETE_COVERAGE'
                                if len(part):score=float(np.log1p(np.where(active!=0,part.tqqq_net_20bps_pct/100,0.)).mean())
                        ranking.append({'candidate':key,'eligible':bool(complete and sum(counts)>=20 and min(counts)>=5),
                                        'score':score,'development_complete':complete,'fold_trades':counts})
            base_rows=actual_rows(paired,base)
            baselines[f'volume{threshold:g}__delay{delay}']={period:_metrics(data,base_rows,mask,base)[0]
                for period,mask in [('development_2022_2023',years.between(2022,2023)),('inspected_2024',years.eq(2024)),
                                    ('inspected_2025_2026',years.ge(2025)),('inspected_2024_2026',years.ge(2024))]}
    ranking=sorted(ranking,key=lambda r:(not r['eligible'],-(r['score'] if r['score'] is not None else -1e10),r['candidate']))
    selected=next((r['candidate'] for r in ranking if r['eligible'] and r['score']>0),None)
    return {'manifest':MANIFEST,'manifest_sha256':stable_hash(MANIFEST),'selected':selected,'ranking':ranking,
            'reports':reports,'baseline_reports':baselines,'decision_log':decision_log,'go_no_go':'NO_VALIDATED_EDGE'}
