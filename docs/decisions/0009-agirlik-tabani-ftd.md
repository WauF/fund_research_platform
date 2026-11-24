# 0009 — Kayıtlar hangi ağırlık tabanıyla saklanır (FPD mi FTD mi)

- **Tarih:** 2026-11-07
- **Durum:** önerildi (Paket B'nin onayı bekleniyor)
- **Karar verenler:** Mehmet Akif Çavuş

## Bağlam
Standart şablondaki raporlar her satır için iki oran basıyor:
- **FPD** (fon portföy değerine oranı, *portfolio weight*): satır değeri / portföy değeri.
- **FTD** (fon toplam değerine oranı, *total-value weight*): satır değeri / fon toplam değeri
  (*net asset value*). Toplam değer = portföy değeri + hazır değerler + alacaklar + diğer
  varlıklar − borçlar.

Look-through için doğru oran FTD: bir yatırımcının fon payı fonun toplam değerinin bir payıdır,
alt fonun payı da onun toplam değerinin bir payı. Portföy dışı kalemler (VİOP teminatı, mevduat,
borçlar) FPD'de görünmüyor. IRF'de FPD/FTD = 0,8797, yani FPD ile hesaplanan look-through her
seviyede yaklaşık %14 şişiyor (1 / 0,8797 = 1,137).

Baseline şimdiye kadar yalnızca FPD'yi okuyordu (`weight_basis = portfolio`). Paket B'nin
`build_graph`'ı `weight_basis` alanına bakmıyor (#13 incelemesi).

## Karar
- **Doğrulama FPD üzerinde yapılır, kayıtlar FTD (`weight_basis = total`) ile saklanır.**
  Ağırlık toplamı kontrolü FPD'de net: satırların toplamı 1,00 olmalı. FTD'de beklenen toplam
  portföy dışı kalemlere bağlı.
- FTD raporda basılıysa basılı değer kullanılır. Bazı satırlarda (ör. VİOP teminatı) FTD sütunu
  boş; orada `değer / toplam değer` hesaplanır ve 4 haneye yuvarlanır.
- Satırın `status` değeri FPD doğrulamasından gelir, FTD'ye çevrilirken korunur.
- Tek oran basan raporlar (Astra, Ünlü, Ziraat: `unknown`) bu karara girmez; LLM çıkarımı ve elle
  etiketleme tabanı rapordan okur.

## Değerlendirilen seçenekler
- **FPD sakla, look-through çevirsin** — artı: rapordaki ilk oran / eksi: her tüketici özet
  tablosunu da okumak zorunda kalır; FTD sütunu boş olan satırlar her yerde ayrı ayrı çözülür.
- **İkisini de sakla** — artı: bilgi kaybı yok / eksi: `Holding` şemasında değişiklik (3 onay),
  hangi alanın kullanılacağı yine her yerde ayrı karar.
- **FTD sakla, FPD'de doğrula** — artı: şema değişmiyor, look-through doğrudan kullanır, FPD
  istenirse `değer / portföy değeri` ile geri hesaplanır / eksi: doğrulama ile saklama farklı
  tabanda. **Seçildi.**

## Sonuçları
- Paket A: `extraction.baseline.to_total_basis()` doğrulamadan sonra çağrılır; DB'ye yazan komut
  bunu kullanır.
- Paket B: `build_graph` yalnızca `weight_basis = total` kayıtları kabul etmeli, diğerlerinde hata
  vermeli ya da açıkça uyarmalı.
