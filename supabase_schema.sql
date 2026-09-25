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
    e.memory_id,
    e.content,
    1 - (e.embedding <=> query_embedding) as similarity
  from public.aster_memory_embeddings as e
  where e.user_id = target_user_id
    and 1 - (e.embedding <=> query_embedding) >= match_threshold
  order by e.embedding <=> query_embedding
  limit match_count;
$$;


-- Aster Voss usage events
create table if not exists public.aster_usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  conversation_id text,
  provider text not null,
  model text not null,
  prompt_tokens integer not null default 0,
  completion_tokens integer not null default 0,
  total_tokens integer not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists aster_usage_events_user_date_idx
  on public.aster_usage_events (user_id, created_at desc);

alter table public.aster_usage_events enable row level security;


-- Aster Voss request rate limiting.
-- This is required for durable rate limits in serverless/Vercel.
create table if not exists public.aster_rate_limit_windows (
  key text not null,
  window_start timestamptz not null,
  count integer not null default 0,
  updated_at timestamptz not null default now(),
  primary key (key, window_start)
);

create index if not exists aster_rate_limit_windows_updated_idx
  on public.aster_rate_limit_windows (updated_at desc);

alter table public.aster_rate_limit_windows enable row level security;

create or replace function public.consume_aster_rate_limit (
  p_key text,
  p_window_seconds integer,
  p_limit integer
)
returns table (
  allowed boolean,
  count integer,
  window_start timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_window_start timestamptz;
  v_count integer;
begin
  if p_window_seconds < 1 or p_limit < 1 then
    raise exception 'invalid rate limit parameters';
  end if;

  v_window_start := to_timestamp(
    floor(extract(epoch from clock_timestamp()) / p_window_seconds)
    * p_window_seconds
  );

  insert into public.aster_rate_limit_windows(key, window_start, count, updated_at)
  values (p_key, v_window_start, 1, now())
  on conflict (key, window_start)
  do update set
    count = public.aster_rate_limit_windows.count + 1,
    updated_at = now()
  returning public.aster_rate_limit_windows.count
  into v_count;

  delete from public.aster_rate_limit_windows
  where key = p_key
    and window_start < v_window_start - make_interval(
      secs => greatest(p_window_seconds * 2, 60)
    );

  return query
    select (v_count <= p_limit), v_count, v_window_start;
end;
$$;

revoke all on function public.consume_aster_rate_limit(text, integer, integer) from public, anon, authenticated;
grant execute on function public.consume_aster_rate_limit(text, integer, integer) to service_role;
