"""KAP fund codes that differ from how a report prints them (decision 0003).

Shared by the extractors and validation, so validation does not depend on one extractor.
"""

from __future__ import annotations

# Exchange ticker of an ETF -> its KAP fund code. Source: KAP search.
ETF_TICKERS = {"GMSTR": "FGS"}
