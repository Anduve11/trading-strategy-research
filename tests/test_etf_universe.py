from datetime import date
import gzip
from io import BytesIO
import numpy as np
import pandas as pd
import pytest
from trade_lab.data import generate_synthetic
from trade_lab.etf_universe import PAIRS, aliases, validate_pair, cache_key, download_pair, match_control
from scripts.universe_research import enough_data


def test_real_ticker_mapping_preserves_prices_and_rejects_wrong_pair():
    original = generate_synthetic(2)
    p = PAIRS['semiconductors']
    actual = original.assign(symbol=original.symbol.map({'QQQ': p.proxy, 'TQQQ': p.bull, 'SQQQ': p.bear}))
    result = aliases(actual, p)
    pd.testing.assert_frame_equal(original, result)
    with pytest.raises(ValueError, match='ticker identity'):
        aliases(actual, PAIRS['smallcap'])
    with pytest.raises(ValueError, match='wrong month'):
        validate_pair(actual, p, date(2026, 4, 1))


def test_archive_identity_distinguishes_pairs_and_keeps_actual_tickers():
    a = cache_key('nasdaq2', date(2026, 9, 1))
    b = cache_key('semiconductors', date(2026, 9, 1))
    assert 'QQQ-QLD-QID' in a and 'SOXX-SOXL-SOXS' in b
    assert a != b
    with pytest.raises(ValueError):
        cache_key('../untrusted', date(2026, 9, 1))


def test_comparison_uses_identical_dates_and_windows():
    keys = [{'date': date(2024, 1, n), 'decision_minute': '09:59', 'horizon': 30, 'exit_policy': 'time_only'} for n in (2, 3, 4)]
    a = pd.DataFrame(keys[:2]).assign(net=[1, 2])
    b = pd.DataFrame(keys[1:]).assign(net=[10, 20])
    x, y = match_control(a, b)
    assert x.date.tolist() == y.date.tolist() == [date(2024, 1, 3)]
    assert x.net.tolist() == [2] and y.net.tolist() == [10]
    with pytest.raises(ValueError, match='Duplicate'):
        match_control(pd.concat([a, a]), b)


class Response:
    status_code = 200
    ok = True
    def __init__(self, body):self.body = body
    def json(self):return self.body


class Session:
    def __init__(self):self.calls = []
    def get(self, url, params, headers, timeout):
        self.calls.append(dict(params))
        page = len(self.calls)
        symbol = ('SOXX', 'SOXL', 'SOXS')[page - 1]
        return Response({'bars': {symbol: [{'t': '2024-06-03T13:30:00Z', 'o': page * 10., 'h': page * 10. + 1,
                                          'l': page * 10. - 1, 'c': page * 10. + .5, 'v': 100}]},
                         'next_page_token': str(page) if page < 3 else None})


def test_provider_pagination_collects_real_instrument_prices():
    session = Session()
    x = download_pair('fake', 'fake', PAIRS['semiconductors'], date(2024, 6, 1), date(2024, 6, 30), session=session, delay=0)
    assert set(x.symbol) == {'SOXX', 'SOXL', 'SOXS'}
    assert x.loc[x.symbol.eq('SOXL'), 'open'].iloc[0] == 20.
    assert session.calls[0]['symbols'] == 'SOXX,SOXL,SOXS'
    assert session.calls[0]['feed'] == 'sip' and session.calls[0]['adjustment'] == 'split'
    assert session.calls[1]['page_token'] == '1'


def test_sparse_history_is_ineligible_not_filled():
    assert not enough_data(pd.DataFrame())
    assert not enough_data(pd.DataFrame({'date': pd.bdate_range('2024-01-01', periods=150).date}))
