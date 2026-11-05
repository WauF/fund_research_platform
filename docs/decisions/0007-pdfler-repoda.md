# 0007 — Kaynak PDF'ler repoda tutulsun mu?

- **Tarih:** 2026-10-31
- **Durum:** önerildi (ekip onayı bekliyor; şu an geçerli kural: PDF'ler git'e girmez)
- **Karar verenler:** —

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

## Öneri
B veya C (Akif). Hangisi seçilirse seçilsin, bir PDF'in üzerine yazılmaz; revizyon yeni dosya
olarak eklenir (spec: eski rapor girdileri korunur). Değişiklik `.gitignore`,
`.pre-commit-config.yaml` ve README'ye dokunduğu için Paket C sahibinin onayı gerekir.
