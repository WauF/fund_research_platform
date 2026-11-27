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
            row_no=h.row_no,
            name=h.name,
            isin=h.isin,
            instrument_code=h.instrument_code,
            currency=h.currency,
            value=h.value,
            weight=h.weight,
            weight_basis=h.weight_basis.value,
            asset_type=h.asset_type.value,
            held_fund_code=h.held_fund_code,
            draft=draft,
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


@pytest.fixture(scope="module")
def deposit(irf):
    # TEB deposit: no ISIN and no instrument code (a bank is not a code), so only the name tells
    # the instrument apart.
    assert (irf[1].isin, irf[1].instrument_code) == (None, None)
    return irf[1]


def test_row_without_isin_needs_the_right_name(deposit):
    # Review on #23: a row without an ISIN used to match on its value alone.
    gold = gold_from([deposit])
    s = score([deposit.model_copy(update={"name": "TOTALLY WRONG BANK"})], gold)
    assert (s.matched, s.correct, s.f1) == (0, 0, 0.0)
    assert s.mistakes == [
        f"row 2: not in gold (TOTALLY WRONG BANK, {deposit.value})",
        f"gold row 2: missed (TEB A.Ş., {deposit.value})",
    ]


def test_row_without_isin_needs_the_right_currency(deposit):
    assert (
        score([deposit.model_copy(update={"currency": "USD"})], gold_from([deposit])).correct == 0
    )


def test_name_spelling_is_not_a_mistake(deposit):
    assert deposit.name == "TEB A.Ş."
    respelled = deposit.model_copy(update={"name": " teb  a ş "})
    assert score([respelled], gold_from([deposit])).correct == 1


@pytest.mark.parametrize(
    ("name", "same"),
    [
        ("TEB A.Ş. mevduat (vade 01/10/26)", True),  # the recorded LLM run's style
        ("Mevduat: TEB A.Ş.", True),
        ("GARANTİ A.Ş.", False),  # shares "A.Ş." but is another bank
        ("TEBA A.Ş.", False),  # whole words only
    ],
)
def test_longer_name_with_the_same_words_matches(deposit, name, same):
    s = score([deposit.model_copy(update={"name": name})], gold_from([deposit]))
    assert s.correct == int(same)


def test_instrument_code_decides_over_name(irf):
    # The labelling guide writes the full company name (NETGL -> NET GLOBAL ...); the code still
    # identifies the row. NETGL has an ISIN, so the ISIN is dropped here to test the code path.
    netgl = irf[0].model_copy(update={"isin": None})
    gold = gold_from([netgl])
    gold = [replace(gold[0], name="NET GLOBAL ENDÜSTRİYEL YATIRIMLAR AŞ")]
    assert score([netgl], gold).correct == 1
    other_code = netgl.model_copy(update={"instrument_code": "OTHER"})
    assert score([other_code], gold).correct == 0


def test_candidate_order_does_not_decide_correctness(irf):
    # Two gold rows with the same key, the wrong one first: the right one must still be picked.
    lot = irf[3]  # BGP fund row
    right = gold_from([lot])[0]
    wrong = replace(right, row_no=99, held_fund_code="DLY")
    s = score([lot], [wrong, right])
    assert (s.matched, s.correct) == (1, 1)
    assert s.mistakes == [f"gold row 99: missed ({lot.isin}, {lot.value})"]
