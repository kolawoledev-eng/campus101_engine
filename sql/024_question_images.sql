-- Optional diagram / figure URL for MCQs (e.g. past papers from blyr `question.image`).
-- App reads `image_url` via practice API; null = text-only question.

alter table past_questions
  add column if not exists image_url text;

alter table generated_questions
  add column if not exists image_url text;

alter table institution_past_questions
  add column if not exists image_url text;

alter table institution_generated_questions
  add column if not exists image_url text;
