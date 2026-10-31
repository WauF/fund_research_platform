"""Rule-based baseline on the real IRF report text (tests/extraction/data/, pdfplumber output).

Expected values come from data/irf_look_through_elle.csv, built by hand from the PDF.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from extraction.baseline import (
    ReportMeta,
    UnsupportedTemplate,
    check_template,
    detect_meta,
    parse_report,
)
from extraction.validation import validate_report
from schemas.holding import AssetType, ReportKind, Status, WeightBasis

DATA = Path(__file__).parent / "data"
IRF_PAGES = json.loads((DATA / "irf_2026-09_pages.json").read_text(encoding="utf-8"))["pages"]
IRF_META = ReportMeta("IRF", date(2026, 9, 28), date(2026, 10, 2), ReportKind.WEEKLY)

# (KAP code, ISIN, value TL, weight of portfolio value) for IRF's 20 sub-funds.
IRF_FUNDS = [
    ("BGP", "TRYAKPO00625", "40073740.62", "0.1202"),
    ("DLY", "TRMDLYWWWWW9", "31610615.00", "0.0950"),
    ("ECA", "TRMECKWWWWW5", "2370258.82", "0.0071"),
    ("EIB", "TRYISVH00029", "4818269.52", "0.0145"),
    ("GPB", "TRYGAPO00029", "5977044.08", "0.0180"),
    ("GPZ", "TRYGAPO00615", "30688335.00", "0.0922"),
    ("GTF", "TRMBD1WWWWW5", "2545857.88", "0.0077"),
    ("ICH", "TRYA1PY00313", "4373450.36", "0.0131"),
    ("ICN", "TRYISTP00539", "157553.45", "0.0005"),
    ("IOO", "TRYISPO00969", "39578963.29", "0.1189"),
    ("IRB", "TRYISTP00836", "37112177.64", "0.1115"),
    ("NJR", "TRYNRPO00144", "4351779.74", "0.0131"),
    ("PGD", "TRYQPYS00300", "2152620.61", "0.0065"),
    ("PPI", "TRYYAPO00865", "30913961.00", "0.0929"),
    ("PTO", "TRYA1PY00537", "3724488.84", "0.0112"),
    ("SUA", "TRYDUUM00010", "10796492.03", "0.0324"),
    ("TE4", "TRYTEBP00187", "11508509.11", "0.0346"),
    ("TMV", "TRYTRPY00058", "261168.05", "0.0008"),
    ("TPF", "TRYTACP00019", "14822492.96", "0.0445"),
    ("ZBJ", "TRYZIPO00394", "32373504.00", "0.0973"),
]


@pytest.fixture(scope="module")
def irf():
    return parse_report(IRF_PAGES, IRF_META)


def test_irf_row_count_and_types(irf):
    types = [h.asset_type for h in irf.holdings]
    assert len(types) == 23
    assert types.count(AssetType.FUND) == 20
    assert types[:3] == [AssetType.EQUITY, AssetType.DEPOSIT, AssetType.CASH]
    assert irf.warnings == []


@pytest.mark.parametrize("code,isin,value,weight", IRF_FUNDS)
def test_irf_sub_fund_matches_reference(irf, code, isin, value, weight):
    (h,) = [h for h in irf.holdings if h.held_fund_code == code]
    assert (h.isin, h.value, h.weight) == (isin, Decimal(value), Decimal(weight))
    assert h.weight_basis is WeightBasis.PORTFOLIO


def test_irf_split_isin_joined(irf):
    # DLY's ISIN is printed as 'TRMDLYWWWW' and 'W9' on two lines.
    (dly,) = [h for h in irf.holdings if h.held_fund_code == "DLY"]
    assert dly.isin == "TRMDLYWWWWW9"


def test_irf_non_fund_rows(irf):
    netgl, teb, viop = irf.holdings[:3]
    assert (netgl.instrument_code, netgl.isin, netgl.value) == (
        "NETGL",
        "TRENETG00027",
        Decimal("977400.00"),
    )
    assert teb.value == Decimal("9754344.52")
    # VİOP collateral has no FTD column: the reading with value / FPD = 3.58% must win.
    assert (viop.value, viop.weight) == (Decimal("11927534.70"), Decimal("0.0358"))


def test_irf_summary(irf):
    s = irf.summary
    assert s.portfolio_value == Decimal("332870561.22")
    assert s.receivables == Decimal("56572172.96")
    assert s.liabilities == Decimal("-11047843.53")
    assert s.total_value == Decimal("378395976.36")
    assert s.page == 2


def test_irf_passes_validation(irf):
    result = validate_report(irf.holdings, irf.summary, IRF_PAGES)
    assert result.ok, result.issues
    assert all(h.status is Status.OK for h in result.holdings)


def test_quotes_and_pages_are_real(irf):
    for h in irf.holdings:
        assert h.quote in IRF_PAGES[h.page - 1]


def test_weekly_report_without_dates_needs_meta():
    # IRF's header says only "Eylül-2026" although the report is weekly.
    with pytest.raises(UnsupportedTemplate, match="weekly"):
        detect_meta(IRF_PAGES)


def test_detect_meta_from_date_range():
    page = IRF_PAGES[0].replace("Eylül-2026", "28/09/2026 - 02/10/2026", 1)
    meta = detect_meta([page, *IRF_PAGES[1:]])
    assert meta == IRF_META


def test_detect_meta_monthly():
    pages = [
        p.replace("HAFTA İÇİNDE", "AY İÇİNDE").replace("Haftalık Pay", "Aylık Pay")
        for p in IRF_PAGES
    ]
    meta = detect_meta(pages)
    assert (meta.period_start, meta.period_end, meta.report_kind) == (
        date(2026, 9, 1),
        date(2026, 9, 30),
        ReportKind.MONTHLY,
    )


@pytest.mark.parametrize(
    "pages,reason",
    [
        (["", ""], "scanned"),  # NJR, NLK: no text layer
        (
            ["YATIRIM FONLARI PORTFÖY DAĞILIM RAPORU\nRapor Dönemi 01/09/2026"],
            "standard",
        ),  # Garanti
    ],
)
def test_other_templates_rejected(pages, reason):
    with pytest.raises(UnsupportedTemplate, match=reason):
        parse_report(pages, IRF_META)


def test_report_start_page_found_when_pages_out_of_order():
    # TPF's PDF starts with section VIII; the title page comes later.
    first = check_template(["VIII-İTFALAR\n...", *IRF_PAGES])
    assert first[0].startswith("IRF-")


def test_short_position_and_fund_code_variants():
    rows = (
        "HİSSE SENETLERİ\n"
        "AEFES TL ANADOLU -64.900,00 17,746365 02/10/26 80100511 18,040000 -1.170.796,00"
        " -0,26 -0,21 -0,21\n"
        "TRAAEFES91A9\n"
        "DİĞER\n"
        "KVS TL AZİMUT 223.000,00 3,962745 30/09/26 3,973590 886.110,57 100,00 0,62 0,63\n"
        "(CKL) YAPI KREDİ TL YAPI 1.259.181,00 1,588334 03/09/26 1,601334 2.016.369,35"
        " 2,05 2,03 2,03\n"
        "Borsa Y.Fonu Türk\n"
        "GMSTR TL QNB 1.700.000,00 640,174238 10/08/26 80100103 572,000000 972.400.000,00"
        " 19,73 18,67 18,53\n"
    )
    page = IRF_PAGES[0].split("HİSSE SENETLERİ")[0] + rows + "IV-FON TOPLAM DEĞERİ TABLOSU\n"
    result = parse_report([page], IRF_META)
    short, kvs, ckl, gmstr = result.holdings
    assert (short.value, short.weight, short.isin) == (
        Decimal("-1170796.00"),
        Decimal("-0.0021"),
        "TRAAEFES91A9",
    )
    assert [kvs.held_fund_code, ckl.held_fund_code] == ["KVS", "CKL"]
    assert (gmstr.asset_type, gmstr.instrument_code, gmstr.held_fund_code) == (
        AssetType.ETF,
        "GMSTR",
        "FGS",
    )
