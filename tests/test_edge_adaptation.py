import json
import runpy
import numpy as np
import pandas as pd
from trade_lab.daily_screen import UNIVERSE
from trade_lab.edge_adaptation import controller,actual_rows,paired_endpoints,run_adaptation


def paired():
    data=pd.DataFrame({'date':pd.bdate_range('2024-01-02',periods=8).date})
    for cost in (10,20,50):
        data[f'bull_net_{cost}bps_pct']=2.
        data[f'bear_net_{cost}bps_pct']=-2.
    return data


def test_decision_precedes_current_outcome_and_can_pause_or_flip():
    data=paired();base=np.ones(len(data),dtype=int)
    a,_=controller(base,data,5,'choose_orientation','both')
    changed=data.copy();changed.loc[5,['bull_net_20bps_pct','bear_net_20bps_pct']]=[-50,50]
    b,log=controller(base,changed,5,'choose_orientation','both')
    assert a[:6].tolist()==b[:6].tolist()==[0,0,0,0,0,1]
    assert b[6]==-1 and log[6]['earlier_paired_opportunities']==6
    gated,_=controller(base,changed,5,'pause_base','both')
    assert gated[6]==0
    bull,_=controller(base,changed,5,'choose_orientation','bull_only')
    assert bull[6]==0


def test_missing_paired_opportunity_does_not_update_or_become_zero():
    data=paired();data.loc[1,'bear_net_20bps_pct']=np.nan
    sides,log=controller(np.ones(len(data),dtype=int),data,5,'pause_base','both')
    assert sides[5]==0 and sides[6]==1
    assert log[5]['earlier_paired_opportunities']==4
    # A planned current trade can have an unknown return; it remains planned.
    data=paired();data.loc[5,'bull_net_20bps_pct']=np.nan
    sides,_=controller(np.ones(len(data),dtype=int),data,5,'pause_base','both')
    assert sides[5]==1 and data.date.iloc[5] not in set(actual_rows(data,sides).date)


def sample():
    data=runpy.run_path('tests/test_research_factory.py')['sample']().head(120).copy()
    data['date']=[d.date() for year in range(2021,2027) for d in pd.bdate_range(f'{year}-01-04',periods=20)]
    data['prior_return_1']=-.03;data['prior_close_range_position']=.1;data['prior_volume_shock']=1.
    calendar={};bars={}
    for day in data.date:
        opening=(pd.Timestamp(day).tz_localize('America/New_York')+pd.Timedelta(hours=9,minutes=30)).tz_convert('UTC')
        closing=opening+pd.Timedelta(minutes=390);calendar[day]=(opening,closing)
        times=[opening+pd.Timedelta(minutes=d) for d in (0,5,15,389)]
        bars[day]=pd.concat([pd.DataFrame({'timestamp':times,'symbol':symbol,'open':100.,'high':106.,'low':94.,
                                        'close':value,'volume':100.}) for symbol,value in [('SOXL',105.),('SOXS',95.)]],ignore_index=True)
    return data,calendar,bars


def test_endpoint_only_time_exit_does_not_require_fabricated_middle_bars():
    data,calendar,bars=sample()
    paired=paired_endpoints(data,UNIVERSE['semiconductors'],calendar,bars,5)
    assert paired.bull_net_20bps_pct.notna().all()
    assert len(bars[data.date.iloc[0]])==8
    assert (paired.bull_net_50bps_pct<paired.bull_net_10bps_pct).all()


def test_grid_retains_all_candidates_and_future_prices_do_not_select():
    data,calendar,bars=sample()
    a=run_adaptation(data,UNIVERSE['semiconductors'],calendar,bars)
    changed={day:x.copy() for day,x in bars.items()}
    for day,x in changed.items():
        if day.year>=2024:
            x.loc[x.timestamp.eq(x.timestamp.max()),['low','close']]=[79.,80.]
    b=run_adaptation(data,UNIVERSE['semiconductors'],calendar,changed)
    assert len(a['ranking'])==108 and len(a['reports'])==108
    assert a['selected'] is not None
    assert a['ranking']==b['ranking'] and a['selected']==b['selected']
    json.dumps(a,allow_nan=False)
