# 0001 — PDF depolama: MinIO yerine SeaweedFS

- **Tarih:** 2026-10-28
- **Durum:** kabul edildi
- **Karar verenler:** Ahmet Emre Kurt

## Bağlam
Ham KAP PDF'leri S3 uyumlu bir nesne deposunda tutuluyor. MinIO resmi Docker imajlarını artık
yayımlamıyor; elimizdeki tek seçenek topluluk derlemesi (`chainguard/minio`, yalnızca `latest`)
idi. Resmi desteği olmayan bir bileşene bitirme projesinin depolama katmanını bağlamak istemedik.

## Karar
SeaweedFS (`chrislusf/seaweedfs:4.48`, Apache-2.0), S3 ağ geçidiyle. `weed mini` master + volume +
filer + S3'ü tek süreçte çalıştırır ve `-bucket=` ile bucket'ı açılışta yaratır; ayrı bir init
konteynerine gerek kalmaz. Backend yalnızca standart S3 API'sini (boto3) kullanır, yani depo
ileride başka bir S3 uyumlu servise taşınabilir.

- S3 erişimi `S3_ACCESS_KEY` / `S3_SECRET_KEY` ile; anonim istekler 403 alır.
- Admin UI (http://localhost:23646) aynı anahtar çiftiyle girilir.
- PDF anahtarı içerik adreslidir: `pdfs/<sha256>.pdf`. Aynı dosya iki kez yazılsa bile depoda tek
  nesne olur; tekrar önlemenin asıl kaynağı `documents.sha256` üzerindeki UNIQUE kısıtıdır.

## Değerlendirilen seçenekler
- MinIO (chainguard) — artı: tanıdık, `mc` aracı / eksi: resmi imaj yok, sürüm sabitlemek için digest
- SeaweedFS — artı: aktif geliştirme, resmi sürümlü imaj, tek süreç / eksi: admin şifresi
  komut satırında (`docker inspect` ile görünür; yalnızca 127.0.0.1'e bağlı geliştirme ortamı için kabul)
- Garage — artı: hafif / eksi: ekipçe tanıdık değil, bucket/anahtar için ek kurulum adımı

## Sonuçları
Eski `miniodata` volume'ü artık kullanılmıyor (`docker volume rm fund-platform_miniodata`).
Çok düğümlü kurulum gerekirse `weed mini` yerine ayrı `master`/`volume`/`filer`/`s3` servisleri.
