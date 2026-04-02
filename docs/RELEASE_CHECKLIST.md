# Release checklist

Run before store submission or a major production deploy.

**Step-by-step production setup:** see [DEPLOY_OPS.md](./DEPLOY_OPS.md) (Supabase migration order, host environment, secret audit, Flutter `API_BASE`).

## Environment (engine host)

- [ ] `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (or anon), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- [ ] `CORS_ALLOWED_ORIGINS` set if you ship **Flutter web**; leave empty for mobile-only (`*` + no credentials)
- [ ] `ADMIN_API_KEY` set if you use `GET /api/admin/stats` (call with header `X-Admin-Key`)
- [ ] `DOWNLOAD_PACK_BACKFILL_DEFAULT` — leave `false` unless you accept extra latency/cost on pack downloads

## Supabase (production)

- [ ] Apply SQL migrations in order through the latest in `engine/sql/` (includes `023_past_questions_metadata.sql`, `024_question_images.sql` for past-question diagrams and `past_questions.image_url`).
- [ ] Optional: ingest licensed past MCQs (e.g. `engine/scripts/import_blyr_past_questions.py`) after `024` is applied so `image_url` is stored for diagram questions.

## Secrets

- [ ] `.env` never committed (`engine/.gitignore` ignores it)
- [ ] Rotate `ANTHROPIC_API_KEY` and `SUPABASE_SERVICE_KEY` if there was any leak risk

## Flutter production build

- [ ] `flutter build … --dart-define=API_BASE=https://your-engine.example.com` (no trailing slash)
- [ ] Optional support overrides: `--dart-define=SUPPORT_EMAIL=support@yourdomain.com` and `--dart-define=SUPPORT_WHATSAPP=234XXXXXXXXXXX` (digits only, country code, no `+`). Defaults live in `app/lib/config/beta_config.dart`.
- [ ] Activation/payments: engine Flutterwave checkout env vars set (`FLUTTERWAVE_*` / secrets per `engine` auth service); test `POST /api/auth/activation/checkout` end-to-end before store submission.

## QA (manual)

| Flow | Check |
|------|--------|
| National download | Download one subject → topics + pack; row shows ready for offline practice |
| WAEC/NECO | Single subject selected → configure → instructions → offline session (~40 questions); try year/difficulty/topic |
| JAMB | Up to 4 selected → multi-config → practice **tabs**; ~40 questions per subject |
| Sparse pack | With backfill off, empty filter shows clear messaging |
| School download parity | POST-UTME / JUPEB subject download prepares questions; row reaches ready state (>=40) before start |
| School start-practice | POST-UTME / JUPEB ready subject -> config -> instructions -> session opens with questions |
| School sparse data | If first fetch is sparse, auto-generation/retry fills; only show failure on true quota/config outage |
| AI tutor | In offline national practice, open **AI tutor** sheet; question sends to `POST /api/tutor/chat` (needs internet) |
| Weak topics | Miss a question offline → Drawer **Weak topics practice** lists subject → session from saved topics |

## Store submission (Apple / Google)

- [ ] Privacy policy URL + support URL (often same as support email or a contact page)
- [ ] Screenshots per required device sizes, feature graphic (Play), app description aligned with actual scope
- [ ] Content rating / data safety questionnaires (account data, optional analytics)
- [ ] Release signing: Android App Bundle / iOS archive + App Store Connect / Play Console tracks

## Store copy (honest scope)

- **National (JAMB, WAEC, NECO):** offline topics and offline practice from downloaded question packs; JAMB supports multiple subjects with tabs.
- **POST UTME / JUPEB:** subject download now includes readiness preparation before practice start (parity guard against dead-ends).
