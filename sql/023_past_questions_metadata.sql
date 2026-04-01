-- Mirror optional metadata from generated_questions on past_questions (explanations, syllabus, outcomes).
-- Past rows typically leave tokens_used / api_cost null; source_type defaults to 'past'.

alter table past_questions
  add column if not exists learning_outcomes jsonb not null default '[]'::jsonb;

alter table past_questions
  add column if not exists syllabus_alignment text;

alter table past_questions
  add column if not exists source_type varchar(20) default 'past';

alter table past_questions
  add column if not exists tokens_used int;

alter table past_questions
  add column if not exists api_cost numeric(12, 6);

update past_questions set source_type = 'past' where source_type is null;

-- Institution past MCQs: same shape for tooling consistency
alter table institution_past_questions
  add column if not exists learning_outcomes jsonb not null default '[]'::jsonb;

alter table institution_past_questions
  add column if not exists syllabus_alignment text;

alter table institution_past_questions
  add column if not exists source_type varchar(20) default 'past';

alter table institution_past_questions
  add column if not exists tokens_used int;

alter table institution_past_questions
  add column if not exists api_cost numeric(12, 6);

update institution_past_questions set source_type = 'past' where source_type is null;
