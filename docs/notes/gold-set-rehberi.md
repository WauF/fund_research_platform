# Gold set etiketleme rehberi

Gold set, çıkarımın doğruluğunu ölçen elle etiketlenmiş rapor setidir (başarı kriteri 1:
held-out raporlarda F1 ≥ 0,95, ağırlık hatası ≤ 0,10 puan; taslak hedef, pilottan sonra
sabitlenir). Hedef: **12 rapor, en geç 5–6 Kasım.**

## Hangi raporlar
Her format ailesinden en az biri, zor durumları kapsayacak şekilde. **Held-out** raporları
prompt'u ve kuralları yazan kişi (Akif) görmez ve etiketlemez.

| Rapor | Aile | Neden | Set | Etiketleyen |
|---|---|---|---|---|
| IRF | standart | Kök fon; elle referans zaten var (`data/irf_look_through_elle.csv`) | geliştirme | Akif |
| ICH | standart | 7 alt fon, bölünmüş ad satırları | geliştirme | Akif |
| IRB | standart | Açığa satış (negatif) satırları, haftalık | geliştirme | Akif |
| TPC | standart | Yerli/yabancı BYF, döviz satırları (ağırlık 0) | geliştirme | Akif |
| GTM | Garanti | İngilizce sayılar, lot satırları, bozuk karakter | geliştirme | Akif |
| EIB | Astra | Tek oran sütunu, GSYF/GYF fonları | geliştirme | Akif |
| ZBJ | Ziraat | A–AA bölümleri | geliştirme | Akif |
| NJR | taranmış | OCR, O/0 karışıklığı | geliştirme | Akif |
| PBI | standart | 30+ fon | **held-out** | Yusuf Eren |
| GPB | Garanti | Fon ve BYF satırları | **held-out** | Yusuf Eren |
| PGD | Astra | VİOP kısa pozisyon | **held-out** | Ahmet Emre |
| PPI | Yapı Kredi | İngilizce sayılar, kendine özgü düzen | **held-out** | Ahmet Emre |

## Dosya biçimi
`data/gold/<KOD>_2026-09.csv`, bir satır = raporun portföy tablosundaki bir satır.
Sütunlar `Holding` şemasıyla aynıdır (`backend/schemas/holding.py`):

```csv
row_no,page,quote,name,asset_type,isin,instrument_code,held_fund_code,currency,value,weight,weight_basis
1,1,"NETGL TL NET 60.000,00",NET GLOBAL ENDÜSTRİYEL YATIRIMLAR AŞ,equity,TRENETG00027,NETGL,,TRY,977400.00,0.0029,portfolio
```

Özet tablo ayrı dosyada: `data/gold/<KOD>_2026-09_summary.csv`
(`page,quote,portfolio_value,cash_equivalents,receivables,other_assets,liabilities,total_value`).

## Kurallar
1. **Sayılar kesir ve nokta ondalıklı:** `40.073.740,62` → `40073740.62`, `%12,02` → `0.1202`.
2. **Her basılı satır bir satırdır.** Garanti'de aynı hissenin her lotu ayrı satır; toplamayın.
   GRUP TOPLAMI satırlarını yazmayın.
3. **Ağırlık tabanı:** rapor FPD ve FTD veriyorsa FPD'yi yazın (`portfolio`). Tek oran varsa
   `unknown`.
4. **İşaretler:** açığa satış ve karşılık satırları raporda negatifse negatif yazın. Özette
   borçlar her zaman negatif.
5. **ISIN** iki satıra bölünmüşse birleştirin (`TRMDLYWWWW` + `W9` → `TRMDLYWWWWW9`). Taranmış
   raporda O/0'ı PDF'e bakarak düzeltin.
6. **held_fund_code** yalnızca yatırım fonu / BYF satırında; BYF'lerde borsa kodu ile KAP fon kodu
   farklı olabilir (GMSTR → FGS), KAP'ta kontrol edin. Yabancı ETF'lerde boş.
7. **Döviz satırları** ağırlığı 0 olsa da tabloda basılıysa yazılır (değer "hazır değerler"de).
8. **quote** satırın PDF'teki ilk basılı satırıdır; `page` o satırın sayfası.
9. Emin olmadığınız satırı atlamayın: yazın ve `notes` sütununa (isteğe bağlı) not düşün.

## Kontrol
- Etiketleyen dosyayı bitirince satırların değer toplamını özet tablodaki portföy değeriyle
  karşılaştırır (doğrulamadaki kuralın aynısı: fark ≤ %0,5).
- Her dosyayı ikinci bir kişi rastgele 5 satırda PDF'le karşılaştırır (held-out dosyalarda
  Akif değil).
