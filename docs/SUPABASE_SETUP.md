# Supabase Setup

## 1. Create project
- Create a project on Supabase.
- Copy `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`.

## 2. Environment variables
Create `.env` in project root:

```env
ANTHROPIC_API_KEY=your_key
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...
```

## 3. Run SQL scripts
In SQL editor:
1. Run `sql/001_schema.sql`
2. Run `sql/002_seed_data.sql`

## 4. Install dependencies
```bash
pip install -r requirements.txt
```

## 5. Start API
```bash
uvicorn run:app --reload --port 8000
```

