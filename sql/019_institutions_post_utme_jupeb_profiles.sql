-- Post-UTME / JUPEB: rich institution profiles + expand university list (data from DB).
-- Re-run safe: ON CONFLICT upserts metadata; offerings/subjects idempotent.

alter table institutions
  add column if not exists city varchar(120),
  add column if not exists state varchar(80),
  add column if not exists established_year int,
  add column if not exists description text,
  add column if not exists institution_type varchar(20) default 'public',
  add column if not exists display_rank int default 500;

alter table institutions drop constraint if exists institutions_institution_type_check;
alter table institutions
  add constraint institutions_institution_type_check
  check (institution_type in ('public', 'private'));

-- ---------------------------------------------------------------------------
-- Upsert institutions (canonical names = API / app keys)
-- display_rank: lower = listed first (public flagship block, then others, then private)
-- ---------------------------------------------------------------------------
insert into institutions (name, short_code, city, state, established_year, description, institution_type, display_rank)
values
  (
    'University of Ibadan',
    'UI',
    'Ibadan',
    'Oyo State',
    1948,
    'Nigeria''s oldest and consistently top-ranked university; strong in medicine, humanities, and social sciences.',
    'public',
    10
  ),
  (
    'University of Lagos',
    'UNILAG',
    'Lagos',
    'Lagos State',
    1962,
    'Top for law, business, and engineering; strong industry connections.',
    'public',
    20
  ),
  (
    'University of Nigeria, Nsukka',
    'UNN',
    'Nsukka',
    'Enugu State',
    1960,
    'Strong research output and broad programmes across faculties.',
    'public',
    30
  ),
  (
    'Obafemi Awolowo University',
    'OAU',
    'Ile-Ife',
    'Osun State',
    1961,
    'Renowned for architecture, law, and agriculture.',
    'public',
    40
  ),
  (
    'Ahmadu Bello University',
    'ABU',
    'Zaria',
    'Kaduna State',
    1962,
    'One of Nigeria''s largest universities; strong in agriculture, engineering, and veterinary medicine.',
    'public',
    50
  ),
  (
    'University of Benin',
    'UNIBEN',
    'Benin City',
    'Edo State',
    1970,
    'Strong in medicine, law, and engineering.',
    'public',
    60
  ),
  (
    'University of Ilorin',
    'UNILORIN',
    'Ilorin',
    'Kwara State',
    1975,
    'Broad programmes with a large student community.',
    'public',
    70
  ),
  (
    'Bayero University Kano',
    'BUK',
    'Kano',
    'Kano State',
    1975,
    'Leading federal university in Northern Nigeria.',
    'public',
    80
  ),
  (
    'Federal University of Technology, Akure',
    'FUTA',
    'Akure',
    'Ondo State',
    1981,
    'Top STEM-focused federal university of technology.',
    'public',
    90
  ),
  (
    'Covenant University',
    'CU',
    'Ota',
    'Ogun State',
    2002,
    'Strong in engineering, IT, and management; frequently highly ranked nationally.',
    'private',
    200
  ),
  (
    'Landmark University',
    'LMU',
    'Omu-Aran',
    'Kwara State',
    null,
    'Private university with strong research quality focus.',
    'private',
    210
  ),
  (
    'American University of Nigeria',
    'AUN',
    'Yola',
    'Adamawa State',
    null,
    'American-style liberal arts and professional programmes.',
    'private',
    220
  ),
  (
    'Pan-Atlantic University',
    'PAU',
    'Lagos',
    'Lagos State',
    null,
    'Strong business and professional programmes.',
    'private',
    230
  ),
  (
    'Afe Babalola University',
    'ABUAD',
    'Ado-Ekiti',
    'Ekiti State',
    null,
    'Private university with broad undergraduate and professional offerings.',
    'private',
    240
  ),
  (
    'Bowen University',
    'BOWEN',
    'Iwo',
    'Osun State',
    null,
    'Private faith-based university with diverse programmes.',
    'private',
    250
  )
on conflict (name) do update set
  short_code = excluded.short_code,
  city = excluded.city,
  state = excluded.state,
  established_year = excluded.established_year,
  description = excluded.description,
  institution_type = excluded.institution_type,
  display_rank = excluded.display_rank;

-- Every institution row: active Post-UTME + JUPEB offerings for 2025
insert into institution_exam_offerings (institution_id, exam_mode, year, active)
select i.id, m.exam_mode, 2025, true
from institutions i
cross join (values ('post-utme'::varchar(20)), ('jupeb'::varchar(20))) as m(exam_mode)
on conflict (institution_id, exam_mode, year) do update set active = excluded.active;

-- Same subject catalog as 006_subject_catalog_expansion.sql (idempotent per offering)
insert into institution_subjects (offering_id, subject_name)
select o.id, s.subject_name
from institution_exam_offerings o
cross join (values
  ('Use of English'),
  ('English'),
  ('Mathematics'),
  ('Physics'),
  ('Chemistry'),
  ('Biology'),
  ('Government'),
  ('Economics'),
  ('Commerce'),
  ('Principles of Accounts'),
  ('Literature in English'),
  ('Christian Religious Knowledge'),
  ('Islamic Religious Studies'),
  ('Geography'),
  ('History'),
  ('Computer Studies'),
  ('Agricultural Science'),
  ('Civic Education'),
  ('Current Affairs'),
  ('General Knowledge')
) as s(subject_name)
where o.exam_mode = 'post-utme' and o.year = 2025
on conflict (offering_id, subject_name) do nothing;

insert into institution_subjects (offering_id, subject_name)
select o.id, s.subject_name
from institution_exam_offerings o
cross join (values
  ('Mathematics'),
  ('Physics'),
  ('Chemistry'),
  ('Biology'),
  ('Agricultural Science'),
  ('Economics'),
  ('Government'),
  ('Geography'),
  ('Accounting'),
  ('Business Studies'),
  ('Christian Religious Studies'),
  ('Islamic Religious Studies'),
  ('Literature in English'),
  ('French'),
  ('History'),
  ('Igbo'),
  ('Yoruba'),
  ('Music'),
  ('Visual Arts')
) as s(subject_name)
where o.exam_mode = 'jupeb' and o.year = 2025
on conflict (offering_id, subject_name) do nothing;

-- New institution_subject rows need topic seeds. Re-run once:
--   psql ... -f engine/sql/012_post_utme_jupeb_institution_topics.sql
