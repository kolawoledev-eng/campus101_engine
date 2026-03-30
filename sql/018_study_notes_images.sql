-- Optional Wikimedia Commons illustrations per study-note card (JSON array of {url, caption}).
alter table study_notes
  add column if not exists images jsonb not null default '[]'::jsonb;
