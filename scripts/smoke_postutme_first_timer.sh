#!/usr/bin/env bash
# Smoke test: POST-UTME first-timer parity path.
# Usage: from repo root,  ./engine/scripts/smoke_postutme_first_timer.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BASE="${API_BASE:-http://127.0.0.1:8000}"
YEAR="${SMOKE_YEAR:-2025}"
INST="${SMOKE_POSTUTME_INSTITUTION:-University of Lagos}"
SUBJECT="${SMOKE_POSTUTME_SUBJECT:-English Language}"

echo "== Base URL: $BASE"
echo "== POST-UTME institutions ($YEAR)"
curl -sS "$BASE/api/school-exams/institutions?exam_mode=post-utme&year=$YEAR" | python3 -c "import sys,json; d=json.load(sys.stdin); rows=d.get('institutions') or []; print('count', len(rows)); print([r.get('institution_name') for r in rows[:6]])" 2>/dev/null || true
echo ""

echo "== POST-UTME subjects for $INST"
curl -sS --get "$BASE/api/school-exams/subjects" \
  --data-urlencode "exam_mode=post-utme" \
  --data-urlencode "institution_name=$INST" \
  --data-urlencode "year=$YEAR" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); rows=d.get('subjects') or []; print('count', len(rows)); print(rows[:10])" 2>/dev/null || true
echo ""

echo "== POST-UTME questions prepare/fetch ($SUBJECT, limit=40)"
curl -sS --get "$BASE/api/school-exams/questions" \
  --data-urlencode "exam_mode=post-utme" \
  --data-urlencode "institution_name=$INST" \
  --data-urlencode "year=$YEAR" \
  --data-urlencode "subject=$SUBJECT" \
  --data-urlencode "limit=40" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); qs=d.get('questions') or []; print('status', d.get('status'), 'count', d.get('count'), 'questions', len(qs)); print('generation_state', d.get('generation_state')); print('sample_keys', list(qs[0].keys())[:12] if qs else [])" 2>/dev/null || true
echo ""
echo "Done. Manual app check: POST-UTME -> Institution -> Subject download -> ready>=40 -> config -> instructions -> start practice."
