# Fund Research & Exposure Platform

CSE 496 bitirme projesi — Gebze Teknik Üniversitesi.
KAP'ta yayımlanan fon portföy raporlarını (PDF) yapılandırılmış `Holding` kayıtlarına çevirir ve
fon-içinde-fon yapılarında **look-through** ile gerçek varlık maruziyetini hesaplar.

**Ekip:** Mehmet Akif Çavuş · Ahmet Emre Kurt · Yusuf Eren Nalbant
**Danışman:** Fatih Özhamaratlı

## Repo yapısı

```
backend/            Python 3.12 (uv)
  app/              FastAPI uygulaması                    — Paket C
  storage/          MinIO + DB repository katmanı          — Paket C
  schemas/          Ortak Pydantic şemaları (3 onay)       — Paket A
  extraction/       PDF → Holding çıkarımı (LLM)           — Paket A
  exposure/         Look-through / risk motoru             — Paket B
  tests/            pytest; fixtures/ ve recorded/ (kayıtlı LLM çıktıları)
frontend/           Next.js (TypeScript, Tailwind, App Router)
docs/decisions/     Karar notları
docs/plans/         Sprint planları
data/corpus.csv     Rapor listesi (KAP linki + SHA-256) — PDF'ler git'e girmez
```

## Kurulum

Gereksinimler: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 20+, Docker.

```bash
# Backend
cd backend
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .

# Frontend
cd frontend
npm install
npm run dev        # http://localhost:3000

# Git hook'ları (repo kökünde, bir kez)
uv tool install pre-commit
pre-commit install
```

Ortam değişkenleri: `cp .env.example .env`.

## Çalışma kuralları

- `main`'e doğrudan push yok. Branch: `feat/...`, `fix/...`. Commit: `feat:`, `fix:`, `test:` önekli.
- Bir görev dört koşulla biter: kod yazıldı, testi var, bir arkadaş onayladı, CI yeşil.
- `backend/schemas/` değişiklikleri 3 onay ister.
- CI gerçek LLM API'sini asla çağırmaz; testler `backend/tests/recorded/` ile çalışır.
- PDF'ler ve `.env` git'e girmez.
- PR'lar küçük (ideal < 300 satır); inceleme 24 saat içinde.
- Önemli kararlar `docs/decisions/` altına yazılır.
