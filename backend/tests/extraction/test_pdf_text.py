"""pdf_text helpers that need no PDF file."""

from extraction.pdf_text import is_scanned, repair_encoding


def test_repair_encoding_eca():
    # ECA's PDF maps İ to Ġ and ş to ġ.
    assert repair_encoding("ECA-GLOBAL MD PORT. BĠRĠNCĠ DEGISKEN FON") == (
        "ECA-GLOBAL MD PORT. BİRİNCİ DEGISKEN FON"
    )
    assert repair_encoding("ALIġ") == "ALIş"


def test_is_scanned():
    assert is_scanned(["", "  \n"])  # NJR, NLK
    assert not is_scanned(["", "A-)Fonun Adı"])
