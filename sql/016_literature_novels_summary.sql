-- Recommended Novels in English: canonical novel/poetry/drama list + cached Claude summaries (generate-once).

create table if not exists literature_novels (
  id bigserial primary key,
  slug text unique not null,
  title text not null,
  author text not null,
  popularity_rank int not null,
  created_at timestamptz default now(),
  unique (popularity_rank)
);

create table if not exists novel_summaries (
  id uuid primary key default gen_random_uuid(),
  novel_id bigint not null references literature_novels(id) on delete cascade,
  sections jsonb not null,
  section_count int not null,
  total_input_tokens int,
  total_output_tokens int,
  total_cost numeric(12, 6),
  generated_by text default 'claude',
  created_at timestamptz default now(),
  unique (novel_id)
);

create index if not exists idx_literature_novels_popularity on literature_novels(popularity_rank asc);
create index if not exists idx_novel_summaries_novel on novel_summaries(novel_id);

-- popularity_rank: 1 = shown first (typical JAMB focus). Adjust with UPDATE as needed.
insert into literature_novels (slug, title, author, popularity_rank) values
  ('the-life-changer', 'The Life Changer', 'Khadija A. Jalli', 1),
  ('the-lion-and-the-jewel', 'The Lion and the Jewel', 'Wole Soyinka', 2),
  ('the-lekki-headmaster', 'The Lekki Headmaster', 'Kabir Alabi Garba', 3),
  ('look-back-in-anger', 'Look back in Anger', 'John Osborne', 4),
  ('second-class-citizen', 'Second Class Citizen', 'Buchi Emecheta', 5),
  ('unexpected-joy-at-dawn', 'Unexpected joy at dawn', 'Alex Agyei-Agyiri', 6),
  ('wuthering-heights', 'Wuthering Heights', 'Emily Bronte', 7),
  ('to-kill-a-mocking-bird', 'To Kill A Mocking Bird', 'Harper Lee', 8),
  ('a-man-for-all-seasons', 'A Man for All Seasons', 'Robert Bolt', 9),
  ('an-inspector-calls', 'An Inspector Calls', 'J. B. Priestley', 10),
  ('the-marriage-of-anansewa', 'The Marriage of Anansewa', 'Efua Sutherland', 11),
  ('once-upon-a-time', 'Once Upon a Time', 'Gabriel Okara', 12),
  ('night', 'Night', 'Wole Soyinka', 13),
  ('not-my-business', 'Not my Business', 'Niyi Osundare', 14),
  ('the-leader-and-the-led', 'The Leader and the Led', 'Niyi Osundare', 15),
  ('caged-bird', 'Caged Bird', 'Maya Angelou', 16),
  ('still-i-rise', 'Still I Rise', 'Maya Angelou', 17),
  ('she-walks-in-beauty', 'She Walks in Beauty', 'Lord Byron', 18),
  ('the-journey-of-the-magi', 'The Journey of the Magi', 'T.S. Eliot', 19),
  ('the-good-morrow', 'The Good Morrow', 'John Donne', 20),
  ('digging', 'Digging', 'Seamus Heaney', 21),
  ('the-stone', 'The Stone', 'Wilfred Wilson Gipson', 22),
  ('bats', 'Bats', 'D.H. Lawrence', 23),
  ('the-telephone-call', 'The Telephone Call', 'Fleur Adcock', 24),
  ('the-nuns-priest-tale', 'The Nuns Priest Tale', 'Geoffrey Chaucer', 25),
  ('antony-and-cleopatra', 'Antony and Cleopatra', 'William Shakespeare', 26),
  ('so-the-path-does-not-die', 'So The Path Does Not Die', 'Pede Hollist', 27),
  ('redemption-road', 'Redemption Road', 'Elma Shaw', 28),
  ('path-of-lucas-the-journey-he-endured', 'Path of Lucas: The Journey He Endured', 'Susanne Bellefeuille', 29),
  ('once-upon-an-elephant', 'Once Upon An Elephant', 'Bosede Ademilua-Afolayan', 30),
  ('new-tongue', 'New Tongue', 'Elizabeth L. A. Kamara', 31),
  ('hearty-garlands', 'Hearty Garlands', 'S. O. H. Afriyie-Vidza', 32),
  ('raider-of-the-treasure-trove', 'Raider of the Treasure Trove', 'Lade Wosornu', 33),
  ('a-government-driver-on-his-retirement', 'A Government Driver on his Retirement', 'Onu Chibuike', 34),
  ('the-song-of-the-women-of-my-land', 'The Song of the Women of my Land', 'Oumar Farouk Sesay', 35),
  ('the-grieved-lands', 'The Grieved Lands', 'Agostinho Neto', 36),
  ('black-woman', 'Black Woman', 'Leopold Sedar Senghor', 37),
  ('the-breast-of-the-sea', 'The Breast of The Sea', 'Syl Cheney-Coker', 38)
on conflict (slug) do nothing;
