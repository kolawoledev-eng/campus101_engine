create extension if not exists pgcrypto;

create table if not exists exams (
  id bigserial primary key,
  name varchar(100) unique not null,
  description text,
  created_at timestamptz default now()
);

create table if not exists subjects (
  id bigserial primary key,
  exam_id bigint not null references exams(id) on delete cascade,
  name varchar(100) not null,
  created_at timestamptz default now(),
  unique(exam_id, name)
);

create table if not exists syllabus_topics (
  id bigserial primary key,
  subject_id bigint not null references subjects(id) on delete cascade,
  topic_name varchar(200) not null,
  year int not null,
  created_at timestamptz default now(),
  unique(subject_id, topic_name, year)
);

create table if not exists generated_questions (
  id uuid primary key default gen_random_uuid(),
  exam varchar(50) not null,
  year int not null,
  subject varchar(100) not null,
  difficulty varchar(20) not null check (difficulty in ('easy', 'medium', 'hard')),
  topic varchar(200) not null,
  question_number int not null,
  question_text text not null,
  option_a text not null,
  option_b text not null,
  option_c text not null,
  option_d text not null,
  correct_answer varchar(1) not null check (correct_answer in ('A', 'B', 'C', 'D')),
  explanation text not null,
  learning_outcomes jsonb default '[]'::jsonb,
  syllabus_alignment text,
  tokens_used int,
  api_cost numeric(12, 6),
  generated_at timestamptz default now(),
  created_at timestamptz default now()
);

create index if not exists idx_generated_questions_exam_year on generated_questions(exam, year);
create index if not exists idx_generated_questions_subject_difficulty on generated_questions(subject, difficulty);
create index if not exists idx_generated_questions_topic on generated_questions(topic);
create index if not exists idx_generated_questions_generated_at on generated_questions(generated_at desc);

create table if not exists question_sets (
  id uuid primary key default gen_random_uuid(),
  exam varchar(50) not null,
  year int not null,
  subject varchar(100) not null,
  difficulty varchar(20) not null,
  topic varchar(200) not null,
  question_count int not null,
  total_tokens_used int,
  total_cost numeric(12, 6),
  generation_time_seconds numeric(10, 2),
  generated_by varchar(255),
  created_at timestamptz default now()
);

create table if not exists question_set_items (
  id bigserial primary key,
  question_set_id uuid not null references question_sets(id) on delete cascade,
  question_id uuid not null references generated_questions(id) on delete cascade,
  sequence_number int not null,
  created_at timestamptz default now(),
  unique(question_set_id, question_id)
);

create table if not exists generation_history (
  id bigserial primary key,
  exam varchar(50) not null,
  year int not null,
  subject varchar(100) not null,
  difficulty varchar(20) not null,
  topic varchar(200) not null,
  count_requested int not null,
  count_generated int not null,
  count_failed int default 0,
  api_calls int default 0,
  total_tokens int default 0,
  total_cost numeric(12, 6) default 0,
  generation_time_seconds numeric(10, 2),
  status varchar(20),
  error_message text,
  generated_by varchar(255),
  created_at timestamptz default now()
);

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email varchar(255) unique not null,
  full_name varchar(255),
  total_questions_generated int default 0,
  total_api_cost numeric(15, 6) default 0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists user_generation_quota (
  id bigserial primary key,
  user_id uuid not null references users(id) on delete cascade,
  month int not null,
  year int not null,
  questions_generated int default 0,
  api_cost_accumulated numeric(15, 6) default 0,
  created_at timestamptz default now(),
  unique(user_id, month, year)
);

create table if not exists study_note_sets (
  id uuid primary key default gen_random_uuid(),
  exam varchar(50) not null,
  year int not null,
  subject varchar(100) not null,
  topic varchar(200) not null,
  min_subtopics int not null default 20,
  generated_by varchar(255),
  source_url text,
  read_time_target_minutes int not null default 3,
  total_subtopics int not null default 0,
  total_tokens_used int,
  total_cost numeric(12, 6),
  status varchar(20) default 'success',
  created_at timestamptz default now()
);

create table if not exists study_notes (
  id uuid primary key default gen_random_uuid(),
  note_set_id uuid not null references study_note_sets(id) on delete cascade,
  exam varchar(50) not null,
  year int not null,
  subject varchar(100) not null,
  topic varchar(200) not null,
  subtopic varchar(200) not null,
  sequence_number int not null,
  title varchar(255) not null,
  summary_text text not null,
  key_points jsonb default '[]'::jsonb,
  examiner_focus text,
  common_mistakes jsonb default '[]'::jsonb,
  memory_hook text,
  quick_recap text,
  read_time_minutes numeric(5, 2),
  syllabus_alignment text,
  created_at timestamptz default now(),
  unique(note_set_id, sequence_number),
  unique(note_set_id, subtopic)
);

create index if not exists idx_study_notes_exam_year_subject on study_notes(exam, year, subject);
create index if not exists idx_study_notes_topic on study_notes(topic);
create index if not exists idx_study_notes_created_at on study_notes(created_at desc);

create table if not exists institutions (
  id bigserial primary key,
  name varchar(200) unique not null,
  short_code varchar(50) unique,
  country varchar(100) default 'Nigeria',
  created_at timestamptz default now()
);

create table if not exists institution_exam_offerings (
  id bigserial primary key,
  institution_id bigint not null references institutions(id) on delete cascade,
  exam_mode varchar(20) not null check (exam_mode in ('post-utme', 'jupeb')),
  year int not null,
  active boolean default true,
  created_at timestamptz default now(),
  unique(institution_id, exam_mode, year)
);

create table if not exists institution_subjects (
  id bigserial primary key,
  offering_id bigint not null references institution_exam_offerings(id) on delete cascade,
  subject_name varchar(120) not null,
  created_at timestamptz default now(),
  unique(offering_id, subject_name)
);

create table if not exists institution_topics (
  id bigserial primary key,
  institution_subject_id bigint not null references institution_subjects(id) on delete cascade,
  topic_name varchar(200) not null,
  created_at timestamptz default now(),
  unique(institution_subject_id, topic_name)
);

create table if not exists institution_question_sets (
  id uuid primary key default gen_random_uuid(),
  exam_mode varchar(20) not null check (exam_mode in ('post-utme', 'jupeb')),
  institution_name varchar(200) not null,
  year int not null,
  subject varchar(120) not null,
  topic varchar(200) not null,
  difficulty varchar(20) not null,
  question_count int not null,
  total_tokens_used int,
  total_cost numeric(12, 6),
  generated_by varchar(255),
  created_at timestamptz default now()
);

create table if not exists institution_generated_questions (
  id uuid primary key default gen_random_uuid(),
  question_set_id uuid not null references institution_question_sets(id) on delete cascade,
  exam_mode varchar(20) not null check (exam_mode in ('post-utme', 'jupeb')),
  institution_name varchar(200) not null,
  year int not null,
  subject varchar(120) not null,
  topic varchar(200) not null,
  difficulty varchar(20) not null,
  question_number int not null,
  question_text text not null,
  option_a text not null,
  option_b text not null,
  option_c text not null,
  option_d text not null,
  correct_answer varchar(1) not null check (correct_answer in ('A', 'B', 'C', 'D')),
  explanation text not null,
  learning_outcomes jsonb default '[]'::jsonb,
  created_at timestamptz default now()
);

create index if not exists idx_inst_questions_lookup
  on institution_generated_questions(exam_mode, institution_name, year, subject, topic);
