-- Update activation plan pricing
-- 1 Month: 1500 NGN
-- 3 Months: 2500 NGN
-- 1 Year: 4000 NGN

update activation_plans
set price_kobo = 150000
where code = 'month_1';

update activation_plans
set price_kobo = 250000
where code = 'month_3';

update activation_plans
set price_kobo = 400000
where code = 'year_1';
