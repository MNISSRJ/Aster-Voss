-- Additive BTS Radar expansion. Existing notices and source rows are preserved.
alter table public.bts_radar_sources
  add column if not exists provenance_url text not null default '';

alter table public.bts_radar_items
  add column if not exists member text not null default '',
  add column if not exists provenance_url text not null default '',
  add column if not exists verification_status text not null default 'verified_official';

create index if not exists bts_radar_items_member_published_idx
  on public.bts_radar_items (member, published_at desc);
