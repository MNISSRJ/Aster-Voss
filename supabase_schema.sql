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


-- Aster Voss daily AI radar
create table if not exists public.ai_radar_briefs (
  brief_date date not null,
  user_id text not null default 'mint',
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (brief_date, user_id)
);

create index if not exists ai_radar_briefs_user_date_idx
  on public.ai_radar_briefs (user_id, brief_date desc);

alter table public.ai_radar_briefs enable row level security;

-- Optional semantic memory foundation. This is dormant until an embedding
-- provider is configured and the vector extension is enabled.
create extension if not exists vector;

create table if not exists public.aster_memory_embeddings (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  memory_id text not null,
  content text not null,
  embedding vector(1536) not null,
  created_at timestamptz not null default now()
);

create index if not exists aster_memory_embeddings_user_idx
  on public.aster_memory_embeddings (user_id);

alter table public.aster_memory_embeddings enable row level security;

create or replace function public.match_aster_memory (
  query_embedding vector(1536),
  match_threshold float,
  match_count int,
  target_user_id text
)
returns table (
  memory_id text,
  content text,
  similarity float
)
language sql stable
as $$
  select
    memory_id,
    content,
    1 - (embedding <=> query_embedding) as similarity
  from public.aster_memory_embeddings
  where user_id = target_user_id
    and 1 - (embedding <=> query_embedding) >= match_threshold
  order by embedding <=> query_embedding
  limit match_count;
$$;
