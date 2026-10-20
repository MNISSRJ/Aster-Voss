begin;
drop trigger if exists radar_events_prune_after_insert on public.radar_events;
drop function if exists public.prune_radar_events();
drop table if exists public.radar_events;
commit;
