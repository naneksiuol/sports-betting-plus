-- Run this in your Supabase SQL Editor (supabase.com → your project → SQL Editor)

-- Profiles table (extends Supabase auth.users)
create table if not exists public.profiles (
  id          uuid references auth.users(id) on delete cascade primary key,
  email       text not null,
  full_name   text,
  tier        text not null default 'free' check (tier in ('free', 'standard', 'premium')),
  stripe_customer_id text,
  stripe_subscription_id text,
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

-- Auto-create profile on new user signup
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer as $$
begin
  insert into public.profiles (id, email, full_name, tier)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
    'free'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- Row-level security: users can only read their own profile
alter table public.profiles enable row level security;

create policy "Users can view own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id);

-- Service role can update tier (used by Stripe webhook)
create policy "Service role full access"
  on public.profiles for all
  using (auth.role() = 'service_role');
