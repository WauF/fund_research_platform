# 0006 — PDF'ten metin çıkarma aracı: pdfplumber

- **Tarih:** 2026-10-25
- **Durum:** önerildi
- **Karar verenler:** Mehmet Akif Çavuş

## Bağlam
Sunumda MarkItDown + pdfplumber veya PyMuPDF yazdık; seçim pilota bırakılmıştı.
`backend/scripts/compare_pdf_text.py`, 6 format ailesinden birer raporda 5 aracı karşılaştırır:
elle seçilmiş değerler metinde var mı ve bir satırın tüm alanları aynı satırda kalıyor mu.

| Araç | Doğru | Süre (6 rapor) | Token (IRF / GTM) |
|---|---|---|---|
| pdfplumber | 13/17 | 2,3 sn | ~4.600 / ~14.600 |
| PyMuPDF (sort) | 13/17 | 0,3 sn | ~10.000 / ~38.700 |
| pdftotext -layout | 13/17 | 0,1 sn | ~10.100 / ~28.300 |
| pdfplumber layout | 13/17 | 2,4 sn | ~19.600 / ~17.700 |
| MarkItDown | 12/17 | 8,7 sn | ~9.900 / ~15.200 |

## Karar
- Birincil: **pdfplumber** `extract_text()`. Doğrulukta fark yok; aynı bilgiyi en az token'la
  veriyor, yani LLM maliyeti yaklaşık yarıya iniyor.
- Yedek: **PyMuPDF**. En hızlısı; sayfa görüntüsü ve kelime koordinatı da verir (review ekranı).
- MarkItDown kullanılmaz: en yavaşı, ağır bağımlılıklar, EIB'de bir satırı bozdu.
- Taranmış raporlar (NJR, NLK) için OCR ayrı bir adım (Tesseract + `tur` dil paketi).

## Sonuçları
Hiçbir araç şunları çözmüyor; çıkarım katmanında ele alınmalı:
- İki satıra bölünmüş ISIN (`TRMDLYWWWW` + `W9`) → `extraction.isin.join_parts`
- PDF içindeki bozuk font eşlemesi (GTM: `Satın` → `Sat;n`) → metin normalleştirmesi
- Çizgisiz tablolar: pdfplumber'ın tablo çıkarımı GTM'de hiç tablo bulamadı → metin tabanlı yaklaşım
