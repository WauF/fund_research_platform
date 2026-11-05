# KAP ve TEFAS verisinin kullanımı (taslak)

- **Durum:** taslak; aşağıdaki "Doğrulanacaklar" bölümü elle kontrol edilmeden kesinleşmez.
- **Sorumlu:** Mehmet Akif Çavuş (Paket A)
- **Tarih:** 2026-10-31

Sunumda "confirmed access and reuse terms for KAP and TEFAS" sözü verdik (Project Requirements).
Bu not, verinin projede nasıl kullanıldığını ve koşulların hangi noktalarının doğrulanması
gerektiğini toplar. Hukuki görüş değildir; şüpheli bir noktada danışmana sorulur.

## Projede kullanım
| Kaynak | Ne alıyoruz | Nasıl | Nerede duruyor |
|---|---|---|---|
| KAP | Fonların portföy dağılım raporları (PDF) | Elle, tek tek ([0005](../decisions/0005-kap-elle-indirme.md)) | Link + SHA-256 `data/corpus.csv`'de; PDF'ler yerelde (repoda olup olmayacağı [0007](../decisions/0007-pdfler-repoda.md)) |
| TEFAS | Günlük fon fiyatları (getiri serileri, Paket B) | Henüz başlanmadı | — |

- Amaç akademik (CSE 496 bitirme projesi), ticari değil.
- Veriler herkese açık yayımlanan bildirimler; kişisel veri içermiyor.
- Her çıkarılan değer kaynağına (rapor, sayfa, alıntı) bağlı; arayüzde kaynak gösterilir.
- Ham PDF'ler projenin dışına dağıtılmaz. Repo gizli kalmalı; 0007'de B veya C seçilirse bu şart.

## Bilinenler
- KAP fon bilgi sayfaları robots.txt ile otomatik taramayı yasaklıyor (sunum, slayt 5;
  12.10.2026'da bakıldı). Bu yüzden indirme elle yapılıyor ve otomatik bir keşif (discovery)
  aracı yazılmayacak.
- KAP dosya linklerindeki kimlik, yükleme zamanını içeriyor ([0005](../decisions/0005-kap-elle-indirme.md));
  bunu kullanmak ek istek gerektirmiyor.

## Doğrulanacaklar (elle, tarayıcıda)
- [ ] kap.org.tr sayfa altındaki "Kullanım Koşulları" / "Yasal Uyarı" metni: içeriğin
      çoğaltılması, saklanması ve türetilmiş veri olarak gösterilmesi hakkında ne diyor?
      İlgili maddeyi ve erişim tarihini buraya alıntılayın.
- [ ] kap.org.tr/robots.txt güncel içeriği (hangi yollar kapalı; `/tr/api/file/download/` dahil mi?).
- [ ] tefas.gov.tr sayfa altındaki yasal uyarı / kullanım koşulları: fiyat verisinin indirilmesi
      ve uygulamada gösterilmesi hakkında ne diyor? Toplu indirmeye izin veriliyor mu?
- [ ] tefas.gov.tr/robots.txt güncel içeriği.
- [ ] Belirsizlik kalırsa: danışmana kısa bir e-posta (akademik kullanım, gizli repo, kaynak
      gösterimi) ve cevabı `docs/decisions/` altına not.

Bu kontroller bu oturumda yapılamadı: iki sitenin sayfalarına buradan erişilemedi.

## Sonuç (doğrulamadan sonra doldurulacak)
- KAP: …
- TEFAS: …
