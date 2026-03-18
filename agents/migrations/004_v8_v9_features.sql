-- =====================================================================
-- Migration 004: V2 Diagram Memory, V6 Session Events, V8 Behavioral
-- =====================================================================

-- V2: Persist diagrams from tutor sessions
CREATE TABLE IF NOT EXISTS tutor_session_diagrams (
    id              BIGSERIAL PRIMARY KEY,
    student_db_id   INTEGER NOT NULL,
    session_id      TEXT NOT NULL,
    subject_code    TEXT NOT NULL DEFAULT '',
    topic           TEXT NOT NULL DEFAULT '',
    step_num        INTEGER NOT NULL DEFAULT 0,
    diagram_title   TEXT NOT NULL DEFAULT '',
    mermaid_code    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tsd_session ON tutor_session_diagrams(session_id);
CREATE INDEX IF NOT EXISTS idx_tsd_student ON tutor_session_diagrams(student_db_id);

-- V6: Session replay events store
CREATE TABLE IF NOT EXISTS session_events (
    id              BIGSERIAL PRIMARY KEY,
    student_db_id   INTEGER NOT NULL,
    session_id      TEXT NOT NULL,
    event_type      TEXT NOT NULL,  -- 'step' | 'narration' | 'diagram' | 'checkpoint' | 'done'
    event_data      JSONB NOT NULL DEFAULT '{}',
    step_num        INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_se_session ON session_events(session_id);
CREATE INDEX IF NOT EXISTS idx_se_student ON session_events(student_db_id, created_at DESC);

-- V8: Attention heartbeat log (tab-focus events from frontend)
CREATE TABLE IF NOT EXISTS session_attention_log (
    id              BIGSERIAL PRIMARY KEY,
    student_db_id   INTEGER NOT NULL,
    session_id      TEXT NOT NULL DEFAULT '',
    is_visible      BOOLEAN NOT NULL DEFAULT TRUE,
    heartbeat_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sal_student ON session_attention_log(student_db_id, heartbeat_at DESC);

-- V8: Study room (peer learning)
CREATE TABLE IF NOT EXISTS study_rooms (
    id              BIGSERIAL PRIMARY KEY,
    room_code       TEXT NOT NULL UNIQUE,
    creator_id      TEXT NOT NULL,
    topic           TEXT NOT NULL DEFAULT '',
    subject_code    TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS study_room_messages (
    id              BIGSERIAL PRIMARY KEY,
    room_code       TEXT NOT NULL,
    sender_id       TEXT NOT NULL,
    sender_name     TEXT NOT NULL DEFAULT 'Student',
    message         TEXT NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_srm_room ON study_room_messages(room_code, sent_at ASC);
