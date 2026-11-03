# 0008 — Extraction run kimliği ve hangi run'ın sunulacağı

- **Tarih:** 2026-11-03
- **Durum:** önerildi (Paket A ve B'nin onayı bekleniyor)
- **Karar verenler:** Ahmet Emre Kurt

## Bağlam
Bir PDF'ten birden fazla çıkarım yapılabiliyor: baseline, farklı modeller, prompt düzeltmesinden
sonra yeniden deneme. Her `Holding` ve `ReportSummary` kaydı ait olduğu çalışmanın
`extraction_run_id` değerini taşıyor. Bu yüzden iki soruya cevap gerekiyor:
1. Run id'yi kim, ne zaman üretiyor?
2. API ve look-through, bir dokümanın hangi run'ını kullanıyor?

İkinci soru look-through için kritik. Motor her fon için tam olarak bir rapor bekliyor, aynı
fonun satırları iki kez gelirse ağırlıklar sessizce toplanıyor (#14 incelemesi: slayt 8'de toplam
1,0 yerine 1,4).

## Karar
- **Run id bir UUID'dir ve çıkarım kodu tarafından üretilir** (`uuid4()`). Çıkarım bitince run
  ve tüm kayıtları `storage.extractions.save_extraction_run()` ile tek transaction'da yazılır.
  Kayıtlardan biri başka bir run'a aitse ya da `row_no` tekrarlıyorsa hiçbir şey yazılmaz.
- **Run durumu:** bir sorun (issue) varsa ya da herhangi bir kayıt `needs_review` ise run da
  `needs_review` olur, aksi halde `ok`.
- **Varsayılan run, dokümanın en son run'ıdır.** Run'ı inceleme gerektirse bile varsayılan budur:
  `GET /documents/{id}/holdings` cevabındaki `run.status` alanı ve kayıtların `status` alanı bunu
  gösterir. İnceleme ekranı en son durumu görmeli.
- **Veriden hesap yapan her şey (look-through, snapshot) `only_ok=True` kullanır:** dokümanın
  doğrulamadan geçmiş en son run'ı. Hiç `ok` run yoksa o doküman hesaba girmez ve unresolved
  sayılır.
- Belirli bir run her zaman `run_id` ile istenebilir.

## Değerlendirilen seçenekler
- **Run id: integer (DB'de üretilir)** — artı: kısa / eksi: id için önce DB'ye boş bir satır
  yazmak gerekir; evaluation sonuçları ve `tests/recorded/` dosyaları DB dışında ürettiği için
  id'ler makineler arasında çakışır.
- **Run id: UUID (kodda üretilir)** — artı: DB'ye gitmeden üretilir, hiçbir yerde çakışmaz /
  eksi: indeks biraz büyük (bu ölçekte önemsiz). **Seçildi.**
- **Varsayılan run: en son `ok` run** — artı: hep temiz veri / eksi: inceleme gereken yeni bir run
  görünmez olur, kullanıcı eski sonucu güncel sanır.
- **Varsayılan run: elle seçilmiş "aktif" run** — artı: tam kontrol / eksi: ek bir durum ve ekran
  gerektirir. Düzeltme (corrections) akışı netleşince yeniden değerlendirilir.

## Sonuçları
- Paket A: çıkarımı başlatmadan önce `run_id = uuid4()` üretir, doğrulamadan sonra
  `save_extraction_run()` çağırır.
- Paket B: look-through'a giden veri her fon için tek run'dan gelir. Motorun aynı fondan birden
  fazla dönem ya da run gördüğünde hata vermesi önerilir.
- "Aktif run" ve düzeltilmiş kayıt (effective holding) mantığı bu notun kapsamı dışında; corrections
  tablosuyla birlikte ayrı bir notta karara bağlanacak.
