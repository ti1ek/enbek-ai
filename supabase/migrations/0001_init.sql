-- Расширение для UUID
create extension if not exists "uuid-ossp";

-- Дополнительные поля пользователей (расширяет auth.users)
create table if not exists public.users_extra (
    id          uuid primary key references auth.users(id) on delete cascade,
    full_name   text,
    organization text,
    tier        text not null default 'free',  -- free | pro | team
    daily_limit integer not null default 10,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

alter table public.users_extra enable row level security;

create policy "Users see own profile"
    on public.users_extra for select
    using (auth.uid() = id);

create policy "Users update own profile"
    on public.users_extra for update
    using (auth.uid() = id);

-- Автоматически создаём запись при регистрации
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer as $$
begin
    insert into public.users_extra (id, full_name)
    values (new.id, new.raw_user_meta_data->>'full_name');
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute procedure public.handle_new_user();

-- Лог запросов (счётчик + аналитика)
create table if not exists public.queries_log (
    id              uuid primary key default uuid_generate_v4(),
    user_id         uuid not null references auth.users(id) on delete cascade,
    query_text      text not null,
    response_text   text,
    sources_json    jsonb default '[]',
    pipeline        text default 'advanced',  -- basic | advanced
    latency_ms      integer,
    cost_usd        numeric(10, 6),
    created_at      timestamptz not null default now()
);

alter table public.queries_log enable row level security;

create policy "Users see own queries"
    on public.queries_log for select
    using (auth.uid() = user_id);

create policy "Users insert own queries"
    on public.queries_log for insert
    with check (auth.uid() = user_id);

create index on public.queries_log (user_id, created_at desc);

-- Загруженные документы
create table if not exists public.documents (
    id                  uuid primary key default uuid_generate_v4(),
    user_id             uuid not null references auth.users(id) on delete cascade,
    filename            text not null,
    storage_path        text not null,
    mime_type           text,
    size_bytes          integer,
    llamaparse_result   text,
    status              text not null default 'pending',  -- pending | parsed | error
    created_at          timestamptz not null default now()
);

alter table public.documents enable row level security;

create policy "Users see own documents"
    on public.documents for select
    using (auth.uid() = user_id);

create policy "Users insert own documents"
    on public.documents for insert
    with check (auth.uid() = user_id);

create policy "Users update own documents"
    on public.documents for update
    using (auth.uid() = user_id);

-- Функция: счётчик запросов пользователя за сегодня
create or replace function public.queries_today(p_user_id uuid)
returns integer language sql stable security definer as $$
    select count(*)::integer
    from public.queries_log
    where user_id = p_user_id
      and created_at >= current_date;
$$;
