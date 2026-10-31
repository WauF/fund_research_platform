# 0002 — Look-through kesme eşiği

- **Tarih:** 2026-10-25
- **Durum:** kabul edildi (eşik değeri önerildi: %0,05)
- **Karar verenler:** Mehmet Akif Çavuş

## Bağlam
IRF'nin Eylül 2026 ağacı elle açıldı (`data/irf_look_through_elle.csv`). Yapı en az 4 seviye
derin, ama ağırlık hızla küçülüyor: 2. seviye FTD'nin %81,98'i, 3. seviye ≈ %0,96, 4. seviye
< %0,1 (PBI ≈ %0,026, TPC ≈ %0,058). 4. seviyedeki fon sepetleri onlarca fon daha tutuyor;
hepsini indirmek emeğe değmiyor.

## Karar
Look-through, kök fondaki yol ağırlığı (path weight) eşiğin altına düşen bir fonu açmaz. O fon
"unresolved (kesme eşiği)" olarak sonuçta görünür kalır, gizlenmez. Önerilen eşik: %0,05.

## Değerlendirilen seçenekler
- Sınırsız derinlik — artı: tam / eksi: rapor sayısı patlıyor, katkı ihmal edilebilir
- Sabit seviye sınırı (ör. 3) — artı: basit / eksi: ağır bir 4. seviye yolunu da keser
- Yol ağırlığı eşiği — artı: emeği katkıyla orantılar / eksi: eşik bir yargı

## Sonuçları
Spec'in "incomplete information must remain visible" şartıyla uyumlu. Paket B'nin look-through
motoru eşiği parametre olarak almalı; coverage hesabında kesilen ağırlık ayrıca raporlanmalı.
