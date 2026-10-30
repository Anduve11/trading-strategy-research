-- Run once in Supabase SQL Editor. The Streamlit server uses the service-role
-- key stored in Streamlit Secrets; never expose that key in browser code.
create table if not exists public.odds_snapshots (
    snapshot_key text primary key,
    sport text not null,
    event_id text not null,
    game_date timestamptz,
    home_team text not null,
    away_team text not null,
    bookmaker text not null,
    market text not null,
    outcome text not null,
    point numeric,
    price numeric,
    provider_updated_at timestamptz,
    snapshot_time timestamptz not null,
    is_pool_lock boolean not null default false,
    inserted_at timestamptz not null default now()
);

create index if not exists odds_snapshots_sport_date_idx
    on public.odds_snapshots (sport, game_date);

create index if not exists odds_snapshots_event_time_idx
    on public.odds_snapshots (event_id, snapshot_time);

alter table public.odds_snapshots enable row level security;
