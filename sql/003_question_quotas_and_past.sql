-- Past papers (national exams: WAEC, JAMB, etc.) — counts toward same quota as generated_questions
create table if not exists past_questions (
  id uuid primary key default gen_random_uuid(),
  exam varchar(50) not null,
  year int not null,
  subject varchar(100) not null,
  difficulty varchar(20) not null check (difficulty in ('easy', 'medium', 'hard')),
  topic varchar(200) not null,
  question_text text not null,
  option_a text not null,
  option_b text not null,
  option_c text not null,
  option_d text not null,
  correct_answer varchar(1) not null check (correct_answer in ('A', 'B', 'C', 'D')),
  explanation text,
  source_label text,
  created_at timestamptz default now()
);

create index if not exists idx_past_questions_scope
  on past_questions(exam, year, subject, topic, difficulty);

alter table generated_questions
  add column if not exists source_type varchar(20) default 'generated';

-- Institution exams: past + generated share quota
create table if not exists institution_past_questions (
  id uuid primary key default gen_random_uuid(),
  exam_mode varchar(20) not null check (exam_mode in ('post-utme', 'jupeb')),
  institution_name varchar(200) not null,
  year int not null,
  subject varchar(120) not null,
  difficulty varchar(20) not null check (difficulty in ('easy', 'medium', 'hard')),
  topic varchar(200) not null,
  question_text text not null,
  option_a text not null,
  option_b text not null,
  option_c text not null,
  option_d text not null,
  correct_answer varchar(1) not null check (correct_answer in ('A', 'B', 'C', 'D')),
  explanation text,
  source_label text,
  created_at timestamptz default now()
);

create index if not exists idx_inst_past_scope
  on institution_past_questions(exam_mode, institution_name, year, subject, topic, difficulty);

alter table institution_generated_questions
  add column if not exists source_type varchar(20) default 'generated';
