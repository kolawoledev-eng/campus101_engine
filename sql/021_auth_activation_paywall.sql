-- Auth + activation foundation for practice paywall.
-- Free users can attempt only first 5 questions in a session.
-- Migration is idempotent and safe to re-run.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- USERS: extend existing users table for app auth profile fields
-- ---------------------------------------------------------------------------
alter table users
  add column if not exists first_name varchar(120),
  add column if not exists last_name varchar(120),
  add column if not exists phone varchar(30),
  add column if not exists password_hash text,
  add column if not exists email_verified boolean not null default false,
  add column if not exists phone_verified boolean not null default false,
  add column if not exists is_deleted boolean not null default false,
  add column if not exists deleted_at timestamptz,
  add column if not exists last_login_at timestamptz;

alter table users
  alter column email drop not null;

create unique index if not exists idx_users_phone_unique_active
  on users(phone)
  where phone is not null and is_deleted = false;

create unique index if not exists idx_users_email_unique_active
  on users(lower(email))
  where email is not null and is_deleted = false;

-- ---------------------------------------------------------------------------
-- AUTH SESSIONS: login tokens (store token hash, not raw token)
-- ---------------------------------------------------------------------------
create table if not exists auth_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  session_token_hash text not null,
  device_name varchar(160),
  platform varchar(40),
  ip_address varchar(80),
  user_agent text,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz default now()
);

create unique index if not exists idx_auth_sessions_token_hash
  on auth_sessions(session_token_hash);

create index if not exists idx_auth_sessions_user
  on auth_sessions(user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- ACTIVATION PLANS + USER ACTIVATIONS
-- ---------------------------------------------------------------------------
create table if not exists activation_plans (
  id bigserial primary key,
  code varchar(40) unique not null,
  name varchar(120) not null,
  duration_days int not null check (duration_days > 0),
  price_kobo int not null check (price_kobo >= 0),
  is_active boolean not null default true,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

insert into activation_plans (code, name, duration_days, price_kobo, is_active)
values
  ('month_1', '1 Month', 30, 150000, true),
  ('month_3', '3 Months', 90, 250000, true),
  ('year_1', '1 Year', 365, 400000, true)
on conflict (code) do update set
  name = excluded.name,
  duration_days = excluded.duration_days,
  price_kobo = excluded.price_kobo,
  is_active = excluded.is_active,
  updated_at = now();

create table if not exists user_activations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  plan_id bigint references activation_plans(id),
  status varchar(20) not null check (status in ('pending', 'active', 'expired', 'cancelled')),
  starts_at timestamptz,
  ends_at timestamptz,
  provider varchar(40),
  provider_reference varchar(200),
  activated_by varchar(20) not null default 'system' check (activated_by in ('system', 'admin', 'payment_webhook')),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_user_activations_user_status
  on user_activations(user_id, status, ends_at desc);

-- ---------------------------------------------------------------------------
-- PRACTICE ATTEMPTS: enforce free-tier question-limit server-side
-- ---------------------------------------------------------------------------
create table if not exists practice_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete set null,
  anonymous_id uuid,
  exam varchar(50) not null,
  year int not null,
  subject varchar(120) not null,
  difficulty varchar(20),
  requested_limit int not null default 40 check (requested_limit >= 1 and requested_limit <= 100),
  served_limit int not null default 5 check (served_limit >= 1 and served_limit <= 100),
  blocked_at_question int,
  is_activated_at_request boolean not null default false,
  created_at timestamptz default now()
);

create index if not exists idx_practice_attempts_user_created
  on practice_attempts(user_id, created_at desc);

create index if not exists idx_practice_attempts_anon_created
  on practice_attempts(anonymous_id, created_at desc);
