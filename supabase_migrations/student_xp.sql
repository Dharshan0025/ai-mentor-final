-- XP Gamification Table
-- Stores cumulative XP for each student. One row per student, updated on each XP award.

create table if not exists student_xp (
    student_id  text        primary key,
    total_xp    int         not null default 0,
    level       int         not null default 1,
    updated_at  timestamptz not null default now()
);

-- Auto-compute level: every 100 XP = 1 level
create or replace function compute_xp_level(xp int) returns int language sql immutable as $$
    select greatest(1, floor(xp / 100)::int + 1);
$$;

-- Stored procedure: award XP and recompute level atomically
create or replace procedure award_xp(p_student_id text, p_xp int)
language plpgsql as $$
begin
    insert into student_xp (student_id, total_xp, level, updated_at)
    values (p_student_id, p_xp, compute_xp_level(p_xp), now())
    on conflict (student_id)
    do update set
        total_xp   = student_xp.total_xp + p_xp,
        level      = compute_xp_level(student_xp.total_xp + p_xp),
        updated_at = now();
end;
$$;

-- RLS
alter table student_xp enable row level security;

create policy "students_read_own_xp"
    on student_xp for select
    using (auth.uid()::text = student_id);

create policy "service_write_xp"
    on student_xp for all
    using (auth.role() = 'service_role');

-- Index for leaderboard (ORDER BY total_xp DESC)
create index if not exists idx_student_xp_leaderboard on student_xp(total_xp desc);
