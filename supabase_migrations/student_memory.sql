-- Episodic Memory Table
-- Stores AI-extracted facts about each student's learning patterns, struggles, and strengths.
-- Populated asynchronously by memory_worker.py after each chat turn.

create extension if not exists pg_trgm; -- BM25-style keyword search

create table if not exists student_memory (
    id              uuid        primary key default gen_random_uuid(),
    student_id      text        not null,
    fact            text        not null,          -- e.g. "Struggles with dynamic programming"
    category        text        not null,          -- weak_topic | strong_topic | learning_style | emotional | goal
    subject_code    text,                          -- optional subject context
    confidence      float       not null default 0.8,  -- 0-1 LLM confidence in this fact
    source_session  text,                          -- session_id where fact was observed
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    expires_at      timestamptz default (now() + interval '60 days')  -- auto-expire stale facts
);

-- Indexes for fast per-student retrieval + keyword search
create index if not exists idx_student_memory_student_id on student_memory(student_id);
create index if not exists idx_student_memory_category   on student_memory(category);
create index if not exists idx_student_memory_fact_trgm  on student_memory using gin(fact gin_trgm_ops);

-- Auto-update updated_at on change
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger student_memory_updated_at
    before update on student_memory
    for each row execute function set_updated_at();

-- RLS: students can only read their own memory; service role can write
alter table student_memory enable row level security;

create policy "students_read_own_memory"
    on student_memory for select
    using (auth.uid()::text = student_id);

create policy "service_write_memory"
    on student_memory for all
    using (auth.role() = 'service_role');
