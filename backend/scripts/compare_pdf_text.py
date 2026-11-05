"""Compare PDF-to-text tools on one report per format family.

Run from backend/:  uv run python scripts/compare_pdf_text.py
The PDFs must be under data/raw/ (download them from the links in data/corpus.csv).
Check: are hand-picked "needles" from each report found in the text? A tuple needle (e.g. a fund
code and its value) must be found on ONE line, because the LLM needs whole rows to read a row
correctly. Results and the decision: docs/decisions/0006-pdf-metin-araci.md.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pdfplumber
import pymupdf as fitz

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"

CASES = {
    "standart (IRF)": (
        "IRF/IRF_2026-09.pdf",
        [
            ("BGP", "40.073.740,62", "12,93", "12,02", "10,59"),  # fon satırının tamamı
            ("IRB-İSTANBUL", "37.112.177,64"),
            "TRYAKPO00625",
            "378.395.976,36",
            "ÜÇÜNCÜ PARA",
            "TRMDLYWWWWW9",
        ],
    ),  # is the ISIN split over two lines joined?
    "garanti (GTM)": (
        "GTM/GTM_2026-09.pdf",
        [("AEFES.E", "TRAAEFES91A9", "633,845.68", "0.07%", "0.06%"), "975,489,543.87", "Satın"],
    ),  # broken font mapping in the PDF: ı -> ;
    "astra (EIB)": (
        "EIB/EIB_2026-09.pdf",
        [("EID", "EID Astra Portföy", "2.727.561,00", "4.866.538,88", "%1,63"), "297.573.399,20"],
    ),
    "ziraat (ZPO)": (
        "ZPO/ZPO_2026-09.pdf",
        [("TRDDVRLA2627", "Ege Yapı", "10.689.277,55", "0,385880"), "2.767.848.836,47"],
    ),
    "yapı kredi (PPI)": (
        "PPI/PPI_2026-09.pdf",
        [("TRT060928T11", "132,000,000.00", "134,956,800.00", "2.76"), "4,891,376,352.39"],
    ),
    "taranmış (NJR)": ("NJR/NJR_2026-09.pdf", ["TOPLAM", "1.262.594.968,85"]),
}


def pdftotext_layout(p: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True
    ).stdout


def plumber_plain(p: Path) -> str:
    with pdfplumber.open(p) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def plumber_layout(p: Path) -> str:
    with pdfplumber.open(p) as pdf:
        return "\n".join(page.extract_text(layout=True) or "" for page in pdf.pages)


def pymupdf_sorted(p: Path) -> str:
    with fitz.open(p) as doc:
        return "\n".join(page.get_text(sort=True) for page in doc)


def markitdown_cli(p: Path) -> str:
    return subprocess.run(["markitdown", str(p)], capture_output=True, text=True).stdout


TOOLS = {
    "pdftotext -layout": pdftotext_layout,
    "pdfplumber": plumber_plain,
    "pdfplumber layout": plumber_layout,
    "PyMuPDF sort": pymupdf_sorted,
}
if shutil.which("markitdown"):
    TOOLS["MarkItDown"] = markitdown_cli


def hit(text: str, needle) -> bool:
    if isinstance(needle, str):
        return needle in text
    return any(all(part in line for part in needle) for line in text.splitlines())


def main() -> None:
    totals = {t: [0, 0, 0.0] for t in TOOLS}
    for family, (rel, needles) in CASES.items():
        print(f"\n## {family}")
        for tool, fn in TOOLS.items():
            t0 = time.perf_counter()
            text = fn(RAW / rel)
            dt = time.perf_counter() - t0
            ok = [hit(text, n) for n in needles]
            totals[tool][0] += sum(ok)
            totals[tool][1] += len(ok)
            totals[tool][2] += dt
            miss = [
                n if isinstance(n, str) else "+".join(n)
                for n, h in zip(needles, ok, strict=True)
                if not h
            ]
            tokens = len(text) // 4
            missing = ", ".join(miss) or "-"
            print(
                f"  {tool:18} {sum(ok)}/{len(ok)}  {dt:5.2f}s ~{tokens:6d} tok  missing: {missing}"
            )
    print("\n## total")
    for tool, (h, n, dt) in totals.items():
        print(f"  {tool:18} {h}/{n}  {dt:5.2f}s")


if __name__ == "__main__":
    main()
