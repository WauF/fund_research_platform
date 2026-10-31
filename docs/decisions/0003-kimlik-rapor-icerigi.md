# 0003 — Fon kimliği rapor içeriğinden belirlenir

- **Tarih:** 2026-10-25
- **Durum:** kabul edildi
- **Karar verenler:** Mehmet Akif Çavuş

## Bağlam
KAP'tan inen dosya adları tutarsız: GPB'nin raporu bazen "GBP" adıyla iniyor. Fon adları da
raporlar arasında farklı yazılıyor (SUA raporunda "QNB Finans Portföy Gümüş BYF", KAP'ta
"QNB Portföy Gümüş Katılım BYF"). BYF'lerde raporda borsa kodu yazıyor (GMSTR), KAP fon kodu
farklı (FGS). Kurucu/yönetici alanları da güvenilmez (EIB "Astra" adlı, kurucu QInvest).

## Karar
Bir raporun ve bir satırın hangi fona ait olduğu şu sırayla belirlenir:
1. ISIN (kontrol hanesi doğrulanmış; OCR'dan geldiyse bilinen ISIN'lerle eşleşmiş)
2. Raporun içindeki KAP fon kodu
3. Ad yalnızca insan incelemesine giden bir aday

Dosya adı hiçbir zaman kimlik kaynağı değildir. Şemada borsa kodu (`instrument_code`) ile KAP fon
kodu (`held_fund_code`) ayrı alanlardır; BYF'ler için borsa kodu → fon kodu eşleme tablosu tutulur.

## Değerlendirilen seçenekler
- Dosya adı — eksi: kanıtlanmış şekilde yanlış (GBP/GPB)
- Fon adı — eksi: raporlar arasında değişiyor
- ISIN + fon kodu — artı: doğrulanabilir

## Sonuçları
Sunumdaki "Identity matching" tasarımıyla aynı. Gerekçe ve örnekler: `docs/notes/veri-bulgulari.md` 2.1.
