"""Number parser tests. Examples are taken from real reports (named in the comments)."""

from decimal import Decimal

import pytest

from extraction.numbers import detect_format, parse_number, parse_percent


@pytest.mark.parametrize(
    "text,expected",
    [
        ("378.395.976,36", "378395976.36"),  # IRF total value
        ("-11.047.843,53", "-11047843.53"),  # IRF liabilities
        ("1.085,71", "1085.71"),  # IRF cash equivalents
        ("2.767.848.836,470", "2767848836.470"),  # ZPO, 3 decimals
        ("60.000,00", "60000.00"),
        ("25,520000", "25.520000"),
        ("0,00", "0.00"),
        ("12", "12"),
        ("1234567,5", "1234567.5"),  # no thousands separator
        ("(11,11)", "-11.11"),  # parantezli eksi
        ("−11.047.843,53", "-11047843.53"),  # unicode eksi
        (" 9.754.344,52 ", "9754344.52"),
    ],
)
def test_tr(text, expected):
    assert parse_number(text, "tr") == Decimal(expected)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("975,489,543.87", "975489543.87"),  # GTM total value
        ("131,084,687", "131084687"),  # GTM unit count, no decimals
        ("7.441674", "7.441674"),  # GTM unit price
        ("100,000,000.00", "100000000.00"),
        ("-5,001,152.98", "-5001152.98"),
    ],
)
def test_en(text, expected):
    assert parse_number(text, "en") == Decimal(expected)


@pytest.mark.parametrize("text", ["", "-", "  ", "–"])
def test_missing_values(text):
    assert parse_number(text, "tr") is None


@pytest.mark.parametrize(
    "text,fmt",
    [
        ("975,489,543.87", "tr"),  # Garanti number read as Turkish
        ("378.395.976,36", "en"),  # Turkish number read as English
        ("1.23,4", "tr"),  # bozuk gruplama
        ("12a,5", "tr"),
        ("1.234.56", "tr"),
    ],
)
def test_format_mismatch_raises(text, fmt):
    with pytest.raises(ValueError):
        parse_number(text, fmt)


def test_ambiguous_value_depends_on_format():
    # Why the format is never guessed: the same text is a different number in each format.
    assert parse_number("1,234", "tr") == Decimal("1.234")
    assert parse_number("1,234", "en") == Decimal("1234")


def test_unknown_format():
    with pytest.raises(ValueError):
        parse_number("1", "de")


@pytest.mark.parametrize(
    "text,fmt,expected",
    [
        ("%1,63", "tr", "0.0163"),  # EIB, Astra format
        ("12,02", "tr", "0.1202"),  # IRF, column without % sign
        ("0,385880", "tr", "0.00385880"),  # ZPO
        ("0.07%", "en", "0.0007"),  # GTM
        ("-8.12%", "en", "-0.0812"),
        ("100.33%", "en", "1.0033"),  # GTM: portfolio value above total value
        ("-", "tr", None),
    ],
)
def test_percent(text, fmt, expected):
    result = parse_percent(text, fmt)
    assert result == (None if expected is None else Decimal(expected))


def test_detect_format():
    irf = [
        "D-)Toplam Değer/Net Varlık Değeri : 378.395.976,36",
        "BGP ... 40.073.740,62 12,93 12,02 10,59",
    ]
    gtm = ["D. TOPLAM DEĞER: (TL) 975,489,543.87", "AEFES.E ... 633,845.68 0.07% 0.06%"]
    assert detect_format(irf) == "tr"
    assert detect_format(gtm) == "en"
    assert detect_format(["0,00", "12"]) is None  # no evidence
    assert detect_format(irf + gtm) is None  # equal evidence: no decision
