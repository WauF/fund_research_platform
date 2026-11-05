# Veri bulguları ve dikkat edilecekler (Eylül 2026 IRF corpus'u)

Repo açılmadan önce (25 Ekim) yapılan veri incelemesinin kaydı. Kararlar ayrı notlar olarak
`docs/decisions/` altında (0002–0007); burada bulgular, açık sorular ve elle look-through sonuçları var.

**İlgili veri dosyaları**
- `data/corpus.csv`: indirilen 58 rapor. İlk dört sütun repo şablonuyla aynı (`fund_code`,
  `report_period`, `kap_url`, `sha256`); ek sütunlar: `level` (IRF'ye göre seviye), `report_kind`
  (`monthly`/`weekly`), `period_start`/`period_end`, `primary` (`yes`: hesapta kullanılan rapor,
  `no`: diğer haftalar, `duplicate`: birebir kopya), `kap_upload_utc` (linkten çözülen yükleme
  zamanı), `pdf_created_utc`, `local_path`, `notes`.
- `data/irf_look_through_elle.csv`: IRF'nin elle çıkarılmış look-through ağacı (2. seviye 20 fon,
  3. seviye 28 pozisyon), yol ağırlıkları (`path_weight_in_root`) ve rapor durumuyla
  (`report_status`: `available`, `not_found`, `not_published`, `expected_unresolved`,
  `not_downloaded`). Ağırlıklar kesir; `weight_basis` şemadaki değerlerle aynı. Çıkarım ve look-through sonuçları
  bununla karşılaştırılacak (Paket B için de referans).
- PDF'ler: `data/raw/<KOD>/<KOD>_2026-09.pdf` (birincil), `haftalik/` (diğer haftalar),
  `haftalik/_kopya/` (birebir kopyalar). Repoda olup olmayacağı: [0007](../decisions/0007-pdfler-repoda.md).

## 1. Açık sorular

1. KAP'ta IRF'nin haftalık dışında ayrı bir **aylık** Eylül 2026 raporu var mı? ([0004](../decisions/0004-referans-tarih.md))
2. Look-through kesme eşiğinin değeri ([0002](../decisions/0002-look-through-kesme-esigi.md); öneri %0,05).
3. Tek oran veren raporlarda (EIB, PGD, SUA ve Ziraat formatı) oran FPD'ye mi FTD'ye mi göre?
4. FGS'nin haftalık raporu hangi haftaya ait? (PDF 01.10'da üretilmiş, başlıkta tarih yok.)
5. Hâlâ bekleyen ekip kararları: LLM erişimi (API mi, danışmanın GPU'su mu), 4. fon (GTM mi HIH mi).
6. PDF'ler repoda mı tutulacak? ([0007](../decisions/0007-pdfler-repoda.md))

## 2. Veri bulguları

### 2.1 Kimlik ve dosyalar
- **Dosya adı güvenilmez.** GPB'nin raporu kaynakta bazen "GBP" adıyla iniyor.
- **Ad eşleştirme güvenilmez.** SUA raporunda fonun adı "QNB Finans Portföy Gümüş BYF" diye geçiyor. KAP'taki adı "QNB Portföy Gümüş Katılım BYF".
- **Borsa kodu ile KAP fon kodu farklı olabilir.** Borsa yatırım fonlarında (BYF) raporda borsa kodu (GMSTR) yazıyor, KAP fon kodu farklı (FGS). Bu fonlar için borsa kodu → fon kodu eşleme tablosu gerekecek.
- **Kurucu/yönetici alanı tutarsız.** EIB "Astra" adlı ama kurucu QInvest yazıyor; PGD'de kurucu "T. İş Bankası". Kimlik için bu alanlara güvenilmemeli.
- **Aynı içerik, farklı SHA-256.** AP7, PIS ve PKV'nin 07–11.09 raporları KAP'ta iki kez yayımlanmış: metin birebir aynı, PDF oluşturma tarihi aynı, hash farklı. `POST /documents`'ın SHA-256 tabanlı tekrar önlemesi bunları **iki ayrı belge** olarak kaydeder. Belge düzeyinde bu kabul edilebilir (iki ayrı dosya), ama çıkarım düzeyinde içerik bazlı bir kontrol gerekir (fon kodu + dönem + toplam değer); yoksa "reprocessing creates 0 duplicate holdings" kriteri bozulur.

### 2.2 Rapor türü ve tarih
- **Serbest ve kısa vadeli fonlar haftalık rapor yayımlıyor:** AP7, PIS, PKV, KVS, NLK, IRB. Bir ay içinde 4–5 rapor çıkıyor.
- **Haftalık raporların çoğunun başlığında hafta yazmıyor**, sadece "Eylül-2026". Hafta, PDF oluşturma tarihi ve pay fiyatlarının sırasıyla belirlendi. Örnek: 14.09'da üretilen rapor 07–11.09 haftası, 05.10'da üretilen 28.09–02.10.
- **IRF'nin kendi raporu da haftalık:** "Haftalık Pay Fiyatı", "Hafta içinde yapılan giderler" geçiyor. PDF 05.10'da üretilmiş.
- **IRB'de yanlış dosya "aylık" sanılmıştı:** aslında 07–11.09 haftalığıydı. Düzeltildi; birincil artık 28.09–02.10 haftalığı.
- **Birincil raporların tarihleri karışık:** bir kısmı aylık (30.09), bir kısmı haftalık (02.10; NLK 04.10). Fark en fazla 4 gün. Sonuçta her yolun rapor tarihi ve en büyük tarih farkı gösterilmeli.
- **KAP dosya linki yükleme zamanını içeriyor.** `.../api/file/download/<32 hex>` kimliğinin 17–28. karakterleri, milisaniye cinsinden yükleme zamanı (Hibernate UUID). Örnek: `4028328c a09bee8f 01a0a5505003 45e7` → 15.09.2026 13:44 UTC. Bu sayede başlığında tarih olmayan haftalık raporların haftası, dosyayı indirmeden belirlenebilir; `corpus.csv` içindeki `kap_upload_utc` sütunu buradan geliyor. Discovery aşamasında doğrudan kullanılabilir.
- **Aynı raporun yeniden yüklenmesi:** Pardus fonlarının (AP7, PIS, PKV) 22.09'da iki yüklemesi var (11:40 ve 13:37). 13:37 yüklemesi 14–18.09 raporu; 11:40 yüklemesi 07–11.09 raporunun tekrar yüklenmesi (bizdeki birebir aynı kopyalar). PIS üzerinden toplam değerle doğrulandı. Yani KAP aynı raporu farklı bir dosya kimliğiyle yeniden yayımlayabiliyor; discovery aynı raporu iki kez almamalı.
- **TMV:** Eylül raporu yayımlanmamış, son rapor Ağustos → unresolved.
- **ICN:** raporu bulunamadı → unresolved.
- **Ağustos sonu haftası karışabiliyor:** NLK'nin 31.08–06.09 raporu indirilen dosyalar arasındaydı; dönem filtresi şart.

### 2.3 Formatlar
Birincil 36 raporda 6 format ailesi var:

| Aile | Raporlar | Not |
|---|---|---|
| Standart şablon ("A-)Fonun Adı") | 24 rapor: IRF, BGP, DLY, ECA, ICH, IOO, IRB, TE4, GTF, PTO, TPF, AC4, AP7, BBF, KHA, PBI, PIS, PKV, KVS, IDY, SHE, TPC, TYH, FGS | Çoğu yönetici aynı şablonu kullanıyor. Kural tabanlı baseline için en iyi hedef. |
| Garanti | GTM, GPB, GPZ | Sayılar İngilizce formatta |
| Astra / Ünlü ("1- FONU TANITICI") | EIB, EID, PGD, SUA | Tek oran sütunu; fonlar "Katılma Belgeleri" bölümünde |
| Ziraat ("AYLIK RAPORU") | ZPO, ZBJ | Bölümler A–AA |
| Yapı Kredi | PPI | Kendine özgü; sayılar **İngilizce** formatta |
| Taranmış görüntü (Nurol) | NJR, NLK | Metin katmanı yok, OCR gerekli |

### 2.4 Çıkarım tuzakları (Paket A)
- **Sayı formatı rapora göre değişiyor.** Garanti ve Yapı Kredi İngilizce (`975,489,543.87`, `4,891,376,352.39`), diğerleri Türkçe (`378.395.976,36`). Ayrıştırıcı formatı rapordan almalı; tahmin `1,234` gibi değerlerde yanlış okur.
- **Yüzde yazımı farklı:** `0.07%`, `12,02`, `0,385880`, `%1,63`.
- **Borç işareti farklı:** IRF'de eksi; Garanti ve Ziraat'ta artı yazılıp etiketle (`(-)`) belirtiliyor. ReportSummary'de borç her zaman negatife normalize edilmeli.
- **ISIN iki satıra bölünebiliyor:** `TRMDLYWWWW` + `W9`. Birleştirip kontrol hanesiyle (check digit) doğrulanmalı. `W` dolgulu ISIN'ler de kontrol hanesi testinden geçiyor.
- **Uzun fon adları 3–6 satıra bölünüyor;** ISIN, adın ortasındaki bir satırda kalabiliyor. Standart şablonda değer satırı güvenilir çapa: ISIN, üstündeki en yakın değer satırına ait.
- **Garanti'de aynı hisse her alım lotu için ayrı satırda** (GTM'de AEFES 19 satır). Satırlar korunur, look-through öncesi ISIN bazında toplanır.
- **Bozuk karakter kodlaması:** GTM'de `ı` → `;` ("Sat;n"); ECA'da `İ` → `Ġ`, `ş` → `ġ`. Alıntı (quote) doğrulaması normalleştirmeden sonra yapılmalı.
- **Sayfa sırası bozuk olabilir:** TPF'de VIII–IX. bölümler I. bölümden önce geliyor.
- **OCR:** NJR'de çalışıyor ama ISIN'de O ile 0'ı karıştırıyor (`TRYNRPOO0789`, doğrusu `TRYNRPO00789`). **Kontrol hanesi bunu yakalamıyor:** iki ISIN de geçerli, çünkü harf (O=24) ve rakam (0) farklı uzunlukta rakam dizisine açılıyor ve Luhn bu değişimi bazen fark etmiyor. OCR'dan gelen ISIN bilinen ISIN'lerle karşılaştırılmalı (`isin.resolve_against_known`). Ortamda yalnızca İngilizce Tesseract var, Türkçe karakterler kayboluyor; `tur` dil paketi kurulmalı.
- **Negatif satırlar gerçek:** açığa satış (short) pozisyonları ve karşılık satırları negatif nominal,
  değer ve ağırlıkla basılıyor (IRB, AP7, TYH hisseleri; TPC'de ETF'ler; GTF, TPF tahvilleri). Sunumdaki
  "negatif ağırlık yok" doğrulaması (slayt 9) bu yüzden geçersiz; şema negatif değere izin veriyor.
- **Döviz satırları portföy değerine girmiyor:** IDY, ECA ve TPC'de `USD USD FED USD ... 0,00 0,00 2,89`
  gibi satırların FPD ağırlığı 0, FTD ağırlığı var; değerleri "hazır değerler" kalemindedir. Türev
  (VİOP) satırlarındaki değer de nominal tutardır. İkisi de portföy toplamı kontrolünden çıkarılır.
- **Bir satırda iki okuma mümkün:** VİOP nakit teminatında FTD sütunu boş, bu yüzden satırın son dört
  sayısı "değer, grup %, FPD %, FTD %" de olabilir "nominal, değer, grup %, FPD %" de. Doğru okuma,
  değer / portföy değeri = FPD % eşitliğinden seçilir.
- **Fon kodu her zaman tireyle yazılmıyor:** `BGP-AK PORTFÖY`, `IOO - İŞ PORTFÖY` yanında `KVS TL`,
  `IHK İŞ PORTFÖY`, `(CKL) YAPI KREDİ` biçimleri de var.
- **Raporlarda holding dışı bölümler var:** portföye alışlar/satışlar, İTFA'lar, giderler. SUA'da GMSTR yüzlerce kez alış satırında geçiyor, holding tablosunda ise bir kez. Çıkarım yalnızca "Fon Portföy Değeri Tablosu" bölümünden yapılmalı.
- **Boş bölüm başlıkları:** ZPO ve standart şablonda içi boş "YATIRIM FONU" başlıkları var. Başlık var diye fon var sanılmamalı.
- **ISIN örüntüleri:** fon payları `TRY…` / `TRM…`; hisseler `TRA…`, `TRE…`; devlet borçlanma `TRT…`; özel sektör `TRS…`, `TRF…`, `TRD…`; VİOP `TRV…`; yabancı ETF `US…`.

### 2.5 Ağırlık tabanı (Paket A ve B)
- Standart şablon her satır için iki oran veriyor: **FPD'ye göre** (fon portföy değeri) ve **FTD'ye göre** (fon toplam değeri). `weight_basis` alanı şart.
- IRF'de fark büyük: fonlar FPD'nin %93,20'si ama FTD'nin %81,98'i. FPD, FTD'nin %87,97'si; çünkü alacaklar (%14,95) ve borçlar (−%2,92) var.
- GTM'de FPD, FTD'nin %100,33'ü (sunumdaki örnek: %102,80). Ağırlıklar %100'e tamamlanmak zorunda değil.
- Garanti formatında "Grup%" ve "Toplam%" var; Astra, Ünlü ve Ziraat tek oran veriyor (taban belirsiz, Açık soru 3).

### 2.6 PDF'ten metin çıkarma karşılaştırması ([0006](../decisions/0006-pdf-metin-araci.md))
`backend/scripts/compare_pdf_text.py`, 6 format ailesinden birer raporda 5 aracı karşılaştırır. Ölçüt: elle seçilmiş değerler metinde var mı; bir satırın tüm alanları (kod, değer, oranlar) aynı satırda kalıyor mu.

| Araç | Doğru | Süre (6 rapor) | Token (IRF / GTM) | Not |
|---|---|---|---|---|
| pdfplumber | 13/17 | 2,3 sn | ~4.600 / ~14.600 | Satırlar bütün, en az token. Saf Python. |
| PyMuPDF (sort) | 13/17 | 0,3 sn | ~10.000 / ~38.700 | En hızlı; sayfa görüntüsü ve kelime koordinatı da verir (review ekranı için). |
| pdftotext -layout | 13/17 | 0,1 sn | ~10.100 / ~28.300 | İnsan okuması için en rahatı; sistem bağımlılığı (poppler). |
| pdfplumber layout | 13/17 | 2,4 sn | ~19.600 / ~17.700 | Boşluk dolgusu token'ı katlıyor. |
| MarkItDown | 12/17 | 8,7 sn | ~9.900 / ~15.200 | EIB'de bir satırı bozdu; en yavaş, ağır bağımlılıklar. |

- Doğrulukta araçlar arasında fark yok; farkı **token sayısı** yapıyor. LLM maliyeti token'la ölçeklendiği için pdfplumber, diğerlerinin yaklaşık yarısıyla aynı bilgiyi veriyor.
- Hiçbir araç bölünmüş ISIN'i birleştirmiyor (`TRMDLYWWWW` + `W9`) → `isin.join_parts`.
- Hiçbir araç GTM'deki bozuk font eşlemesini düzeltmiyor (`Satın` → `Sat;n`); sorun PDF'in içinde → metin normalleştirmesi gerekir.
- Taranmış raporlarda (NJR, NLK) hepsi boş döner → OCR ayrı adım.
- pdfplumber'ın tablo çıkarımı güvenilir değil: IRF'de 3 tablo buldu, GTM'de hiç bulamadı (çizgisiz tablolar). Metin tabanlı yaklaşım daha tutarlı.

### 2.7 Kural tabanlı baseline sonuçları
`backend/scripts/evaluate_baseline.py` (31.10.2026): standart şablondaki 23 birincil raporun hepsi
okundu (FGS dönemi belirsiz olduğu için atlandı), **1.474 satır, 23/23 rapor doğrulamadan geçiyor**.
IRF'nin 20 alt fonu elle referansla birebir aynı (değer, ağırlık, ISIN, fon kodu); ICH, TE4 ve GTF'nin
alt fon listeleri de referansla aynı. Diğer 12 rapor (Garanti, Astra/Ünlü, Ziraat, Yapı Kredi,
taranmış) açıkça "desteklenmiyor" olarak reddediliyor. LLM çıkarımı bu çıtayı geçmeli (kriter 1).

## 3. IRF look-through sonuçları (elle)

**IRF (28.09–02.10):** toplam değer 378.395.976,36 TL. FPD 332.870.561,22. Alacaklar 56.572.172,96, borçlar −11.047.843,53. Fon dışı kalemler: NETGL hissesi, TEB mevduatı, VİOP nakit teminatı.

**2. seviye:** 20 alt fon, toplam 310.211.282,00 TL (FPD %93,20, FTD %81,98). Toplamlar raporla birebir tutuyor; 20 ISIN'in hepsi kontrol hanesinden geçiyor.
- En büyük 7 (FTD %): BGP 10,59 · IOO 10,46 · IRB 9,81 · ZBJ 8,56 · DLY 8,35 · PPI 8,17 · GPZ 8,11 → toplam ≈ %64.
- Rapor var: 18 fon. Unresolved: ICN (%0,04, bulunamadı), TMV (%0,07, yayımlanmamış).
- Fon tutmayanlar (2. seviyede biten): BGP, DLY, GPZ, IOO, IRB, PPI, ZBJ, PTO, TPF.
- ECA'nın yabancı ETF'leri (DRAM, DISK) yaprak olarak kalıyor; para birimi USD.

**3. seviye:** 28 fon pozisyonu, IRF içindeki toplam yol ağırlığı yaklaşık **%0,96**.
- ICH: 7 Pardus fonu (ICH'nin FTD'sinin %18,47'si).
- EIB: 8 fon; 6'sı girişim sermayesi (GSYF) veya gayrimenkul (GYF) fonu. Bunlar aylık portföy raporu yayımlamaz → beklenen unresolved.
- GPB: 4 Garanti fonu. TE4: 4 TEB fonu. NJR: 2 Nurol fonu. SUA (FGS), PGD (EID), GTF (KVS): birer fon.
- **Tekrar eden maruziyet:** EID hem EIB hem PGD içinde.
- **Döngü yok:** hiçbir alt fon IRF'yi tutmuyor.

**4. seviye:** PBI (ICH içinde) 30'dan fazla fon tutuyor; TPC (TE4 içinde) yerli ve yabancı BYF'ler tutuyor. Yol ağırlıkları: PBI ≈ %0,026, TPC ≈ %0,058. [0002](../decisions/0002-look-through-kesme-esigi.md) gereği burada durulur.

**Araştırma sorusu için ilk cevap:** yapı en az 4 seviye derin, ama ağırlığın neredeyse tamamı 2. seviyede. 3. seviye ≈ %0,96, 4. seviye < %0,1. Raporda yazmaya değer.

## 4. Plan ve süreç notları

İlk ay iş planı ve hafta 1 planının incelemesinden çıkanlar:

- **Paket dağılımı:** A (veri ve çıkarım) Mehmet Akif, B (exposure ve risk) Yusuf Eren, C (platform ve arayüz) Ahmet Emre. Ahmet Emre ile Yusuf Eren paketlerini takas etti.
- **Holding şeması en kritik bağımlılık;** üç onayla merge edilmeli. Taslak: `backend/schemas/holding.py` (PR `feat/schema-holding`). İçerdiği eklemeler:
  - `held_fund_code`: alt fon bağlantısı; graf bunsuz kurulamaz.
  - `value_tl`, `currency`: ECA'daki USD ETF'ler için.
  - Ayrı bir `ReportSummary`: portföy değeri, alacaklar, borçlar, toplam değer. Toplam toleransı kontrolü bunlarla yapılır.
  - Bu incelemeden gelen ekler: rapor türü (aylık/haftalık), kapsadığı tarih aralığı, `row_no` (lot satırları), `instrument_code` (borsa kodu; `held_fund_code`'dan ayrı), `weight_basis` için `unknown` değeri.
  - Şema yalnızca yapıyı zorlar; ISIN kontrol hanesi ve toplam toleransı gibi anlamsal kontroller kaydı reddetmez, `needs_review` yapar (kayıt kaybolmasın).
- **Snapshot sahipliği iki pakete dağılmış;** netleştirilmeli. Öneri: tablo ve tetikleyici C'de, snapshot üreten fonksiyon B'de.
- **"Geçerli kayıt" (effective holding) mantığı tanımsız:** orijinal kayıt + düzeltme. Kimin yazacağı belirlenmeli.
- **Exposure JSON formatı** Sprint 2 başı yerine Sprint 1 sonunda belirlenmeli; C erken başlayabilsin.
- **Gold set:** 12 rapor etiketlenmeli, en geç 5–6 Kasım'a kadar. Held-out olacak 4 raporu Paket A sahibi etiketlememeli. `irf_look_through_elle.csv` ilk referans olarak kullanılabilir.
- **Bireysel katkı:** spec her öğrencinin kendi önemli işini yapmasını istiyor; başkasının paketinin kod işine girilmemeli.
- **CI gerçek LLM çağırmaz;** testler kayıtlı çıktılarla çalışır. Prompt injection test PDF'i (gömülü talimatlı rapor) gerekli.
