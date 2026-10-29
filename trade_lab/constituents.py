"""Nasdaq constituent research universe and point-in-time filing utilities.

IMPORTANT: This is a *fixed 2026-10-16 snapshot*, not reconstructed historical
QQQ membership. Prior to 2026-10-16, basket aggregates are biased by hindsight
selection. Never use the 2026 weights for historical research or claim a PIT index.
"""
from __future__ import annotations
import pandas as pd
import numpy as np

AS_OF = '2026-10-16'
# Official Invesco QQQ top ten SECURITY positions as reported 2026-10-16.
CURRENT_SECURITIES = {'NVDA': 8.15, 'AAPL': 7.92, 'MSFT': 6.21,
    'MU': 4.33, 'AMZN': 4.26, 'AMD': 3.76, 'META': 3.33,
    'GOOGL': 3.16, 'TSLA': 2.94, 'GOOG': 2.94}
SYMBOLS = tuple(CURRENT_SECURITIES)
# Alphabet dual classes share the same issuer / SEC companyfacts.
ISSUER_SYMBOLS = ('NVDA','AAPL','MSFT','MU','AMZN','AMD','META','GOOGL','TSLA')


def validate_filing_facts(data: dict, metric: str, unit='USD') -> pd.DataFrame:
    """Return time-available XBRL facts; filing date, NOT fiscal period end, is first seen.

    SEC data is historical but current JSON can contain restated prior values.
    Filter by original filing accession and its original filed date; allow all
    original submissions, never treat fiscal quarter end as publish date.
    """
    gaap=data.get('facts',{}).get('us-gaap',{})
    tags={
      'revenue':('RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet'),
      'net_income':('NetIncomeLoss',),
      'operating_income':('OperatingIncomeLoss',),
      'assets':('Assets',),
      'diluted_eps':('EarningsPerShareDiluted',)
    }
    if metric not in tags:raise ValueError('Unknown filing metric')
    unit='USD/shares' if metric=='diluted_eps' else unit
    for tag in tags[metric]:
        if tag in gaap and unit in gaap[tag].get('units',{}):
            rows=gaap[tag]['units'][unit]
            break
    else:return pd.DataFrame(columns=['filed','available_date','end','val','accn','form','fy','fp'])
    df=pd.DataFrame(rows)
    req={'filed','end','val','form','accn'}
    if not req.issubset(df.columns):return pd.DataFrame(columns=['filed','available_date','end','val','accn','form','fy','fp'])
    df=df.loc[df.form.isin(['10-Q','10-K','10-Q/A','10-K/A'])].copy()
    df['filed']=pd.to_datetime(df.filed,errors='coerce').dt.date
    df['end']=pd.to_datetime(df.end,errors='coerce').dt.date
    df['val']=pd.to_numeric(df.val,errors='coerce')
    df=df.dropna(subset=['filed','end','val'])
    df['available_date']=(pd.to_datetime(df.filed)+pd.Timedelta(days=1)).dt.date
    for col in ('fy','fp'):
        if col not in df:df[col]=None
    # Preserve period and filing id; newer revisions must not overwrite older vintages.
    return df[['filed','available_date','end','val','accn','form','fy','fp']].drop_duplicates().sort_values(['available_date','end']).reset_index(drop=True)


def asof_filing(facts: pd.DataFrame, decision_day) -> dict | None:
    """Most recent quarter/fiscal report actually filed before day, no future values."""
    if facts.empty:return None
    day=pd.Timestamp(decision_day).date()
    available=facts.loc[facts.available_date<=day]
    if available.empty:return None
    # Newest disclosure timestamp wins; prefer newest underlying fiscal period.
    row=available.sort_values(['available_date','end']).iloc[-1]
    return {'value':float(row.val),'filed':str(row.filed),'period_end':str(row.end), 'accn':str(row.accn)}


def aggregate_filing_features(decisions:pd.DataFrame,issuer_facts: dict[str, dict[str, pd.DataFrame]]) -> pd.DataFrame:
    """Equal-issuer (not retrospectively weighted QQQ) PIT aggregates.

    A single company can contain stale or unavailable metrics; expose coverage.
    We do not backfill nonexistent values with future reports.
    """
    out=[]
    for day in pd.to_datetime(decisions.date).dt.date:
        margins=[]; opmargins=[]; available=0; files_30=0
        for issuer in ISSUER_SYMBOLS:
            metrics=issuer_facts.get(issuer,{})
            revenue=asof_filing(metrics.get('revenue',pd.DataFrame()),day)
            income=asof_filing(metrics.get('net_income',pd.DataFrame()),day)
            operating=asof_filing(metrics.get('operating_income',pd.DataFrame()),day)
            if revenue and income and revenue['value']>0 and revenue['period_end']==income['period_end']:
                margins.append(income['value']/revenue['value'])
            if revenue and operating and revenue['value']>0 and revenue['period_end']==operating['period_end']:
                opmargins.append(operating['value']/revenue['value'])
            if revenue:
                available+=1
                files_30+=0 <= (day-pd.Timestamp(revenue['filed']).date()).days <= 30
        out.append({'date':day,
           'issuer_profit_margin_mean':float(np.mean(margins)) if margins else np.nan,
           'issuer_operating_margin_mean':float(np.mean(opmargins)) if opmargins else np.nan,
           'issuer_filing_coverage':available/len(ISSUER_SYMBOLS),
           'issuer_recent_reports_30d':int(files_30),
           'issuer_margin_coverage':len(margins)/len(ISSUER_SYMBOLS)})
    return pd.DataFrame(out)

# Verified issuer identifiers must be checked against official SEC company list
# when adding new firms; GOOGL and GOOG represent the same issuer.
SEC_CIKS={'NVDA':1045810,'AAPL':320193,'MSFT':789019,'MU':723125,
          'AMZN':1018724,'AMD':2488,'META':1326801,'GOOGL':1652044,'TSLA':1318605}


def fetch_companyfacts(user_agent:str, session=None)->dict[str,dict[str,pd.DataFrame]]:
    """SEC EDGAR XBRL filings. Require user-owned identifying User-Agent.

    Never include future-filed statements at a historical decision date.
    A revision reported later remains associated with its later filing date.
    SEC latest feed is not a full historical vintage, so results are exploratory.
    """
    import requests,time
    if not user_agent or '@' not in user_agent:
        raise ValueError('SEC_USER_AGENT must identify a contact email and application')
    sess=session or requests.Session()
    rows={}
    for issuer,cik in SEC_CIKS.items():
        r=sess.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json',
            headers={'User-Agent':user_agent,'Accept-Encoding':'gzip','Accept':'application/json'},timeout=90)
        if not r.ok:raise RuntimeError(f'SEC historical facts fetch failed for {issuer} HTTP {r.status_code}')
        d=r.json()
        rows[issuer]={m:validate_filing_facts(d,m) for m in ('revenue','net_income','operating_income')}
        time.sleep(.35)  # Respect SEC fair-access rate limit.
    return rows