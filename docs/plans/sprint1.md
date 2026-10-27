# CSE 496 Fon Maruziyet Platformu - 1. Hafta Görev Planı

**Tarih:** 25 Ekim – 1 Kasım 2026
**Ekip:** Mehmet Akif Çavuş, Ahmet Emre Kurt, Yusuf Eren Nalbant
**Danışman:** Fatih Özhamaratlı

**Güncel Paket Dağılımı:**
* **Paket A:** Mehmet Akif Çavuş
* **Paket B:** Yusuf Eren Nalbant
* **Paket C:** Ahmet Emre Kurt

---

## 1. Hafta Sonu Hedefi (1 Kasım Pazar)

1 Kasım akşamı uçtan uca bir iskelet çalışıyor olmalı: gerçek bir KAP PDF'i sisteme girer, `Holding` kayıtlarına dönüşür, veritabanına yazılır; look-through motoru elle hazırlanmış test verilerinde doğru sonuç verir. Aşağıdaki beş madde Pazar demosunda tek tek kontrol edilir:

- [ ] `docker compose up` tek komutla PostgreSQL, MinIO ve FastAPI'yi ayağa kaldırıyor *(Ahmet Emre)*
- [ ] `Holding` + `ReportSummary` şeması `main`'e 3 onayla merge edilmiş *(herkes, sorumlu Akif)*
- [ ] 1 gerçek KAP PDF'i yükleniyor, MinIO'da tek kez saklanıyor, LLM ile geçerli `Holding` JSON'una çevriliyor ve `holdings` tablosuna yazılıyor *(Akif + Ahmet Emre)*
- [ ] Look-through 4 test verisinde çalışıyor; recursive yöntem ile matris yöntemi $10^{-9}$ içinde aynı sonucu veriyor, döngü yakalanıyor *(Yusuf Eren)*
- [ ] CI her PR'da yeşil; her kişinin en az 2 merge edilmiş PR'ı ve en az 1 incelemesi var *(herkes)*

*Not: Kişi başı yük bu hafta yaklaşık 15 saat. 29 Ekim (Cumhuriyet Bayramı) tatil olduğu için en yoğun iş günü olarak planlandı.*

---

## 2. Roller ve Kurallar

Herkes kendi klasöründe çalışır; ortak dosyaya (şema) dokunmak 3 onay ister.

| Kişi | Paket | Klasör | Bu Haftaki Çıktı | PR'larını İnceleyen |
| :--- | :--- | :--- | :--- | :--- |
| **Mehmet Akif Çavuş** | A - Veri ve çıkarım | `backend/extraction/`, `backend/schemas/` | Gerçek PDF $\rightarrow$ geçerli `Holding` JSON | Yusuf Eren |
| **Yusuf Eren Nalbant** | B - Exposure ve risk | `backend/exposure/`, `tests/fixtures/` | Look-through + matris kontrolü + döngü | Ahmet Emre |
| **Ahmet Emre Kurt** | C - Platform ve arayüz | `backend/app/`, `backend/storage/`, `.github/`, `docker-compose.yml` | Docker, CI, DB şeması, PDF yükleme API'si | Akif |

**En Kritik Bağımlılık:** `Holding` şeması. Üç paket de buna bağlı. Taslak Pazartesi akşamı PR olarak açılır, Salı akşamına kadar üç onayla merge edilir. O zamana kadar B ve C kendi taraflarında şemayı taslaktan kopyalayarak çalışır.

### Çalışma Kuralları (İlk Günden İtibaren)
* Bir görev dört koşulla biter: kod yazıldı, testi var, bir arkadaş PR'ı onayladı, CI yeşil.
* `main`'e doğrudan push yok. Dallar `feat/...`, `fix/...`; commit mesajları `feat:`, `fix:`, `test:` önekli.
* CI gerçek LLM API'sini asla çağırmaz; testler kayıtlı LLM çıktılarıyla çalışır.
* PDF'ler ve `.env` git'e girmez. Repoda yalnızca `data/corpus.csv` (link + SHA-256) ve `.env.example` durur.
* PR'lar küçük tutulur (ideal: 300 satırın altı). İnceleme 24 saat içinde yapılır.
* Önemli her karar `docs/decisions/` altına kısa bir not olarak yazılır.

---

## 3. Bugün (25 Ekim Pazar): Kararlar ve Kurulum

Bugünkü toplantı bitmeden aşağıdaki dört karar verilip `docs/decisions/` altına yazılır; bunlar olmadan Pazartesi kimse başlayamaz.

### Kararlar (Toplantıda, Hep Birlikte)
- [ ] **Fon evreni kesinleşti:** IRF, TJI, TEJ + 4. fon (GTM mi HIH mi?). Bu hafta yalnızca IRF ve alt fonlarının Eylül 2026 raporu kullanılır.
- [ ] **LLM erişimi:** API mi (hangi model, anahtar kimde, bu haftalık bütçe sınırı) yoksa danışmanın GPU'sunda yerel model mi? Bu hafta için hızlı olanı seçin; nihai karar Kasım pilotunda.
- [ ] **Holding alanları üzerinde sözlü anlaşma** (aşağıdaki liste). Akif bunu Pazartesi PR'a çevirir.
- [ ] **Haftalık toplantılar:** Çarşamba 15 dk durum, Pazar 1 saat demo + retro. İletişim kanalı (WhatsApp/Discord) ve GitHub Projects panosu.

### Önerilen Şema Alanları
* **Holding:** `fund_code`, `report_date`, `row_no`, `isin`, `name`, `asset_type` (`equity` / `bond` / `fund` / `etf` / `cash` / `other`), `held_fund_code` (alt fonsa aday fon kodu), `value_tl`, `currency`, `weight`, `weight_basis` (`portfolio` / `total`), `page`, `quote`, `extraction_run_id`, `status` (`ok` / `needs_review`).
* **ReportSummary:** `fund_code`, `report_date`, `portfolio_value_tl`, `receivables_tl`, `liabilities_tl`, `total_value_tl`, `page`, `quote` — toplam toleransı kontrolü bunlara dayanır.

### Herkesin Bugün Akşama Kadar Yapacağı Kurulum (Yaklaşık 2 Saat)
* **Akif:** Python 3.12 + `uv`, Docker, `pre-commit`; GitHub hesabı repoya eklendi.
* **Ahmet Emre:** GitHub'da repo + Projects panosu açıldı, iki arkadaş davet edildi; Python 3.12 + `uv`, Docker (Windows'ta WSL2).
* **Yusuf Eren:** Python 3.12 + `uv`, Docker, `pre-commit`; GitHub hesabı repoya eklendi.

---

## 4. Gün Gün Görevler

Her günün sonunda hücredeki iş bir PR olarak açılmış olmalı; bir gün kayarsa ertesi günün ilk işi odur. Saatler kişi başı tahmindir.

| Gün | Akif (Paket A) | Yusuf Eren (Paket B) | Ahmet Emre (Paket C) |
| :--- | :--- | :--- | :--- |
| **Pzt 26 Eki** | `Holding` + `ReportSummary` Pydantic şeması + birim testleri $\rightarrow$ PR (3 sa). KAP'ta IRF Eylül raporunu ve alt fonlarını bul (1 sa) | Slayt 8 örneğini `Holding` formatında JSON test verisi olarak yaz, beklenen sonucu elle hesapla (2 sa) | Repo iskeleti: klasörler, `pyproject.toml`, `ruff`, `pre-commit`, `CODEOWNERS`, PR şablonu, dal koruması, `README` (3 sa) |
| **Sal 27 Eki** | Şema PR'ı merge. `data/corpus.csv` ilk satırlar: IRF + alt fonlar, Eylül, KAP linki (2 sa) | Şema PR'ını incele. NetworkX graf modeli: `Holding` listesinden graf kur + test (3 sa) | Şema PR'ını incele. GitHub Actions CI (`ruff` + `pytest`). Docker Compose: PostgreSQL + MinIO + FastAPI, `.env.example` (3 sa) |
| **Çar 28 Eki** | Türkçe sayı ayrıştırıcı (`1.234,56`, `%2,98`, eksi) + ISIN kontrol hanesi doğrulayıcı, testleriyle (3 sa) | Recursive look-through + memoization; slayt 8 testi geçiyor (3 sa) | SQLAlchemy modelleri + Alembic: `documents`, `extraction_runs`, `holdings`, `report_summaries`, `corrections`, `snapshots` (3 sa) |
| **Per 29 Eki (Tatil)** | PDF $\rightarrow$ metin karşılaştırması: MarkItDown, pdfplumber, PyMuPDF; 2 farklı format; araç seçimi notu (4 sa) | Matris kontrolü $e = d + a(I - F)^{-1}L$, iki yöntem $10^{-9}$ içinde eşit testi. DFS ile döngü tespiti (4 sa) | `POST /documents`: PDF yükle $\rightarrow$ SHA-256 $\rightarrow$ MinIO; aynı PDF ikinci kez gelirse tek kayıt + testi (4 sa) |
| **Cum 30 Eki** | İlk LLM çıkarımı: IRF Eylül PDF'i $\rightarrow$ structured output $\rightarrow$ `Holding` JSON. Ham çıktıyı `tests/recorded/` altına kaydet (4 sa) | HHI + overlap. Test verileri: döngülü, unresolved (raporsuz fon), $\ge 3$ seviye iç içe (3 sa) | `GET /documents`, `GET /documents/{id}/holdings`; `save_extraction_run()` depo fonksiyonu (Akif bunu çağıracak) (3 sa) |
| **Cmt 31 Eki** | Entegrasyon: çıkarım çıktısını `save_extraction_run()` ile DB'ye yaz. KAP/TEFAS kullanım koşulları notu (3 sa) | Exposure JSON formatı taslağı (`docs/decisions/` + örnek çıktı); Ahmet Emre ile birlikte gözden geçir (2 sa) | Entegrasyon: yükle $\rightarrow$ sakla $\rightarrow$ çıkarımı elle tetikleyen komut $\rightarrow$ `holdings`'te kayıt; `docker compose up` temiz makinede denenir (3 sa) |
| **Paz 1 Kas** | Demo + retro (1 sa); Sprint 2 planlaması (1 sa) | Demo + retro; Sprint 2 planlaması | Demo + retro; Sprint 2 planlaması |

---

## 5. Kişi Bazlı Kontrol Listeleri

Her madde bir GitHub issue'sudur; parantez içindeki koşul sağlanınca işaretlenir.

### Mehmet Akif Çavuş – Paket A (Yaklaşık 19 Saat)
- [ ] `Holding` + `ReportSummary` şeması *(3 onayla merge)*
- [ ] IRF ve alt fonlarının Eylül raporları bulundu, `data/corpus.csv` dolduruldu *(fon kodu, dönem, KAP linki, SHA-256)*
- [ ] Türkçe sayı ayrıştırıcı *(birim testleri geçiyor)*
- [ ] ISIN kontrol hanesi doğrulayıcı *(geçerli ve bozuk ISIN testleri geçiyor)*
- [ ] PDF $\rightarrow$ metin araç karşılaştırması *(`docs/decisions/` altında not + seçilen araç)*
- [ ] İlk LLM çıkarımı *(1 gerçek PDF'ten şemaya uygun JSON; ham çıktı kayıtlı)*
- [ ] Çıkarım sonucu DB'ye yazılıyor *(`holdings` tablosunda kayıtlar görünüyor)*
- [ ] KAP/TEFAS kullanım koşulları notu *(1 paragraf)*
- [ ] Yusuf Eren'in en az 1 PR'ı incelendi

### Yusuf Eren Nalbant – Paket B (Yaklaşık 17 Saat)
- [ ] Slayt 8 test verisi + elle hesaplanmış beklenen sonuç *(ASELS %50, TUPRS %20,4, Devlet tahvili %16,8, Nakit %10, Unresolved %2,8)*
- [ ] Graf modeli *(`Holding` listesinden NetworkX grafı kuruluyor)*
- [ ] Recursive look-through *(slayt 8 testi geçiyor)*
- [ ] Matris kontrolü *(iki yöntem $10^{-9}$ içinde eşit)*
- [ ] Döngü tespiti *(döngülü test verisi yakalanıyor, sessizce yok sayılmıyor)*
- [ ] HHI ve overlap *(birim testleri geçiyor)*
- [ ] 4 test verisi `tests/fixtures/` altında: slayt 8, döngülü, unresolved, $\ge 3$ seviye
- [ ] Exposure JSON formatı taslağı *(Ahmet Emre ile gözden geçirildi)*
- [ ] Ahmet Emre'nin en az 1 PR'ı incelendi

### Ahmet Emre Kurt – Paket C (Yaklaşık 19 Saat)
- [ ] Repo iskeleti *(`main`'e doğrudan push yapılamıyor, `CODEOWNERS` çalışıyor)*
- [ ] GitHub Actions CI *(her PR'da `ruff` + `pytest` çalışıyor)*
- [ ] Docker Compose *(`docker compose up` ile PostgreSQL + MinIO + FastAPI ayakta)*
- [ ] Veritabanı şeması v1 + Alembic *(migration'lar temiz DB'de çalışıyor)*
- [ ] PDF yükleme + SHA-256 ile tekrar önleme *(aynı PDF iki kez yüklenince tek kayıt)*
- [ ] Listeleme uç noktaları *(OpenAPI dokümanında görünüyor)*
- [ ] `save_extraction_run()` depo fonksiyonu *(Akif'in çıktısı bununla yazılıyor)*
- [ ] Uçtan uca entegrasyon komutu *(yükle $\rightarrow$ çıkar $\rightarrow$ DB)*
- [ ] Akif'in en az 1 PR'ı incelendi

---

## 6. Teslim Noktaları, Demo ve Gecikme Planı

Paketler üç noktada birbirine dokunur; bu noktalar kaçarsa Pazar demosu parçalar halinde kalır.

| Ne Zaman | Kimden $\rightarrow$ Kime | Teslim Edilen |
| :--- | :--- | :--- |
| **Sal 27 Eki** | Akif $\rightarrow$ Herkes | Merge edilmiş `Holding` + `ReportSummary` şeması |
| **Cum 30 Eki** | Ahmet Emre $\rightarrow$ Akif | `save_extraction_run()` fonksiyonu ve çalışan DB |
| **Cmt 31 Eki** | Yusuf Eren $\rightarrow$ Ahmet Emre | Exposure JSON formatı *(Sprint 2'de API ve arayüz buna göre yazılır)* |

### Pazar Demo Akışı (1 Saat)
1. **Ahmet Emre** temiz bir klasörde `docker compose up` çalıştırır, IRF PDF'ini iki kez yükler; tek kayıt oluştuğunu gösterir.
2. **Akif** çıkarımı tetikler; `holdings` tablosundaki kayıtları ve sayfa/alıntı alanlarını gösterir.
3. **Yusuf Eren** 4 test verisinde look-through sonuçlarını, matris kontrolünü ve yakalanan döngüyü gösterir.
4. **Retro:** Ne iyi gitti, nerede takıldık, Sprint 2'de neyi değiştiriyoruz.
5. Danışmana 5 satırlık ilerleme notu gönderilir.

### Gecikirse Kaydırılacaklar (Önce Bunlar, Sırayla)
* HHI ve overlap *(Yusuf Eren)* $\rightarrow$ Sprint 2'nin ilk günü
* KAP/TEFAS kullanım koşulları notu *(Akif)* $\rightarrow$ Sprint 2
* Listeleme uç noktaları *(Ahmet Emre)* $\rightarrow$ Sprint 2

### Kaymayacaklar
Şema, 1 gerçek PDF $\rightarrow$ JSON, recursive + matris look-through, Docker + CI. Bunlar 2 Aralık ara demosunun temeli; Çarşamba toplantısında bunlardan biri hâlâ başlamamışsa iş o toplantıda yeniden dağıtılır.
