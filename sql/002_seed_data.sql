insert into exams (name, description) values
  ('JAMB', 'Joint Admissions and Matriculation Board'),
  ('WAEC', 'West African Examinations Council'),
  ('NECO', 'National Examinations Council'),
  ('IGCSE', 'International General Certificate of Secondary Education'),
  ('Cambridge', 'Cambridge Assessment International Education')
on conflict (name) do nothing;

-- JAMB subjects
insert into subjects (exam_id, name)
select e.id, x.name
from exams e
cross join (values
  ('Mathematics'), ('English'), ('Physics'), ('Chemistry'), ('Biology'), ('Computing')
) as x(name)
where e.name = 'JAMB'
on conflict (exam_id, name) do nothing;

-- WAEC subjects
insert into subjects (exam_id, name)
select e.id, x.name
from exams e
cross join (values
  ('Mathematics'), ('English Language'), ('Physics'), ('Chemistry'), ('Biology'), ('Further Mathematics')
) as x(name)
where e.name = 'WAEC'
on conflict (exam_id, name) do nothing;

-- WAEC Physics topics (2024)
insert into syllabus_topics (subject_id, topic_name, year)
select s.id, x.topic_name, 2024
from subjects s
join exams e on e.id = s.exam_id
cross join (values
  ('Kinematics'),
  ('Dynamics'),
  ('Energy and Work'),
  ('Simple Harmonic Motion'),
  ('Thermal Physics'),
  ('Light and Optics'),
  ('Electricity and Magnetism')
) as x(topic_name)
where e.name = 'WAEC' and s.name = 'Physics'
on conflict (subject_id, topic_name, year) do nothing;

-- Institutions
insert into institutions (name, short_code) values
  ('University of Lagos', 'UNILAG'),
  ('University of Ibadan', 'UI'),
  ('Obafemi Awolowo University', 'OAU'),
  ('University of Nigeria, Nsukka', 'UNN'),
  ('Ahmadu Bello University', 'ABU')
on conflict (name) do nothing;

-- Post-UTME offerings (sample for 2025)
insert into institution_exam_offerings (institution_id, exam_mode, year)
select i.id, 'post-utme', 2025
from institutions i
on conflict (institution_id, exam_mode, year) do nothing;

-- JUPEB offerings (sample for 2025)
insert into institution_exam_offerings (institution_id, exam_mode, year)
select i.id, 'jupeb', 2025
from institutions i
on conflict (institution_id, exam_mode, year) do nothing;

-- Subjects for post-utme offerings
insert into institution_subjects (offering_id, subject_name)
select o.id, s.subject_name
from institution_exam_offerings o
cross join (values
  ('English'),
  ('Mathematics'),
  ('Physics'),
  ('Chemistry'),
  ('Biology'),
  ('Government'),
  ('Economics'),
  ('General Knowledge')
) as s(subject_name)
where o.exam_mode = 'post-utme' and o.year = 2025
on conflict (offering_id, subject_name) do nothing;

-- Topics for Physics subject (post-utme)
insert into institution_topics (institution_subject_id, topic_name)
select isub.id, t.topic_name
from institution_subjects isub
join institution_exam_offerings o on o.id = isub.offering_id
cross join (values
  ('Kinematics'),
  ('Dynamics'),
  ('Waves'),
  ('Electricity'),
  ('Modern Physics')
) as t(topic_name)
where o.exam_mode = 'post-utme' and o.year = 2025 and isub.subject_name = 'Physics'
on conflict (institution_subject_id, topic_name) do nothing;

