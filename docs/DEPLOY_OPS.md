# Production deploy operations (Phase A)

Run these steps on your **production** Supabase project and **host environment** before a controlled go-live. No code deploy is required for this section beyond what is already merged.

## 1. Secret audit (local / CI)

Before pushing or sharing the repo:

```bash
cd /path/to/grade9
git log --all --full-history -- engine/.env app/.env 2>/dev/null || true
```

If `.env` ever appeared in history, treat keys as compromised and **rotate** them in Anthropic + Supabase.

Confirm `.env` is ignored:

- [engine/.gitignore](../.gitignore) lists `.env` and `.env.*` (with `!.env.example`).

## 2. Supabase SQL (production)

In the Supabase dashboard → **SQL Editor**, run each file **in order** (same order as filenames):

| Order | File |
|------|------|
| 1 | [sql/001_schema.sql](../sql/001_schema.sql) |
| 2 | [sql/002_seed_data.sql](../sql/002_seed_data.sql) |
| 3 | [sql/003_question_quotas_and_past.sql](../sql/003_question_quotas_and_past.sql) |
| 4 | [sql/004_neco_subjects.sql](../sql/004_neco_subjects.sql) |
| 5 | [sql/005_jupeb_institution_subjects.sql](../sql/005_jupeb_institution_subjects.sql) |
| 6 | [sql/006_subject_catalog_expansion.sql](../sql/006_subject_catalog_expansion.sql) |
| 7 | [sql/007_subject_display_rank.sql](../sql/007_subject_display_rank.sql) |

If a migration was partially applied before, resolve conflicts manually; do not skip earlier files.

## 3. Host environment

Set these **environment variables** on the service that runs the FastAPI app:

| Variable | Required | Notes |
|----------|----------|--------|
| `SUPABASE_URL` | Yes | Project URL |
| `SUPABASE_SERVICE_KEY` | Yes (preferred) | Server-side; avoid anon if you need RLS bypass |
| `SUPABASE_ANON_KEY` | Fallback | If service key not set |
| `ANTHROPIC_API_KEY` | Yes | Engine calls `validate_settings` at startup |
| `ANTHROPIC_MODEL` | Yes | e.g. `claude-haiku-4-5-20251001` |
| `CORS_ALLOWED_ORIGINS` | Optional | Comma-separated; empty = `*` with credentials off |
| `CORS_ALLOW_CREDENTIALS` | Optional | `true` only if you need credentialed browser clients |
| `ADMIN_API_KEY` | Optional | If unset, `GET /api/admin/stats` returns 503 |
| `DOWNLOAD_PACK_BACKFILL_DEFAULT` | Optional | `false` recommended for mobile timeouts |

See [.env.example](../.env.example) for short descriptions.

**Cold starts:** Free tiers may sleep; first request after idle can take 30–60+ seconds. The Flutter client uses a 60s HTTP timeout by default.

## 4. Flutter release builds

Use your **production engine URL** (no trailing slash):

```bash
flutter build apk --release --dart-define=API_BASE=https://your-engine.onrender.com
flutter build appbundle --release --dart-define=API_BASE=https://your-engine.onrender.com
flutter build ipa --release --dart-define=API_BASE=https://your-engine.onrender.com
```

## 5. Manual QA

Follow [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md) (national offline path, JAMB tabs, WAEC/NECO single, school network path, sparse pack messaging).

## 6. Store / marketing copy (honest scope)

- **JAMB, WAEC, NECO:** Offline syllabus topics and offline practice from downloaded question packs; JAMB supports multiple subjects with tabs where applicable.
- **POST UTME / JUPEB:** Requires an internet connection for the current app flow; not the same offline pack experience as national exams.

## Exit criteria

- [ ] Migrations applied on prod without blocking errors  
- [ ] Health check and a sample API (e.g. `/api/exams`) succeed after cold start within client timeout  
- [ ] Admin stats not public unless `ADMIN_API_KEY` is set and used  
- [ ] QA checklist signed off for beta scope  
