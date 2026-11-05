# 0004 — Referans tarih ve birincil rapor seçimi

- **Tarih:** 2026-10-25
- **Durum:** önerildi
- **Karar verenler:** Mehmet Akif Çavuş

## Bağlam
IRF'nin elimizdeki raporu başlıkta "Eylül-2026" yazsa da haftalık bir rapor (28.09–02.10). Alt
fonların bir kısmı aylık (30.09), serbest ve kısa vadeli fonlar haftalık rapor yayımlıyor (AP7,
PIS, PKV, KVS, NLK, IRB); bir ayda 4–5 rapor çıkıyor. Haftalık raporların çoğunun başlığında hafta
yazmıyor.

## Karar
- Referans tarih, kök fonun raporunun bitiş tarihidir: 02.10.2026.
- Her alt fon için referans tarihe en yakın rapor birincil seçilir (`corpus.csv`, `primary=yes`).
- Her look-through yolunun rapor tarihi ve en büyük tarih farkı sonuçta gösterilir (şu an en fazla 4 gün).
- Başlıkta tarih yoksa hafta, KAP linkindeki yükleme zamanından çözülür (`kap_upload_utc`).

## Değerlendirilen seçenekler
- Yalnızca aylık raporlar — eksi: haftalık yayımlayan fonların aylık raporu yok
- Referansa en yakın rapor — artı: her fonda uygulanabilir / eksi: tarihler birebir aynı değil

## Sonuçları
KAP'ta IRF'nin ayrı bir aylık Eylül raporu bulunursa bu not yeniden değerlendirilir.
