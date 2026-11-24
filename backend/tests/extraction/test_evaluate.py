"""The evaluation counts each kind of mistake the way criterion 1 defines it.

The gold rows here are built from the IRF baseline and then broken on purpose, so every expected
number is known in advance. (The real gold drafts are not used: they were pre-filled from the
baseline, so scoring against them would be circular.)
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from extraction.baseline import parse_report
from extraction.evaluate import GoldRow, score
from tests.extraction.test_baseline import IRF_META, IRF_PAGES


@pytest.fixture(scope="module")
def irf():
    return parse_report(IRF_PAGES, IRF_META).holdings


def gold_from(holdings, draft=False):
    return [
        GoldRow(
            h.row_no,
            h.isin,
            h.value,
            h.weight,
            h.weight_basis.value,
            h.asset_type.value,
            h.held_fund_code,
            draft,
        )
        for h in holdings
    ]


def test_perfect_extraction(irf):
    s = score(irf, gold_from(irf))
    assert (s.f1, s.matched, s.correct) == (1.0, 23, 23)
    assert s.max_weight_error_pp == 0 and s.mistakes == [] and s.gold_verified


def test_missed_row_lowers_recall(irf):
    s = score(irf[:-1], gold_from(irf))
    assert (s.correct, s.precision, s.recall) == (22, 1.0, 22 / 23)
    assert s.mistakes == ["gold row 23: missed (TRYZIPO00394, 32373504.00)"]


def test_wrong_value_is_an_invented_and_a_missed_row(irf):
    wrong = [*irf[:-1], irf[-1].model_copy(update={"value": Decimal("3237350.40")})]
    s = score(wrong, gold_from(irf))
    assert (s.matched, s.correct, s.predicted_rows, s.gold_rows) == (22, 22, 23, 23)
    assert len(s.mistakes) == 2


def test_wrong_fund_code_matches_but_is_not_correct(irf):
    wrong = [h.model_copy(update={"held_fund_code": "DLY"}) if h.row_no == 4 else h for h in irf]
    s = score(wrong, gold_from(irf))
    assert (s.matched, s.correct) == (23, 22)
    assert "wrong held_fund_code" in s.mistakes[0]


def test_weight_error_in_points(irf):
    off = [
        h.model_copy(update={"weight": h.weight + Decimal("0.0015")}) if h.row_no == 4 else h
        for h in irf
    ]
    s = score(off, gold_from(irf))
    assert s.correct == 23  # the weight does not decide correctness: it has its own target
    assert s.max_weight_error_pp == Decimal("0.15")


def test_repeated_lots_are_counted_one_by_one(irf):
    lot = irf[0]
    gold = gold_from([lot, lot.model_copy(update={"row_no": 2})])
    s = score([lot], gold)
    assert (s.matched, s.recall) == (1, 0.5)


def test_other_basis_is_not_scored_for_weight(irf):
    gold = [replace(g, weight_basis="total") for g in gold_from(irf)]
    s = score(irf, gold)
    assert (s.basis_mismatches, s.weight_errors_pp) == (23, [])


def test_draft_gold_is_marked_unverified(irf):
    assert not score(irf, gold_from(irf, draft=True)).gold_verified
