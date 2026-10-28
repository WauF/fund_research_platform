## Ne değişti?
<!-- 1-3 cümle. İlgili issue: Closes #... -->

## Neden?

## Nasıl test edildi?

## Kontrol listesi
- [ ] Branch adı `feat/...` / `fix/...`, commit'ler `feat:` / `fix:` / `test:` önekli
- [ ] Testi var ve lokalde geçiyor (`uv run pytest` / `npm run lint`)
- [ ] PR küçük (ideal < 300 satır)
- [ ] PDF, `.env` veya gerçek LLM çağrısı yok (testler `tests/recorded/` kullanır)
- [ ] `backend/schemas/` değiştiyse: 3 onay alındı
- [ ] DB şeması değiştiyse: migration + çalışan `downgrade()` var, gidiş-dönüş denendi ve açıklamada
      **Rollback** notu var (kurallar: `.claude/skills/db-migrations/SKILL.md`)
- [ ] Önemli bir karar varsa `docs/decisions/` altına not eklendi
