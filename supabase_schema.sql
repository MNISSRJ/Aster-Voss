-- Aster Voss cloud brain
-- Run this once in Supabase SQL Editor.
create table if not exists public.aster_memory (
  user_id text primary key,
  memory jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.aster_memory enable row level security;

-- The current Aster backend uses the service-role key server-side.
-- Do not expose SUPABASE_SERVICE_ROLE_KEY to the browser.
