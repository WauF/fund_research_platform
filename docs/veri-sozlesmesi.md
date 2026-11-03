# Veri sözleşmesi

Üç paketin ortak kullandığı verinin tanımı: alanlar ne anlama geliyor, kim yazıyor, kim okuyor,
nasıl değiştiriliyor.

- **Sahibi:** Ahmet Emre Kurt (Paket C). Bu dokümanı ve aşağıdaki dosyaları değiştiren her PR
  sahibinin onayını alır.
- **Kaynak dosyalar (doküman bunlarla çelişirse kod doğrudur, doküman düzeltilir):**
  - `backend/schemas/holding.py`: Pydantic sözleşmesi (`Holding`, `ReportSummary`)
  - `backend/storage/models.py`: veritabanı tabloları
  - `backend/migrations/versions/`: şema değişiklikleri
  - `backend/storage/extractions.py`: yazma ve okuma fonksiyonları
  - `backend/app/`: HTTP API
- **İlgili kararlar:** [0008 — run kimliği ve hangi run'ın sunulduğu](decisions/0008-extraction-run-secimi.md)

## 1. Genel akış

```
PDF ──POST /documents──▶ documents            (Paket C: SHA-256 ile tek kayıt)
                            │ 1
                            │ n
                         extraction_runs      (Paket A yazar: save_extraction_run)
                          │ 1          │ 1
                          │ n          │ 0..1
                       holdings    report_summaries
                          │
                          ▼
              look-through motoru     (Paket B okur: dokümanın en son ok run'ı)
```

- Bir PDF bir kez saklanır (`documents`), ama üzerinde birden fazla çıkarım yapılabilir
  (baseline, farklı modeller, yeniden deneme). Her çıkarım bir `extraction_runs` satırıdır.
- Kayıtlar (`holdings`, `report_summaries`) doğrudan PDF'e değil, ait oldukları run'a bağlıdır.
- Kayıtlar hiçbir zaman güncellenmez. Yeni bir çıkarım yeni bir run olarak eklenir.

## 2. Ortak kurallar

| Kural | Açıklama |
|---|---|
| **Ağırlık oran, yüzde değil** | %12,02 → `0.1202`. Aralık −1 … 1. |
| **Negatif değerlere izin var** | Açığa satış ve karşılık satırlarında `value`, `nominal` ve `weight` negatif olabilir. |
| **Borç her zaman ≤ 0** | `ReportSummary.liabilities` raporda pozitif basılsa bile negatif saklanır. İşareti düzeltmek çıkarımın işi. |
| **Para birimi her satırda** | `value` her zaman `currency` cinsindendir, TL olduğu varsayılmaz (ECA'da USD ETF var). |
| **Aynı ISIN birden fazla satırda olabilir** | Garanti raporları her alım lotunu ayrı satır basar. Tekil olan `(extraction_run_id, row_no)`. |
| **Ağırlık toplamı 1 olmak zorunda değil** | `total` tabanlı ağırlıklar FPD/FTD'ye toplanır (IRF'de ≈ 0,88). |
| **Sorunlu kayıt silinmez** | Doğrulamadan geçemeyen kayıt `status = needs_review` olarak saklanır. |
| **Her değerin kanıtı var** | `page` (1'den başlar) ve `quote` (PDF'teki satırın birebir metni). |
| **Dönem, tek tarih değil** | `period_start` + `period_end` + `report_kind`. Haftalık raporlar en fazla 7 gün kapsar. |

## 3. Alan sözlüğü

### 3.1 Her kayıtta olan alanlar (`holdings` ve `report_summaries`)

| Alan | Pydantic tipi | DB kolonu | Kural | Örnek |
|---|---|---|---|---|
| `fund_code` | str | `VARCHAR(6)`, indeksli | `^[A-Z0-9]{2,6}$`; raporu yayınlayan fonun KAP kodu | `"IRF"` |
| `period_start` | date | `DATE` | ≤ `period_end` | `2026-09-28` |
| `period_end` | date | `DATE` | Look-through'un referans tarihi bu | `2026-10-02` |
| `report_kind` | enum | `VARCHAR(16)` + CHECK | `monthly` / `weekly` | `"weekly"` |
| `page` | int | `INTEGER` | ≥ 1 | `1` |
| `quote` | str | `TEXT` | Boş olamaz; PDF'teki metin, değiştirilmeden | `"NETGL TL NET 60.000,00 …"` |
| `extraction_run_id` | UUID | `UUID`, FK → `extraction_runs.id` | Kaydın ait olduğu run | `"3f2b8c1e-…"` |
| `status` | enum | `VARCHAR(16)` + CHECK | `ok` / `needs_review` | `"ok"` |

### 3.2 `Holding` / tablo `holdings`: portföy tablosunun bir satırı

| Alan | Pydantic tipi | DB kolonu | Kural | Örnek |
|---|---|---|---|---|
| `row_no` | int | `INTEGER` | ≥ 1; run içinde tekil | `4` |
| `name` | str | `TEXT` | Boş olamaz | `"BGP-AK PORTFÖY"` |
| `asset_type` | enum | `VARCHAR(32)` + CHECK | Bkz. §3.4 | `"fund"` |
| `isin` | str \| null | `VARCHAR(12)`, indeksli | Biçim `^[A-Z]{2}[A-Z0-9]{9}[0-9]$`; kontrol hanesi doğrulamada bakılır | `"TRYAKPO00625"` |
| `instrument_code` | str \| null | `VARCHAR(32)` | Raporda basılan borsa/fon kodu | `"BGP"` |
| `held_fund_code` | str \| null | `VARCHAR(6)` | **Look-through bağlantısı.** Satır bir fonsa o fonun KAP kodu. Sadece `fund` / `etf` satırlarında dolu olabilir. Borsa kodundan farklı olabilir (GMSTR → FGS). | `"BGP"` |
| `nominal` | Decimal \| null | `NUMERIC(24,6)` | Adet/nominal | `null` |
| `value` | Decimal | `NUMERIC(24,6)` | `currency` cinsinden toplam değer | `"40073740.62"` |
| `currency` | str | `VARCHAR(3)` | ISO 4217, varsayılan `TRY` | `"TRY"` |
| `weight` | Decimal | `NUMERIC(16,10)` | −1 … 1, oran | `"0.1202"` |
| `weight_basis` | enum | `VARCHAR(16)` + CHECK | Bkz. §3.4 | `"portfolio"` |

### 3.3 `ReportSummary` / tablo `report_summaries`: fon toplam değer tablosu

Raporun IV. bölümü. Bir run'ın en fazla bir özeti olur.

| Alan | Raporda | DB kolonu | Kural | IRF örneği |
|---|---|---|---|---|
| `portfolio_value` | A) Fon portföy değeri (FPD) | `NUMERIC(24,6)` | ≥ 0 | `"332870561.22"` |
| `cash_equivalents` | B) Hazır değerler | `NUMERIC(24,6)` | ≥ 0 | `"1085.71"` |
| `receivables` | C) Alacaklar | `NUMERIC(24,6)` | ≥ 0 | `"56572172.96"` |
| `other_assets` | D) Diğer varlıklar | `NUMERIC(24,6)` | İşaret serbest | `"0"` |
| `liabilities` | E) Borçlar | `NUMERIC(24,6)` | **≤ 0** | `"-11047843.53"` |
| `total_value` | Fon toplam değeri (FTD) | `NUMERIC(24,6)` | > 0 | `"378395976.36"` |
| `currency` | — | `VARCHAR(3)` | Varsayılan `TRY` | `"TRY"` |

A + B + C + D + E ≈ `total_value` olmalı. Bu tutarlılık kontrolü doğrulamada yapılır (tolerans 1,00);
şema bu nedenle kaydı reddetmez.

### 3.4 Enum değerleri

| Enum | Değerler |
|---|---|
| `asset_type` | `equity` hisse · `bond` tahvil, bono, kira sertifikası · `fund` yatırım fonu · `etf` borsa yatırım fonu · `deposit` mevduat, katılım hesabı · `repo` repo, ters repo · `derivative` VİOP · `cash` nakit teminat, hazır değer · `other` |
| `weight_basis` | `portfolio` FPD'ye göre · `total` FTD'ye göre · `unknown` rapor tek oran veriyor, tabanını yazmıyor |
| `report_kind` | `monthly` · `weekly` |
| `status` | `ok` · `needs_review` |

Enum'lar veritabanında Postgres ENUM tipi değil, `VARCHAR` + `CHECK` olarak tutulur
(`.claude/skills/db-migrations`, kural 8). Yeni bir değer eklemek bir migration gerektirir.

### 3.5 Tablo `extraction_runs`: bir çıkarım çalışması

| Kolon | Tip | Açıklama |
|---|---|---|
| `id` | `UUID`, PK | **Çıkarım kodu üretir** (`uuid4()`), DB değil. Kayıtlar bu id'yi taşır. |
| `document_id` | `INTEGER`, FK → `documents.id`, indeksli | Hangi PDF |
| `model` | `VARCHAR(128)` | Baseline için `"baseline"`, LLM için sağlayıcının verdiği model adı |
| `prompt_version` | `VARCHAR(64)`, null olabilir | LLM çalışmalarında prompt sürümü (ör. `"2026-10-31.1"`) |
| `raw_output` | `TEXT`, null olabilir | Modelin ham cevabı, tekrar üretilebilirlik için. API'de dönmez. |
| `status` | `VARCHAR(16)` + CHECK | En az bir sorun varsa ya da herhangi bir kayıt `needs_review` ise `needs_review`, aksi halde `ok` |
| `issues` | `JSONB` | `[{"code", "message", "row_no"}]`; `row_no = null` sorunun bütün rapora ait olduğunu gösterir |
| `created_at` | `TIMESTAMPTZ` | Mikrosaniye hassasiyetinde; "en son run" sıralaması buna göre |

## 4. Paket A için: çıkarım sonucunu yazmak

```python
from uuid import uuid4
from storage.extractions import save_extraction_run

run_id = uuid4()                              # 1. id'yi çıkarımdan ÖNCE üret
holdings, summary = ...                       # 2. her kayda extraction_run_id=run_id ver
result = validate_report(holdings, summary, pages)   # 3. doğrula (status'lar kesinleşir)

save_extraction_run(                          # 4. tek transaction'da yaz
    session,
    run_id=run_id,
    document_id=document.id,
    model="baseline",                         # ya da client.model
    holdings=result.holdings,
    summary=result.summary,
    issues=result.issues,                     # Issue nesneleri ya da dict'ler
    prompt_version=None,                      # LLM'de PROMPT_VERSION
    raw_output=None,                          # LLM'de modelin ham cevabı
)
```

Hiçbir şey yazılmayan durumlar:

| Hata | Ne zaman |
|---|---|
| `LookupError` | `document_id` diye bir doküman yok |
| `ValueError` | Bir kaydın `extraction_run_id` değeri `run_id` ile aynı değil, ya da iki holding aynı `row_no`'ya sahip |
| `sqlalchemy.exc.IntegrityError` | Bu `run_id` ile daha önce bir run kaydedilmiş |

Doğrulamadan geçemeyen kayıtları **atma**: `needs_review` olarak yaz, inceleme ekranı onları
gösterecek.

## 5. Paket B için: look-through verisini okumak

- **Her doküman için tek run kullan:** `latest_run(session, document_id, only_ok=True)`.
  Aynı fonun satırları iki farklı run'dan gelirse ağırlıklar ikiye katlanır.
- Hiç `ok` run'ı olmayan bir doküman hesaba girmez; o fon **unresolved** sayılır.
- Bir fonun birden fazla raporu varsa (haftalık raporlar), referans tarihe (kök fonun
  `period_end` değeri) en yakın olanı seç. Bu seçimin yeri henüz kararlaştırılmadı, bkz. §8.
- Ağırlıklar `Decimal` olarak gelir; `float`'a çevirmek motorun kararı.

```python
from storage.extractions import latest_run, list_holdings

run = latest_run(session, document_id, only_ok=True)
rows = list_holdings(session, run.id) if run else []
holdings = [Holding.model_validate(r, from_attributes=True) for r in rows]
```

## 6. Arayüz ve diğer istemciler için: HTTP API

Tüm uç noktalar ve şemalar: `http://localhost:8000/docs` (OpenAPI).

| Uç nokta | Ne döner |
|---|---|
| `POST /documents` | PDF yükler. Yeni içerikse `201`, aynı içerik daha önce yüklendiyse `200` ve mevcut kayıt. |
| `GET /documents?limit=50&offset=0` | Dokümanlar, en yenisi önce. `limit` 1–200. |
| `GET /documents/{id}` | Tek doküman, yoksa `404` |
| `GET /documents/{id}/runs` | Dokümanın tüm run'ları, en yenisi önce (`raw_output` hariç) |
| `GET /documents/{id}/holdings` | Bir run'ın özeti ve satırları |

`GET /documents/{id}/holdings` parametreleri:

| Parametre | Varsayılan | Etkisi |
|---|---|---|
| `run_id` | — | Belirli bir run. Başka bir dokümana aitse `404`. |
| `only_ok` | `false` | `true` ise `needs_review` run'ları atlanır |
| `status` | — | Sadece bu durumdaki satırlar (`ok` / `needs_review`). `holding_count` yine run'ın tamamını sayar. |

Varsayılan olarak **en son run** döner, inceleme gerektirse bile. `run.status` alanına bak
(karar 0008).

Örnek cevap (`GET /documents/1/holdings`, kısaltılmış):

```json
{
  "run": {
    "id": "3f2b8c1e-5d4a-4e0b-9a7c-1b2d3e4f5a6b",
    "document_id": 1,
    "model": "baseline",
    "prompt_version": null,
    "status": "ok",
    "issues": [],
    "holding_count": 2,
    "created_at": "2026-11-03T11:39:36.347233+00:00"
  },
  "summary": {
    "fund_code": "IRF",
    "period_start": "2026-09-28",
    "period_end": "2026-10-02",
    "report_kind": "weekly",
    "page": 2,
    "quote": "FON TOPLAM DEĞERİ 378.395.976,36 100,00 %",
    "extraction_run_id": "3f2b8c1e-5d4a-4e0b-9a7c-1b2d3e4f5a6b",
    "status": "ok",
    "portfolio_value": "332870561.22",
    "cash_equivalents": "1085.71",
    "receivables": "56572172.96",
    "other_assets": "0",
    "liabilities": "-11047843.53",
    "total_value": "378395976.36",
    "currency": "TRY"
  },
  "holdings": [
    {
      "fund_code": "IRF",
      "period_start": "2026-09-28",
      "period_end": "2026-10-02",
      "report_kind": "weekly",
      "page": 1,
      "quote": "BGP-AK PORTFÖY TL AK 5.884.985,00 6,796958 29/09/26 6,809489 40.073.740,62",
      "extraction_run_id": "3f2b8c1e-5d4a-4e0b-9a7c-1b2d3e4f5a6b",
      "status": "ok",
      "row_no": 4,
      "name": "BGP-AK PORTFÖY",
      "asset_type": "fund",
      "isin": "TRYAKPO00625",
      "instrument_code": "BGP",
      "held_fund_code": "BGP",
      "nominal": null,
      "value": "40073740.62",
      "currency": "TRY",
      "weight": "0.1202",
      "weight_basis": "portfolio"
    }
  ]
}
```

İstemci tarafında dikkat:

- **Ondalıklar JSON'da string döner** (`"0.1202"`), sayı değil. Kayıpsız olsun diye böyle;
  hesap yapmadan önce sayıya çevir. Sondaki sıfırlar atılır: `977400.00` → `"977400"`.
- `created_at` zaman dilimiyle döner. Değerler UTC olarak yazılır; Postgres'in `TimeZone` ayarı
  (docker compose'da UTC) cevaptaki gösterimi belirler.
- Hata cevapları FastAPI biçimindedir: `{"detail": "..."}`. `404` kayıt yok, `422` geçersiz
  parametre (ör. UUID olmayan `run_id`).

## 7. Değişiklik süreci

Bir alan eklemek, silmek ya da anlamını değiştirmek istiyorsan:

1. Bir issue aç ya da bu dokümanın sahibine yaz: **ne** lazım ve **neden** (hangi rapor, hangi
   satır).
2. Değişiklik **tek bir PR**'da yapılır ve şunların hepsini içerir:
   - `backend/schemas/holding.py` (Pydantic sözleşmesi)
   - `backend/storage/models.py` + yeni bir migration (`.claude/skills/db-migrations`)
   - Bu doküman
   - Testler
3. `backend/schemas/` değiştiyse **3 onay** gerekir (sprint planı §2).
4. Merge edilmiş bir migration değiştirilmez, yeni migration yazılır (skill, kural 3).
5. Alan silmek ya da yeniden adlandırmak iki sürümde yapılır: önce yeni alan eklenir ve kod ona
   geçer, sonraki sürümde eski alan silinir (skill, kural 5).

Pydantic şemasında bir alan değişip tablo değişmezse `save_extraction_run()` hata verir
(`HoldingRow(**holding.model_dump())`). Bu bilerek böyle: sözleşme ile veritabanının ayrışması
sessizce geçmesin.

## 8. Açık konular

| Konu | Sorumlu | Etkisi |
|---|---|---|
| **Exposure JSON formatı** (look-through sonucunun API ve snapshot biçimi) | Yusuf Eren + Ahmet Emre | `snapshots` tablosu ve exposure uç noktaları buna bağlı |
| **`weight_basis` ve look-through** — motor hangi tabanla çarpacak, `unknown` ne olacak | Yusuf Eren | IRF'de iki taban arasında ≈ %14 fark var |
| **Bir fonun birden fazla raporu** — referans tarihe göre hangisinin seçileceği nerede yapılacak (sorgu mu, motor mu) | Yusuf Eren + Ahmet Emre | Haftalık rapor yayınlayan fonlar |
| **`corrections` tablosu ve "geçerli kayıt"** — inceleme ekranındaki düzeltmeler nasıl saklanacak | Ahmet Emre | İnceleme akışı |
| **Nakit/mevduatın para birimi** — look-through grafı şu an hepsini `CASH:TRY` düğümünde birleştiriyor | Yusuf Eren | Döviz riski yanlış görünür |
| **Karar 0008'in onayı** | Akif + Yusuf Eren | Run seçimi kuralı |
