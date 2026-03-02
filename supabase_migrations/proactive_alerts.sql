-- proactive_alerts table for AI Mentor Attendance Cliff Warning
-- Run this in your Supabase SQL editor

CREATE TABLE IF NOT EXISTS proactive_alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_college_id  TEXT NOT NULL,        -- e.g. "22CSBS001"
    alert_type          TEXT NOT NULL,        -- "attendance" | "emotional" | "exam" | "assignment"
    subject_code        TEXT,                 -- NULL for non-subject alerts
    severity            TEXT NOT NULL,        -- "critical" | "warning" | "notice"
    message             TEXT NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    read_at             TIMESTAMPTZ           -- NULL = unread
);

-- Index for fast per-student unread alert lookup
CREATE INDEX IF NOT EXISTS idx_proactive_alerts_student_unread
    ON proactive_alerts(student_college_id, read_at)
    WHERE read_at IS NULL;

-- Row Level Security (recommended for Supabase)
ALTER TABLE proactive_alerts ENABLE ROW LEVEL SECURITY;
