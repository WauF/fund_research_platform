"""ISIN validator tests. ISINs are taken from real reports."""

import pytest

from extraction.isin import (
    check_digit,
    is_valid,
    join_parts,
    normalize,
    ocr_candidates,
    resolve_against_known,
)

REAL_ISINS = [
    # IRF's sub-funds (fund units, W-padded ones included)
    "TRYAKPO00625",
    "TRMDLYWWWWW9",
    "TRMECKWWWWW5",
    "TRYISVH00029",
    "TRYGAPO00029",
    "TRYGAPO00615",
    "TRMBD1WWWWW5",
    "TRYA1PY00313",
    "TRYISTP00539",
    "TRYISPO00969",
    "TRYISTP00836",
    "TRYNRPO00144",
    "TRYQPYS00300",
    "TRYYAPO00865",
    "TRYA1PY00537",
    "TRYDUUM00010",
    "TRYTEBP00187",
    "TRYTRPY00058",
    "TRYTACP00019",
    "TRYZIPO00394",
    # other asset types
    "TRAAEFES91A9",
    "TRAAKBNK91N6",  # hisse (GTM)
    "TRENETG00027",  # hisse (IRF, NETGL)
    "TRT090130T12",  # devlet tahvili (TE4)
    "TRSKCTF22718",  # corporate bond (GTF)
    "TRVXIST05P68",  # VİOP future (ICH)
    "US77926X3200",  # foreign ETF (ECA, DRAM)
    "TRMTYHWWWWW3",  # TYH inside TE4, printed over two lines
]


@pytest.mark.parametrize("isin", REAL_ISINS)
def test_real_isins_valid(isin):
    assert is_valid(isin)


@pytest.mark.parametrize(
    "isin",
    [
        "TRYAKPO00626",  # wrong check digit
        "TRYAKPO0062",  # 11 karakter
        "1RYAKPO00625",  # digit in country code
        "TRYAKPO0062X",  # kontrol hanesi harf
        "",
    ],
)
def test_invalid(isin):
    assert not is_valid(isin)


def test_check_digit():
    assert check_digit("TRYAKPO0062") == 5
    with pytest.raises(ValueError):
        check_digit("TRY")


def test_normalize():
    assert normalize(" trmdlyWWWW\nW9 ") == "TRMDLYWWWWW9"


def test_join_split_isin():
    # DLY row of the IRF report: ISIN split over two lines
    assert join_parts("TRMDLYWWWW", "W9") == "TRMDLYWWWWW9"
    assert join_parts("TRMTYHWWWW", "W3") == "TRMTYHWWWWW3"
    assert join_parts("TRMDLYWWWW", "W8") is None


def test_check_digit_does_not_catch_ocr_o_zero_swap():
    # Scanned NJR report: OCR read 'TRYNRPOO0789'. Both are valid ISINs!
    assert is_valid("TRYNRPOO0789")
    assert is_valid("TRYNRPO00789")


def test_ocr_candidates_include_true_isin():
    cands = ocr_candidates("TRYNRPOO0789")
    assert "TRYNRPO00789" in cands
    assert "TRYNRPOO0789" in cands  # the input is valid too and stays in the list
    assert all(is_valid(c) for c in cands)


def test_resolve_against_known_ocr_isin():
    known = {"TRYNRPO00144", "TRYNRPO00789", "TRYNRPO00508"}  # Nurol funds
    assert resolve_against_known("TRYNRPOO0789", known) == "TRYNRPO00789"
    assert resolve_against_known("TRYNRPOO0508", known) == "TRYNRPO00508"


def test_resolve_against_known_unknown_or_ambiguous():
    assert resolve_against_known("TRYNRPOO0789", {"TRYAKPO00625"}) is None
    assert resolve_against_known("TRYNRPOO0789", {"TRYNRPO00789", "TRYNRPOO0789"}) is None


def test_ocr_candidates_wrong_length():
    assert ocr_candidates("TRYAKPO006") == []
