# Complete Guide

## Architecture
- `app/config.py`: environment settings and validation.
- `app/db.py`: Supabase client factory.
- `app/schemas.py`: request models.
- `app/services/question_generator.py`: generation service entry.
- `app/api/routes.py`: API endpoints.
- `run.py`: FastAPI app bootstrap.

## API Endpoints
- `GET /api/exams`
- `GET /api/exams/{exam}/subjects`
- `GET /api/exams/{exam}/{year}/{subject}/topics`
- `POST /api/generate`
- `POST /api/topics/ingest`
- `POST /api/study-notes/generate`
- `GET /api/school-exams/institutions`
- `GET /api/school-exams/subjects`
- `GET /api/school-exams/topics`
- `POST /api/school-exams/generate`
- `GET /api/school-exams/questions`
- `GET /api/questions`
- `GET /api/study-notes`
- `GET /api/study-note-sets/{note_set_id}`
- `GET /api/question-sets/{set_id}`
- `GET /api/user/{email}/history`
- `GET /api/user/{email}/stats`
- `GET /api/admin/stats`
- `GET /api/practice/session` — practice set: **past_questions first**, then `generated_questions`

## Question quotas (WAEC/JAMB + Post-UTME/JUPEB)

Run `sql/003_question_quotas_and_past.sql` after `001`/`002`.

Rules (per `exam`, `year`, `subject`, `topic`, `difficulty`):

- At most **100** questions per difficulty (past + generated combined).
- At most **500** questions per topic across all difficulties (past + generated).

If limits are reached, `/api/generate` and `/api/school-exams/generate` return **400** with a quota message and **do not call** the LLM.

Ingest licensed past papers into `past_questions` / `institution_past_questions` so practice and RAG prefer real items.

## Generate Example
```json
{
  "exam": "waec",
  "year": 2024,
  "subject": "Physics",
  "difficulty": "hard",
  "topic": "all topics",
  "count": 40,
  "user_email": "student@example.com"
}
```

## Topic Ingestion Example

Use this endpoint to make topics syllabus-grade before question generation.

```json
{
  "exam": "waec",
  "year": 2024,
  "subject": "Physics",
  "raw_topics": [
    "Kinematics",
    "Motion in a straight line",
    "Dynamics",
    "Newton's laws",
    "Thermal physics"
  ],
  "source_text": "Optional syllabus excerpt copied from official source",
  "source_url": "https://example.com/waec-physics-syllabus",
  "create_subject_if_missing": false
}
```

Flow:
- Claude normalizes and deduplicates topics.
- Service upserts into `syllabus_topics` by `(subject_id, topic_name, year)`.
- Then `/api/generate` can use `topic='all topics'` or single topic from this curated set.

## Study Notes Generation (20+ Subtopics)

`POST /api/study-notes/generate`

```json
{
  "exam": "jamb",
  "year": 2025,
  "subject": "Physics",
  "topic": "Kinematics",
  "min_subtopics": 20,
  "read_time_target_minutes": 3,
  "user_email": "student@example.com"
}
```

Behavior:
- Validates exam -> subject -> topic from your syllabus tree.
- Uses Claude to generate structured study notes.
- Enforces at least 20 valid, unique subtopics.
- Persists a set in `study_note_sets` and notes in `study_notes`.

## School Exams (Post-UTME / JUPEB)

New tree:
- exam_mode (`post-utme` or `jupeb`) -> institution -> subject -> topic

Example generate payload:

```json
{
  "exam_mode": "post-utme",
  "institution_name": "University of Lagos",
  "year": 2025,
  "subject": "Physics",
  "topic": "all topics",
  "difficulty": "medium",
  "count": 20,
  "user_email": "student@example.com"
}
```

## Local Run
```bash
pip install -r requirements.txt
uvicorn run:app --reload --port 8000
```

Docs at: `http://localhost:8000/docs`

