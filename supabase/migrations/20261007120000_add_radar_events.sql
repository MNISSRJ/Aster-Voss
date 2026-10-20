begin;

create table if not exists public.radar_events (
  id bigint generated always as identity primary key,
  user_id text not null,
  item_id text not null,
  event_type text not null check (event_type in ('item_view','item_click','item_favorite','item_dislike','ask_aster','open_original')),
  created_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  retention_days integer not null default 90 check (retention_days between 1 and 3650)
);

create index if not exists radar_events_user_created_idx
  on public.radar_events (user_id, created_at desc);
create index if not exists radar_events_item_created_idx
  on public.radar_events (item_id, created_at desc);
alter table public.radar_events enable row level security;

create or replace function public.prune_radar_events()
returns trigger language plpgsql as $$
begin
  delete from public.radar_events
  where created_at < now() - make_interval(days => retention_days);
  return new;
end;
$$;

drop trigger if exists radar_events_prune_after_insert on public.radar_events;
create trigger radar_events_prune_after_insert
after insert on public.radar_events
for each row execute function public.prune_radar_events();

commit;
