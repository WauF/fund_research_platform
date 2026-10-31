# 0007 — Kaynak PDF'ler repoda (data/raw/)

- **Tarih:** 2026-10-31
- **Durum:** kabul edildi
- **Karar verenler:** Mehmet Akif Çavuş, Ahmet Emre Kurt

## Bağlam
Repo kuralı PDF'leri dışarıda tutuyor (`.gitignore`, pre-commit `no-pdfs` kancası,
`check-added-large-files` 1024 KB). Eylül corpus'u 58 PDF, toplam 21 MB; elle indirmek (0005)
her kurulumda yaklaşık bir saat sürüyor ve ekipteki herkesin aynı dosyalarla çalışması gerekiyor.
Repo gizli.

## Seçenekler
- **A — Kural aynen kalır.** PDF'ler `corpus.csv`'deki linkten indirilir. Artı: repo küçük, mevcut
  CI/pre-commit değişmez. Eksi: herkes 58 dosyayı elle indirir; KAP bir dosyayı kaldırırsa kaybolur.
- **B — PDF'ler git'te.** `data/raw/` izlenir. Eksi: `no-pdfs` kancası ve 1 MB sınırı değişmeli
  (7 dosya 1 MB'tan büyük, en büyüğü 5,1 MB); sürümler birikir.
- **C — PDF'ler Git LFS'te.** Artı: clone hızlı, sınırlar korunur. Eksi: LFS kotası, CI'da ek ayar.
- **D — PDF'ler paylaşılan bir klasörde** (Drive) + `corpus.csv`'deki SHA-256 ile doğrulama.

## Karar
**B.** PDF'ler `data/raw/<KOD>/` altında git'te tutulur. 21 MB için LFS gereksiz; repo 100 MB'a
yaklaşırsa C'ye (LFS) geçilir. MediaFire gibi herkese açık bir paylaşım düşünüldü, link herkese
açık olduğu ve kalıcı olmadığı için seçilmedi.

Kurallar:
- PDF yalnızca `data/raw/` altında olabilir (`.gitignore` ve pre-commit `no-pdfs` bunu zorlar).
- Bir PDF'in üzerine yazılmaz; revizyon yeni dosya olarak eklenir. `data/corpus.csv` her dosyanın
  SHA-256'sını tutar.
- Repo gizli kalır. KAP kullanım koşulları doğrulanınca (`docs/notes/kap-tefas-kullanim-kosullari.md`)
  saklamayı yasaklayan bir madde çıkarsa bu karar yeniden açılır.

Eski öneri metni: Hangisi seçilirse seçilsin, bir PDF'in üzerine yazılmaz; revizyon yeni dosya
olarak eklenir (spec: eski rapor girdileri korunur). Değişiklik `.gitignore`,
`.pre-commit-config.yaml` ve README'ye dokunduğu için Paket C sahibinin onayı gerekir.
