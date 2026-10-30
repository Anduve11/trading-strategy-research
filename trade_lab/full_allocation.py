"""Full-equity paper replays and declared growth selectors; never orders."""
import numpy as np
import pandas as pd
from .research_factory import candidates,policy_returns,stable_hash
from .reversal_research import reversal_sides
from .sizing_research import size_metrics

MANIFEST={'version':'full_equity_v1','allocations':[.1,1.],
    'cost_bps_per_side':[10,20,50],'development_years':[2021,2022,2023],
    'single_position_replays_per_pair':49,'declared_rules_per_pair':48,
    'new_policies':['development_growth','development_fold_resilience',
                    'quarterly_growth','active_weight_family_ensemble'],
    'frozen_policy_controls':['fixed_slot_family_ensemble','original_quarterly_selector'],
    'growth_score':'mean log(1 + full-equity net position return at 20bps), including cash days',
    'frozen_eligibility':'75 development trades and 10 in each development year',
    'rolling_eligibility':'250 training observations, 40 trades, 504-observation window, 2-observation embargo',
    'growth_cash_gate':True,'active_allocation':'100% total across active ETF legs; cash on no signal',
    'no_account_borrowing':True,'historical_status':'All evaluation years already inspected'}


def with_cost_stress(data):
    out=data.copy()
    # Recover the same observed close/open ratio from its 10bps net return.
    # This changes the assumed adverse fill price, never the observed path.
    adjustment=((1-.005)/(1+.005))/((1-.001)/(1+.001))
    for side in ('tqqq','sqqq'):
        out[f'{side}_net_50bps_pct']=100*((1+out[f'{side}_net_10bps_pct']/100)*adjustment-1)
    return out


def net_returns(data,sides,cost):
    sides=np.asarray(sides)
    if len(sides)!=len(data) or not np.isin(sides,[-1,0,1]).all():raise ValueError('Invalid directions')
    r=np.where(sides==1,data[f'tqqq_net_{cost}bps_pct'],
               np.where(sides==-1,data[f'sqqq_net_{cost}bps_pct'],0.))/100
    if not np.isfinite(r).all() or (r<=-1).any():raise ValueError('Invalid position returns')
    return r


def risk_metrics(data,sides,allocation,cost):
    m=size_metrics(data,sides,allocation,cost)
    r=allocation*net_returns(data,sides,cost)
    equity=np.r_[1.,np.cumprod(1+r)];dd=equity/np.maximum.accumulate(equity)-1
    m['worst_session_return_pct']=float(100*r.min())
    m['best_session_return_pct']=float(100*r.max())
    m['sessions_below_peak']=int((dd[1:]<0).sum())
    m['drawdown_breach_sessions']={str(p):int((dd[1:]<=-p/100).sum()) for p in (25,50,75,90)}
    m['recovery_needed_from_max_drawdown_pct']=float(100*(1/(1+dd.min())-1)) if dd.min()>-1 else None
    m['ever_below_half_starting_equity']=bool(equity.min()<=.5)
    streak=longest=0
    # Cash days do not erase a run of losing trades.
    for value in r[np.asarray(sides)!=0]:
        streak=streak+1 if value<0 else 0;longest=max(longest,streak)
    m['max_consecutive_losing_trades']=longest
    return m


def signal_report(data,sides,allocation,capital_fraction=None):
    capital=(np.asarray(sides)!=0).astype(float) if capital_fraction is None else np.asarray(capital_fraction)
    result={f'cost_{c}bps':risk_metrics(data,sides,allocation,c) for c in (10,20,50)}
    for cost in (10,20,50):result[f'cost_{cost}bps']['mean_capital_deployed_pct']=float(100*allocation*capital.mean())
    r=net_returns(data,sides,10);positive=np.flatnonzero((np.asarray(sides)!=0)&(r>0))
    ordered=positive[np.argsort(-r[positive])]
    result['skip_best_winning_sessions']={}
    for count in (1,3,5):
        altered=np.array(sides,copy=True);altered[ordered[:count]]=0
        m=risk_metrics(data,altered,allocation,10)
        m['mean_capital_deployed_pct']=float(100*allocation*np.mean(capital*(altered!=0)))
        result['skip_best_winning_sessions'][str(count)]={'removed_winners':min(count,len(ordered)),**m}
    quarters=pd.to_datetime(data.date).dt.to_period('Q')
    result['quarters_10bps']={}
    for q in sorted(quarters.unique()):
        mask=quarters==q;m=risk_metrics(data.loc[mask],np.asarray(sides)[mask],allocation,10)
        m['mean_capital_deployed_pct']=float(100*allocation*capital[mask].mean())
        result['quarters_10bps'][str(q)]=m
    return result


def rule_grid(data):
    grid={key:value['sides'] for key,value in candidates(data).items()}
    grid.update({'reversal__'+key:sides for key,sides in reversal_sides(data).items()})
    if len(grid)!=48:raise ValueError('Declared grid changed')
    return grid


def growth_ranking(data,grid,train,min_trades,annual_min=None):
    if len(train)==0:raise ValueError('Empty training window')
    rows=[];years=pd.to_datetime(data.date).dt.year
    for key,sides in grid.items():
        r=net_returns(data.iloc[train],sides[train],20)
        count=int((sides[train]!=0).sum())
        counts=[int((sides[train][years.iloc[train].to_numpy()==y]!=0).sum()) for y in (2021,2022,2023)]
        eligible=count>=min_trades and (annual_min is None or min(counts)>=annual_min)
        score=float(np.log1p(r).mean())
        rows.append({'candidate':key,'eligible':bool(eligible),'score':score,'trades':count,
                     'train_first_date':str(data.iloc[train[0]].date),'train_last_date':str(data.iloc[train[-1]].date)})
    return sorted(rows,key=lambda x:(not x['eligible'],-x['score'],x['candidate']))


def choose_growth(ranking):
    return next((r['candidate'] for r in ranking if r['eligible'] and r['score']>0),None)


def frozen_slots(data,grid,source):
    chosen=source['selected_by_family']
    slots=np.column_stack([grid[key] if key else np.zeros(len(data),dtype=int) for key in chosen.values()])
    original=np.zeros((len(data),1),dtype=int)
    quarters=pd.to_datetime(data.date).dt.to_period('Q').astype(str)
    for row in source['quarterly_decisions']:
        key=row['selected']
        if key:original[quarters==row['quarter'],0]=grid[key][quarters==row['quarter']]
    return slots,original


def active_weight_returns(data,slots,cost):
    slots=np.asarray(slots)
    active=(slots!=0).sum(axis=1)
    total=policy_returns(data,slots,cost)*slots.shape[1]
    # Equal weight only the active legs. No signal => cash; any signal => 100%.
    return np.divide(total,active,out=np.zeros(len(data)),where=active>0)


def run_full_equity(data,source):
    data=with_cost_stress(data);grid=rule_grid(data);years=pd.to_datetime(data.date).dt.year
    dev=np.flatnonzero(years.between(2021,2023))
    if any(not years.eq(y).any() for y in (2021,2022,2023)):raise ValueError('Missing development years')
    ranking=growth_ranking(data,grid,dev,75,10);growth=choose_growth(ranking)
    fold_rows=[]
    for key,sides in grid.items():
        folds=[size_metrics(data.loc[years.eq(y)],sides[years.eq(y)],1.,20) for y in (2021,2022,2023)]
        returns=[m['return_pct'] for m in folds];counts=[m['active_sessions'] for m in folds]
        score=min(returns)+.25*np.mean(returns)-.5*max(abs(m['max_close_to_close_drawdown_pct']) for m in folds)
        fold_rows.append({'candidate':key,'eligible':sum(counts)>=75 and min(counts)>=10,
                          'score':float(score),'fold_returns_20bps':returns})
    fold_rows=sorted(fold_rows,key=lambda x:(not x['eligible'],-x['score'],x['candidate']))
    resilient=choose_growth(fold_rows)
    policy_sides={'development_growth':grid[growth] if growth else np.zeros(len(data),dtype=int),
                  'development_fold_resilience':grid[resilient] if resilient else np.zeros(len(data),dtype=int)}
    rolling=np.zeros(len(data),dtype=int);decisions=[]
    quarters=pd.to_datetime(data.date).dt.to_period('Q')
    for quarter in sorted(quarters.unique()):
        if quarter.year<2024:continue
        test=np.flatnonzero(quarters==quarter);train=np.arange(max(0,test[0]-2))[-504:]
        selected=None;rank=[]
        if len(train)>=250:
            rank=growth_ranking(data,grid,train,40);selected=choose_growth(rank)
            if selected:rolling[test]=grid[selected][test]
        decisions.append({'quarter':str(quarter),'selected':selected,'ranking':rank})
    policy_sides['quarterly_growth']=rolling
    slots,original=frozen_slots(data,grid,source)
    # Controls preserve earlier choices exactly. Normalizing active slots is a
    # separately registered policy, rather than silently changing the control.
    pseudo={}
    for name in ('fixed_slot_family_ensemble','original_quarterly_selector','active_weight_family_ensemble'):
        frame=data[['date']].copy()
        relevant=original if name=='original_quarterly_selector' else slots
        active=(relevant!=0).any(axis=1).astype(int)
        for cost in (10,20,50):
            values=(active_weight_returns(data,relevant,cost) if name=='active_weight_family_ensemble'
                    else policy_returns(data,relevant,cost))
            frame[f'tqqq_net_{cost}bps_pct']=values;frame[f'sqqq_net_{cost}bps_pct']=0.
        pseudo[name]=(frame,active,((relevant!=0).mean(axis=1) if name=='fixed_slot_family_ensemble' else active))
    all_signals={**grid,'frozen_adaptive_incumbent':data.frozen_incumbent_side.to_numpy(dtype=int)}
    periods=[('development_2021_2023',years.between(2021,2023)),('inspected_2024',years.eq(2024)),
             ('inspected_2025_2026',years.ge(2025)),('inspected_2024_2026',years.ge(2024))]
    individual={};policies={}
    for label,mask in periods:
        individual[label]={key:{str(allocation):{f'cost_{cost}bps':risk_metrics(data.loc[mask],sides[mask],allocation,cost)
                                                for cost in (10,20,50)} for allocation in (.1,1.)}
                           for key,sides in all_signals.items()}
        if label=='development_2021_2023':continue
        policies[label]={name:signal_report(data.loc[mask],sides[mask],1.) for name,sides in policy_sides.items()}
        for name,(frame,active,capital) in pseudo.items():
            policies[label][name]=signal_report(frame.loc[mask],active[mask],1.,capital[mask])
    # All 49 signals receive winner-concentration diagnostics at full equity,
    # without selecting a later-period winner. Preserve primary details in one artifact.
    signal_diagnostics={label:{key:signal_report(data.loc[mask],sides[mask],1.) for key,sides in all_signals.items()}
                        for label,mask in periods if label!='development_2021_2023'}
    replay=data[['date']].copy()
    for key,sides in all_signals.items():replay['signal__'+key]=sides
    for name,sides in policy_sides.items():replay['policy__'+name]=sides
    return {'manifest':MANIFEST,'manifest_sha256':stable_hash(MANIFEST),'growth_ranking':ranking,
            'fold_ranking':fold_rows,'selected_growth':growth,'selected_fold_resilience':resilient,
            'quarterly_decisions':decisions,'individual_reports':individual,'policy_reports':policies,
            'signal_diagnostics':signal_diagnostics,'go_no_go':'NO_VALIDATED_EDGE'},replay
