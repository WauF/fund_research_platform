"""Rule-based extraction for the standard KAP report template ("A-)Fonun Adı").

This is the baseline the LLM extractor has to beat (success criterion 1). It covers the template
most managers use: 24 of the 36 primary reports in the September 2026 corpus. Other families
(Garanti, Astra/Ünlü, Ziraat, Yapı Kredi, scanned) are out of scope here and raise
UnsupportedTemplate.

How a row is read (section III, Fon Portföy Değeri Tablosu): a value line ends with
"<value> <group %> <FPD %> [<FTD %>]"; the security's long name, issuer and ISIN continue on the
next lines. FPD weights are always printed, FTD weights are not (e.g. VİOP collateral), so rows use
WeightBasis.PORTFOLIO.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from pydantic import ValidationError

from extraction import isin as isin_mod
from extraction.numbers import parse_number
from extraction.pdf_text import repair_encoding
from schemas.holding import (
    FUND_LIKE,
    AssetType,
    Holding,
    ReportKind,
    ReportSummary,
    WeightBasis,
)


class UnsupportedTemplate(ValueError):
    """The report does not use the standard template."""


# Group and sub-group headers of section III -> asset type. A sub-group overrides its group.
GROUPS: dict[str, AssetType] = {
    "HİSSE SENETLERİ": AssetType.EQUITY,
    "Hisse Türk": AssetType.EQUITY,
    "Hisse Yabancı": AssetType.EQUITY,
    "BORÇLANMA SENETLERİ": AssetType.BOND,
    "Devlet Tahvili": AssetType.BOND,
    "Bono": AssetType.BOND,
    "Özel Sektör": AssetType.BOND,
    "Varlığa Dayalı Menkul Kıymet": AssetType.BOND,
    "KİRA SERTİFİKALARI": AssetType.BOND,
    "Kamu Kesimi Kira Sertifikaları": AssetType.BOND,
    "Özel Sektör Kira Sertifikaları": AssetType.BOND,
    "T.REPO": AssetType.REPO,
    "REPO": AssetType.REPO,
    "TPP": AssetType.REPO,
    "MEVDUAT": AssetType.DEPOSIT,
    "KATILIM HESABI": AssetType.DEPOSIT,
    "VIOP Nakit Teminatı": AssetType.CASH,
    "Yurtdışı Futures USD Nakit Teminatı": AssetType.CASH,
    "Döviz": AssetType.CASH,
    "TÜREV": AssetType.DERIVATIVE,
    "Futures": AssetType.DERIVATIVE,
    "Option": AssetType.DERIVATIVE,
    "Call Alım": AssetType.DERIVATIVE,
    "Call Satım": AssetType.DERIVATIVE,
    "Put Alım": AssetType.DERIVATIVE,
    "Put Satım": AssetType.DERIVATIVE,
    "DİĞER": AssetType.FUND,
    "Y.Fonu Türk": AssetType.FUND,
    "Y.Fonu Yabancı": AssetType.FUND,
    "Borsa Y.Fonu Türk": AssetType.ETF,
    "Borsa Y.Fonu Yabancı": AssetType.ETF,
    "D.Maden": AssetType.OTHER,  # precious metal (FGS: GUMUS999)
    "AÇIĞA SATIŞ": AssetType.OTHER,
    "ÖDÜNÇ ALMA": AssetType.OTHER,
}

MONTHS = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}  # fmt: skip
# Exchange tickers of ETFs whose KAP fund code differs (decision 0003). Source: KAP search.
ETF_TICKERS = {"GMSTR": "FGS"}
CURRENCIES = {"TL": "TRY", "TRY": "TRY", "USD": "USD", "EUR": "EUR", "GBP": "GBP", "CHF": "CHF"}

_NUM = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d+$")
_COLUMN_HEADER = re.compile(r"VADEYE|DÖVİZ İHRAÇCI|MENKUL KIYMET KALAN|CİNSİ KURUM|GÜN ORANI")
_FUND_PREFIX = re.compile(r"^([A-Z0-9]{2,4})\s*-\s*")
_FUND_CODE_TOKEN = re.compile(r"^\(?([A-Z0-9]{3})\)?$")  # KAP fund codes have 3 characters
_ISIN_TOKEN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_ISIN_HEAD = re.compile(r"^(?:TR|US|IE|LU|DE|GB|FR)[A-Z0-9]{6,10}$")
_DATE_RANGE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{2})/(\d{2})/(\d{4})")
_MONTH_HEADER = re.compile(r"^(\w+)-(\d{4})$")
_SUMMARY_LINE = re.compile(r"^([A-G])-\)\s*(.+?)\s+(-?[\d.]+,\d+)\s+(-?[\d.]+,\d+)\s*%")
_TOTAL_LINE = re.compile(r"^FON TOPLAM DEĞERİ\s+(-?[\d.]+,\d+)")
_PORTFOLIO_TOTAL = re.compile(r"^FON PORTFÖY DEĞERİ\s+(-?[\d.]+,\d+)")
_WEIGHT_SLACK = Decimal("0.011")  # FPD % is printed with 2 decimals


@dataclass(frozen=True)
class ReportMeta:
    fund_code: str
    period_start: date
    period_end: date
    report_kind: ReportKind


@dataclass
class BaselineResult:
    meta: ReportMeta
    holdings: list[Holding]
    summary: ReportSummary | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Row:
    page: int
    line: str
    asset_type: AssetType
    nums: list[Decimal]
    extra: list[str] = field(default_factory=list)


def _n(text: str) -> Decimal:
    value = parse_number(text, "tr")
    assert value is not None
    return value


def _trailing_numbers(line: str) -> list[Decimal]:
    out: list[Decimal] = []
    for token in reversed(line.split()):
        if not _NUM.match(token):
            break
        out.append(_n(token))
    return out[::-1]


def check_template(pages: list[str]) -> list[str]:
    """Raise UnsupportedTemplate unless the report uses the standard template.

    Returns the lines of the page that starts the report (title, period, "A-)Fonun Adı").
    """
    if not any(p.strip() for p in pages):
        raise UnsupportedTemplate("no text layer: scanned PDF, needs OCR")
    # Usually page 1, but pages can be out of order (TPF starts with section VIII).
    for page in pages:
        lines = repair_encoding(page).splitlines()
        if any("A-)Fonun Ad" in line for line in lines[:6]):
            return lines
    raise UnsupportedTemplate("no 'A-)Fonun Adı' line: not the standard template")


def detect_meta(pages: list[str]) -> ReportMeta:
    """Fund code, period and report kind from the report header.

    Weekly reports often print only the month ("Eylül-2026"); then the week cannot be known from
    the text and UnsupportedTemplate is raised: pass the period from data/corpus.csv instead.
    """
    first = check_template(pages)
    code = _FUND_PREFIX.match(first[0].strip())
    if not code:
        raise UnsupportedTemplate(f"no fund code in title {first[0]!r}")
    text = "\n".join(pages)
    weekly = "HAFTA İÇİNDE" in text or "Haftalık Pay Fiyatı" in text
    kind = ReportKind.WEEKLY if weekly else ReportKind.MONTHLY
    header = first[1].strip()
    if m := _DATE_RANGE.search(header):
        d1, m1, y1, d2, m2, y2 = map(int, m.groups())
        return ReportMeta(code.group(1), date(y1, m1, d1), date(y2, m2, d2), kind)
    if (m := _MONTH_HEADER.match(header)) and kind is ReportKind.MONTHLY:
        month, year = MONTHS[m.group(1).casefold()], int(m.group(2))
        start = date(year, month, 1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return ReportMeta(code.group(1), start, end, kind)
    raise UnsupportedTemplate(f"weekly report without dates in header {header!r}: pass the period")


def _summary(pages: list[str], meta: ReportMeta, run_id: str) -> ReportSummary | None:
    parts: dict[str, Decimal] = {}
    for page_no, page in enumerate(pages, 1):
        for raw in page.splitlines():
            line = repair_encoding(raw).strip()
            if m := _SUMMARY_LINE.match(line):
                parts.setdefault(m.group(1), _n(m.group(3)))
            elif m := _TOTAL_LINE.match(line):
                liabilities = -sum((abs(parts.get(k, Decimal(0))) for k in "EFG"), Decimal(0))
                return ReportSummary(
                    fund_code=meta.fund_code,
                    period_start=meta.period_start,
                    period_end=meta.period_end,
                    report_kind=meta.report_kind,
                    page=page_no,
                    quote=raw.strip(),  # verbatim: validation looks for it in the page text
                    extraction_run_id=run_id,
                    portfolio_value=parts.get("A", Decimal(0)),
                    cash_equivalents=parts.get("B", Decimal(0)),
                    receivables=parts.get("C", Decimal(0)),
                    other_assets=parts.get("D", Decimal(0)),
                    liabilities=liabilities,
                    total_value=_n(m.group(1)),
                )
    return None


def _rows(pages: list[str], title: str) -> tuple[list[_Row], Decimal | None]:
    """Value rows of section III, each with its continuation lines, and the printed FPD total."""
    rows: list[_Row] = []
    current: _Row | None = None
    group: AssetType | None = None
    portfolio_total: Decimal | None = None
    inside = False
    for page_no, page in enumerate(pages, 1):
        for raw in page.splitlines():
            line = repair_encoding(raw).strip()
            if line.startswith("III-FON PORTFÖY DEĞERİ"):
                inside = True
                continue
            if not inside:
                continue
            if line.startswith("IV-FON TOPLAM"):
                return rows, portfolio_total
            if m := _PORTFOLIO_TOTAL.match(line):
                portfolio_total = _n(m.group(1))
                current = None
                continue
            if (
                not line
                or line == title
                or _COLUMN_HEADER.search(line)
                or _DATE_RANGE.fullmatch(line)
                or _MONTH_HEADER.match(line)
            ):
                continue
            if line in GROUPS:
                group, current = GROUPS[line], None
                continue
            if line.startswith("GRUP TOPLAMI"):
                current = None
                continue
            nums = _trailing_numbers(line)
            if group is not None and len(nums) >= 3:
                current = _Row(page_no, raw.strip(), group, nums)
                rows.append(current)
            elif current is not None:
                current.extra.append(line)
    return rows, portfolio_total


def _read_numbers(row: _Row, portfolio_value: Decimal | None) -> tuple[Decimal, Decimal]:
    """(value, FPD weight as a fraction). Chooses the reading in which value / FPD matches."""
    n = row.nums
    readings = []
    if len(n) >= 4:
        readings.append((n[-4], n[-3], n[-2]))  # value, group %, FPD %, FTD %
    readings.append((n[-3], n[-2], n[-1]))  # value, group %, FPD %   (no FTD column)
    readings = [r for r in readings if r[1] <= 100 and r[2] <= 100]
    if not readings:
        raise ValueError(f"no plausible reading of {row.line!r}")
    if portfolio_value:
        for value, _group, fpd in readings:
            if abs(value / portfolio_value * 100 - fpd) <= _WEIGHT_SLACK:
                return value, fpd / 100
    value, _group, fpd = readings[0]  # derivatives: notional value, 0 weight
    return value, fpd / 100


def _find_isin(row: _Row) -> str | None:
    tokens = [t for line in [row.line, *row.extra] for t in line.split()]
    for t in tokens:
        if _ISIN_TOKEN.match(t) and isin_mod.is_valid(t):
            return t
    # Split over two lines: 'TRMDLYWWWW' at the end of one line, 'W9' at the end of the next.
    lines = [row.line, *row.extra]
    for i, line in enumerate(lines[:-1]):
        head = line.split()[-1] if line.split() else ""
        tail = lines[i + 1].split()[-1] if lines[i + 1].split() else ""
        if _ISIN_HEAD.match(head) and (joined := isin_mod.join_parts(head, tail)):
            return joined
    return None


def _held_fund_code(prefix: str, asset_type: AssetType) -> str | None:
    """KAP fund code of a fund or ETF row: 'BGP-AK PORTFÖY', 'IOO - İŞ', 'KVS', '(CKL) YAPI'."""
    if asset_type not in FUND_LIKE or not prefix:
        return None
    if m := _FUND_PREFIX.match(prefix):
        return ETF_TICKERS.get(m.group(1), m.group(1))
    first = prefix.split()[0]
    if first in ETF_TICKERS:
        return ETF_TICKERS[first]
    if asset_type is AssetType.FUND and (m := _FUND_CODE_TOKEN.match(first)):
        return m.group(1)
    return None  # an ETF ticker without a known KAP code: validation flags it


def parse_report(
    pages: list[str], meta: ReportMeta | None = None, run_id: str = "baseline"
) -> BaselineResult:
    """Extract holdings and the summary from a standard-template report.

    meta: fund code and period; detected from the header if omitted (see detect_meta).
    """
    title = check_template(pages)[0].strip()
    meta = meta or detect_meta(pages)
    warnings: list[str] = []
    summary = _summary(pages, meta, run_id)
    rows, printed_total = _rows(pages, title)
    portfolio_value = summary.portfolio_value if summary else printed_total

    holdings: list[Holding] = []
    for row_no, row in enumerate(rows, 1):
        prefix = row.line
        tokens = row.line.split()
        cur_at = next((i for i, t in enumerate(tokens) if t in CURRENCIES), None)
        if cur_at is not None:
            prefix = " ".join(tokens[:cur_at])
        currency = CURRENCIES[tokens[cur_at]] if cur_at is not None else "TRY"
        isin = _find_isin(row)
        held_fund_code = _held_fund_code(prefix, row.asset_type)
        try:
            value, weight = _read_numbers(row, portfolio_value)
            holdings.append(
                Holding(
                    fund_code=meta.fund_code,
                    period_start=meta.period_start,
                    period_end=meta.period_end,
                    report_kind=meta.report_kind,
                    page=row.page,
                    quote=row.line,
                    extraction_run_id=run_id,
                    row_no=row_no,
                    name=prefix or row.line,
                    asset_type=row.asset_type,
                    isin=isin,
                    instrument_code=re.split(r"[\s-]", prefix, maxsplit=1)[0] or None,
                    held_fund_code=held_fund_code,
                    value=value,
                    currency=currency,
                    weight=weight,
                    weight_basis=WeightBasis.PORTFOLIO,
                )
            )
        except (ValueError, ValidationError) as exc:
            warnings.append(f"row {row_no} on page {row.page} skipped: {exc}")
    if summary is None:
        warnings.append("section IV (fund total value) not found")
    return BaselineResult(meta, holdings, summary, warnings)
