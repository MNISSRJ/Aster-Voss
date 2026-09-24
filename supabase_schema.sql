-- Aster Voss cloud brain
-- Run this once in Supabase SQL Editor.
create table if not exists public.aster_memory (
  user_id text primary key,
  memory jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.aster_memory enable row level security;

-- The current Aster backend uses a server-side Supabase key.
-- Never expose SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY to the browser.

-- Aster Voss conversation archive
create table if not exists public.aster_conversations (
  id text primary key,
  user_id text not null default 'mint',
  title text not null default '新对话',
  messages jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists aster_conversations_user_updated_idx
  on public.aster_conversations (user_id, updated_at desc);

alter table public.aster_conversations enable row level security;
