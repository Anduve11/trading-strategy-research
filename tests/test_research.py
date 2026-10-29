from datetime import date
from dataclasses import replace
import pandas as pd
import pytest

from trade_lab.data import ET, generate_synthetic
from trade_lab.engine import Config
from trade_lab.research import Candidate, calendar_quarters, default_candidates, run_study, select_development_winner, year_partitions


def test_research_partitions_do_not_overlap():
    p = year_partitions(2019, 2026)
    assert [y for y, s in p.items() if s == 'Development'] == list(range(2019, 2024))
    assert [y for y, s in p.items() if s == 'Validation'] == [2024]
    assert [y for y, s in p.items() if s == 'Final holdout'] == [2025, 2026]
    assert len(default_candidates()) == 16
    qs = list(calendar_quarters(date(2024, 11, 15), date(2025, 4, 4)))
    assert qs == [(date(2024,11,15),date(2024,12,31)),(date(2025,1,1),date(2025,3,31)),(date(2025,4,1),date(2025,4,4))]


def test_multiyear_study_compounds_and_selects_only_development():
    # Synthetic bars here validate calculations only, not trading performance.
    calls = []
    def fake_fetch(start: str, end: str):
        calls.append((start, end))
        base = generate_synthetic(9)
        desired = pd.Timestamp(start, tz=ET)
        actual = base.timestamp.min().tz_convert(ET).normalize()
        base['timestamp'] = base.timestamp + (desired - actual)
        return base

    candidates = [Candidate('EMA trend', 1.5, 1.0), Candidate('Opening range breakout', 2.0, 1.5)]
    report = run_study(fake_fetch, date(2024,1,1), date(2026,12,31),
                       Config(initial_capital=10000,allocation_pct=10), candidates=candidates)
    assert len(calls) == 12
    assert len(report['results']) == 6
    assert set(report['results'].period) == {'Development','Validation','Final holdout'}
    assert set(report['annual_results'].year) == {2024,2025,2026}
    assert set(report['equity_curve'].candidate) == {c.label() for c in candidates}
    for name in [c.label() for c in candidates]:
        each_year = report['annual_results'].loc[report['annual_results'].candidate == name].sort_values('year')
        assert len(each_year) == 3
        assert each_year.iloc[0].starting_equity == pytest.approx(10000.0, abs=0.01)
        assert each_year.ending_equity.to_list()[:-1] == pytest.approx(each_year.starting_equity.to_list()[1:], abs=0.03)
        rows = report['results'][report['results'].candidate == name]
        train = rows[rows.period == 'Development'].iloc[0]
        valid = rows[rows.period == 'Validation'].iloc[0]
        test = rows[rows.period == 'Final holdout'].iloc[0]
        assert train.ending_equity == pytest.approx(valid.starting_equity, abs=0.015)
        assert valid.ending_equity == pytest.approx(test.starting_equity, abs=0.015)
        assert train.trades <= 36 and valid.trades <= 36 and test.trades <= 36
    selection = select_development_winner(report, min_trades=9999)
    assert selection['qualified'] is False
    assert selection['winner'] in [c.label() for c in candidates]
    assert len(selection['selected']) == 3


def test_fails_on_missing_full_quarter():
    with pytest.raises(ValueError, match='No market data'):
        run_study(lambda start, end: pd.DataFrame(), date(2024,1,1), date(2026,12,31),
                  Config(), candidates=[Candidate('EMA trend',1.5,1)])