# 0005 — KAP raporları elle indirilir

- **Tarih:** 2026-10-25
- **Durum:** kabul edildi
- **Karar verenler:** Mehmet Akif Çavuş

## Bağlam
KAP'ın fon bilgi sayfaları robots.txt ile otomatik taramayı yasaklıyor. Sunumda "curated list,
polite downloads" sözü verdik.

## Karar
Raporlar KAP'ta elle bulunur ve indirilir. Her dosyanın doğrudan indirme linki
(`kap.org.tr/tr/api/file/download/<id>`) ve SHA-256'sı `data/corpus.csv` içinde tutulur.

## Sonuçları
- Link kimliğinin 17–28. hex karakterleri dosyanın KAP'a yüklenme zamanıdır (milisaniye). Bu,
  dosyayı indirmeden haftalık raporun dönemini belirlemeye yarar (`corpus.csv`, `kap_upload_utc`).
- KAP aynı raporu farklı bir kimlikle yeniden yayımlayabiliyor (Pardus fonları, 22.09); link veya
  hash tek başına tekrarı yakalamaz.
- KAP/TEFAS kullanım koşulları notu hâlâ açık (Paket A).
