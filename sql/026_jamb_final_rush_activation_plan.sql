-- JAMB FINAL RUSH activation plan (2 weeks)
-- This plan is used for the “immediate launch” offer.

-- Create/Upsert plan and disable the others.
insert into activation_plans (code, name, duration_days, price_kobo, is_active)
values
  (
    'jamb_final_rush_2w',
    'JAMB FINAL RUSH (2 Weeks) – ₦1,000',
    14,
    100000,
    true
  )
on conflict (code) do update set
  name = excluded.name,
  duration_days = excluded.duration_days,
  price_kobo = excluded.price_kobo,
  is_active = excluded.is_active;

-- Optional: ensure “only this plan” behavior immediately.
update activation_plans
set is_active = false
where code in ('month_1', 'month_3', 'year_1');

