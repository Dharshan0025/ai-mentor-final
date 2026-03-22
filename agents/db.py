"""
AI-Mentor — Database Service
Async connection pool to Supabase (PostgreSQL).
Use this module for all DB queries in agents and the FastAPI app.

Usage:
    from db import db
    student = await db.get_student_by_college_id("22CSBS001")
"""
import asyncio
import asyncpg
import logging
from datetime import datetime
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

# ── Connection Pool (singleton) ───────────────────────────────────────────────
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=2,
                max_size=5,
                command_timeout=30,
                ssl="require",             # Supabase requires SSL
            )
            logger.info("✅ Supabase database pool established")
        except Exception as e:
            logger.error(f"❌ DB pool creation failed: {e}")
            raise
    return _pool


async def close_pool():
    """Gracefully close the pool on app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("DB pool closed")


# ── Student Queries ───────────────────────────────────────────────────────────

class Database:
    """All database queries for the AI-Mentor system."""

    async def _fetch_from_pool(self, query: str, *args) -> list[asyncpg.Record]:
        """Helper to fetch data using a new connection from the pool."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _fetchrow_from_pool(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Helper to fetch a single row using a new connection from the pool."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def get_student_by_college_id(self, college_id: str) -> Optional[dict]:
        """Fetch full student profile by college ID (e.g. '22CSBS001')."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Fetch initial student data
            row = await conn.fetchrow(
                """
                SELECT s.id, s.name, s.email, s.dept, s.current_semester,
                       s.cgpa, s.college_id, s.year, s.college,
                       s.attendance_overall, s.exam_days, s.study_streak,
                       s.lang_pref, s.predicted_cgpa, s.arrear_count,
                       s.parent_name, s.parent_phone, s.dob, s.gender,
                       s.category, s.admission_year, s.total_credits_earned,
                       s.total_credits_required, s.phone
                FROM students s
                WHERE s.college_id = $1
                """,
                college_id,
            )
            if not row:
                return None

            student = dict(row)
            sid = student["id"]
            sem = student["current_semester"]

            # ── Sequential data fetch to respect Supabase Session Mode limits ──
            # 1. CGPA history
            cgpa_rows = await conn.fetch("SELECT semester, cgpa FROM cgpa_history WHERE student_id=$1 ORDER BY semester", sid)
            # 2. Current semester subjects
            subj_rows = await conn.fetch(
                "SELECT code, name, grade, attendance, credit_weight, bloom_level, predicted, status "
                "FROM subject_profiles WHERE student_id=$1 AND semester=$2 ORDER BY status DESC, grade ASC",
                sid, sem
            )
            # 3. Arrear history
            arrear_rows = await conn.fetch(
                "SELECT subject_code, subject_name, semester_failed, cleared, cleared_at, cleared_grade, attempt_number "
                "FROM arrear_history WHERE student_id=$1 ORDER BY semester_failed DESC",
                sid
            )
            # 4. Assignments
            assign_rows = await conn.fetch(
                "SELECT subject_code, title, type, max_marks, scored_marks, due_date, submitted_date, submission_status "
                "FROM assignments WHERE student_id=$1 AND semester=$2 ORDER BY due_date DESC",
                sid, sem
            )
            # 5. Activities
            activity_rows = await conn.fetch(
                "SELECT activity_type, title, organizer, level, domain, grade_or_score, verified, end_date "
                "FROM activities WHERE student_id=$1 ORDER BY end_date DESC LIMIT 15",
                sid
            )
            # 6. Placement records
            placement_rows = await conn.fetch(
                "SELECT company_name, role, package_lpa, status, drive_date, placement_type "
                "FROM placement_records WHERE student_id=$1 ORDER BY drive_date DESC",
                sid
            )
            # 7. Syllabus coverage
            syllabus_rows = await conn.fetch(
                "SELECT subject_code, subject_name, unit_number, unit_title, coverage_pct, total_topics, covered_topics "
                "FROM syllabus_coverage WHERE semester=$1 ORDER BY subject_code, unit_number",
                sem
            )
            # 8. Attendance summary
            att_summary = await conn.fetch(
                "SELECT subject_code, COUNT(*) AS total_classes, "
                "SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS attended, "
                "ROUND(100.0 * SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 1) AS live_pct "
                "FROM attendance_records WHERE student_id=$1 GROUP BY subject_code",
                sid
            )
            # 9. Library
            library_rows = await conn.fetch(
                "SELECT book_title, book_author, due_date, return_date, fine_amount, fine_paid, status "
                "FROM library_records WHERE student_id=$1 ORDER BY due_date DESC LIMIT 5",
                sid
            )
            # 10. Historical subjects
            hist_subj_rows = await conn.fetch(
                "SELECT semester, code, name, grade, attendance, credit_weight, bloom_level, status "
                "FROM subject_profiles WHERE student_id=$1 AND semester < $2 ORDER BY semester DESC, grade ASC",
                sid, sem
            )
            # 11. Next semester subjects
            next_sem_rows = await conn.fetch(
                "SELECT dc.subject_code, dc.subject_title, dc.credits, dc.subject_type, dc.elective_vertical "
                "FROM department_curriculum dc WHERE dc.semester = $1 ORDER BY dc.subject_type, dc.subject_code",
                sem + 1
            )
            # 12. Fee records
            fee_rows = await conn.fetch(
                "SELECT fee_type, amount_due, amount_paid, status, semester FROM fee_records WHERE student_id=$1 ORDER BY semester DESC",
                sid
            )
            # 13. Mentoring sessions
            mentor_rows = await conn.fetch(
                "SELECT faculty_mentor, session_date, agenda, notes, action_items, parent_present "
                "FROM mentoring_sessions WHERE student_id=$1 ORDER BY session_date DESC LIMIT 5",
                sid
            )
            # 14. Placement eligibility
            eligibility_rows = await conn.fetch(
                "SELECT cgpa_eligible, arrear_free, attendance_ok, cgpa_threshold, is_eligible FROM placement_eligibility WHERE student_id=$1",
                sid
            )

        student["cgpa_history"]     = [dict(r) for r in cgpa_rows]
        student["subjects"]         = [dict(r) for r in subj_rows]
        student["arrears"]          = [dict(r) for r in arrear_rows]
        student["assignments"]      = [dict(r) for r in assign_rows]
        student["activities"]       = [dict(r) for r in activity_rows]
        student["placement"]        = [dict(r) for r in placement_rows]
        student["syllabus_coverage"]= [dict(r) for r in syllabus_rows]
        student["attendance_detail"]= {r["subject_code"]: dict(r) for r in att_summary}
        student["library"]          = [dict(r) for r in library_rows]
        student["historical_subjects"] = [dict(r) for r in hist_subj_rows]
        student["next_sem_subjects"]   = [dict(r) for r in next_sem_rows]
        student["fee_records"]         = [dict(r) for r in fee_rows]
        student["mentoring"]           = [dict(r) for r in mentor_rows]
        student["placement_eligibility"] = dict(eligibility_rows[0]) if eligibility_rows else None

        return self._normalize_profile(student)

    # ── Learning DNA ────────────────────────────────────────────────────────────

    async def get_learning_dna(self, student_college_id: str) -> dict:
        """
        Fetch the student's Learning DNA row, auto-creating a default profile
        if it does not exist yet.
        """
        row = await self._fetchrow_from_pool(
            """
            SELECT id,
                   student_college_id,
                   preferred_style,
                   weak_topics,
                   strong_topics,
                   quiz_history,
                   total_questions,
                   total_quizzes,
                   correct_answers,
                   peak_hour,
                   updated_at
            FROM student_learning_dna
            WHERE student_college_id = $1
            """,
            student_college_id,
        )

        if not row:
            # Create a default Learning DNA profile
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO student_learning_dna (student_college_id)
                    VALUES ($1)
                    RETURNING id,
                              student_college_id,
                              preferred_style,
                              weak_topics,
                              strong_topics,
                              quiz_history,
                              total_questions,
                              total_quizzes,
                              correct_answers,
                              peak_hour,
                              updated_at
                    """,
                    student_college_id,
                )

        return dict(row)

    async def update_learning_dna(
        self,
        student_college_id: str,
        *,
        preferred_style: str | None = None,
        weak_topics_append: list[dict] | None = None,
        strong_topics_append: list[dict] | None = None,
        quiz_history_entry: dict | None = None,
        questions_delta: int = 0,
        quizzes_delta: int = 0,
        correct_delta: int = 0,
        peak_hour_observation: int | None = None,
    ) -> dict:
        """
        Update the student's Learning DNA in a single helper.
        - Appends to weak/strong topic arrays and quiz_history.
        - Increments aggregate counters.
        - Optionally nudges peak_hour based on a new observation.
        Returns the updated row as a dict.
        """
        current = await self.get_learning_dna(student_college_id)

        import json
        
        def _parse_json_list(val):
            if not val:
                return []
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return []
            if isinstance(val, list):
                return list(val)
            return []

        weak_topics = _parse_json_list(current.get("weak_topics"))
        strong_topics = _parse_json_list(current.get("strong_topics"))
        quiz_history = _parse_json_list(current.get("quiz_history"))

        if weak_topics_append:
            weak_topics.extend(weak_topics_append)
        if strong_topics_append:
            strong_topics.extend(strong_topics_append)
        if quiz_history_entry:
            quiz_history.append(quiz_history_entry)

        total_questions = int(current.get("total_questions") or 0) + questions_delta
        total_quizzes = int(current.get("total_quizzes") or 0) + quizzes_delta
        correct_answers = int(current.get("correct_answers") or 0) + correct_delta

        peak_hour = current.get("peak_hour")
        if peak_hour_observation is not None:
            # Simple heuristic: if peak_hour is not set, adopt the first observation.
            # More advanced smoothing can be added later.
            if peak_hour is None:
                peak_hour = peak_hour_observation

        new_preferred_style = preferred_style or current.get("preferred_style")

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE student_learning_dna
                SET preferred_style = COALESCE($2, preferred_style),
                    weak_topics     = $3,
                    strong_topics   = $4,
                    quiz_history    = $5,
                    total_questions = $6,
                    total_quizzes   = $7,
                    correct_answers = $8,
                    peak_hour       = COALESCE($9, peak_hour),
                    updated_at      = NOW()
                WHERE student_college_id = $1
                RETURNING id,
                          student_college_id,
                          preferred_style,
                          weak_topics,
                          strong_topics,
                          quiz_history,
                          total_questions,
                          total_quizzes,
                          correct_answers,
                          peak_hour,
                          updated_at
                """,
                student_college_id,
                new_preferred_style,
                json.dumps(weak_topics),
                json.dumps(strong_topics),
                json.dumps(quiz_history),
                total_questions,
                total_quizzes,
                correct_answers,
                peak_hour,
            )

        return dict(row)

    def _normalize_profile(self, raw: dict) -> dict:
        """Convert DB row to the format expected by agents and frontend."""
        att_detail = raw.get("attendance_detail", {})

        # ── Current semester subjects ─────────────────────────────────
        subjects = []
        for s in raw.get("subjects", []):
            code = s.get("code", "")
            live = att_detail.get(code, {})
            subjects.append({
                "code":            code,
                "name":            s.get("name"),
                "grade":           float(s.get("grade") or 0),
                "attendance":      s.get("attendance"),
                "live_attendance": float(live.get("live_pct") or s.get("attendance") or 0),
                "total_classes":   int(live.get("total_classes") or 0),
                "attended":        int(live.get("attended") or 0),
                "creditWeight":    s.get("credit_weight", 3),
                "bloomLevel":      s.get("bloom_level", 1),
                "predicted":       float(s.get("predicted") or 0),
                "status":          s.get("status", "safe"),
            })

        # ── Historical subjects grouped by semester ───────────────────
        hist_by_sem: dict = {}
        for s in raw.get("historical_subjects", []):
            sem_key = str(s.get("semester"))
            if sem_key not in hist_by_sem:
                hist_by_sem[sem_key] = []
            hist_by_sem[sem_key].append({
                "code":        s.get("code"),
                "name":        s.get("name"),
                "grade":       float(s.get("grade") or 0),
                "attendance":  s.get("attendance"),
                "creditWeight": s.get("credit_weight", 3),
                "bloomLevel":  s.get("bloom_level", 1),
                "status":      s.get("status", "safe"),
            })

        # ── Next semester subjects ────────────────────────────────────
        next_sem_subjects = [
            {
                "code":    r.get("subject_code"),
                "name":    r.get("subject_title"),
                "credits": r.get("credits"),
                "type":    r.get("subject_type"),
                "elective_vertical": r.get("elective_vertical"),
            }
            for r in raw.get("next_sem_subjects", [])
        ]

        # ── Fee records ───────────────────────────────────────────────
        fee_records = [dict(r) for r in raw.get("fee_records", [])]
        fee_due = sum(
            float(r.get("amount_due") or 0) - float(r.get("amount_paid") or 0)
            for r in fee_records if r.get("status") in ("pending", "overdue")
        )

        # ── Mentoring sessions ────────────────────────────────────────
        mentoring = []
        for m in raw.get("mentoring", []):
            mentoring.append({
                "mentor":         m.get("faculty_mentor"),
                "date":           str(m.get("session_date") or ""),
                "agenda":         m.get("agenda"),
                "notes":          m.get("notes"),
                "action_items":   m.get("action_items"),
                "parent_present": m.get("parent_present", False),
            })

        # ── Placement eligibility ─────────────────────────────────────
        elig = raw.get("placement_eligibility") or {}
        placement_eligibility = {
            "cgpa_eligible":   elig.get("cgpa_eligible", False),
            "arrear_free":     elig.get("arrear_free", False),
            "attendance_ok":   elig.get("attendance_ok", False),
            "cgpa_threshold":  float(elig.get("cgpa_threshold") or 6.5),
            "is_eligible":     elig.get("is_eligible", False),
        } if elig else None

        # ── Derived stats ─────────────────────────────────────────────
        placed          = [p for p in raw.get("placement", []) if p.get("status") == "offered"]
        active_arrears  = [a for a in raw.get("arrears", []) if not a.get("cleared")]
        total_assign    = len(raw.get("assignments", []))
        not_submitted   = sum(1 for a in raw.get("assignments", []) if a.get("submission_status") == "not_submitted")

        return {
            # ── Identity ──────────────────────────────────────────────
            "id":                     raw.get("college_id") or str(raw.get("id")),
            "db_id":                  raw.get("id"),
            "name":                   raw.get("name"),
            "email":                  raw.get("email"),
            "department":             raw.get("dept"),
            "semester":               raw.get("current_semester"),
            "year":                   raw.get("year"),
            "college":                raw.get("college"),
            "phone":                  raw.get("phone"),
            "parent_name":            raw.get("parent_name"),
            "parent_phone":           raw.get("parent_phone"),
            "dob":                    str(raw.get("dob") or ""),
            "gender":                 raw.get("gender"),
            "category":               raw.get("category"),
            "admission_year":         raw.get("admission_year"),
            # ── Academic summary ──────────────────────────────────────
            "currentCGPA":            float(raw.get("cgpa") or 0),
            "predictedCGPA":          float(raw.get("predicted_cgpa") or 0),
            "cgpaHistory":            [float(r["cgpa"]) for r in raw.get("cgpa_history", [])],
            "attendanceOverall":      raw.get("attendance_overall"),
            "examDays":               raw.get("exam_days"),
            "studyStreak":            raw.get("study_streak", 0),
            "langPref":               raw.get("lang_pref", "en"),
            "total_credits_earned":   raw.get("total_credits_earned", 0),
            "total_credits_required": raw.get("total_credits_required", 180),
            # ── Current semester ──────────────────────────────────────
            "subjects":               subjects,
            "syllabusCoverage":       raw.get("syllabus_coverage", []),
            "assignments":            raw.get("assignments", []),
            "assignmentHealth": {
                "total":           total_assign,
                "not_submitted":   not_submitted,
                "submission_rate": round((1 - not_submitted / max(total_assign, 1)) * 100, 1),
            },
            # ── Historical semesters ──────────────────────────────────
            "historicalSemesters":    hist_by_sem,           # {sem: [subject, …]}
            # ── Next semester preview ─────────────────────────────────
            "nextSemesterSubjects":   next_sem_subjects,
            # ── Arrears ───────────────────────────────────────────────
            "arrears":                raw.get("arrears", []),
            "activeArrears":          len(active_arrears),
            # ── Activities ────────────────────────────────────────────
            "activities":             raw.get("activities", []),
            "certCount":              sum(
                                          1 for a in raw.get("activities", [])
                                          if a.get("activity_type") in ("certification", "online_course")
                                          and a.get("verified")
                                      ),
            # ── Fee ───────────────────────────────────────────────────
            "feeRecords":             fee_records,
            "feeDue":                 round(fee_due, 2),
            # ── Placement ─────────────────────────────────────────────
            "placement":              raw.get("placement", []),
            "isPlaced":               len(placed) > 0,
            "placedAt":               placed[0]["company_name"] if placed else None,
            "placementEligibility":   placement_eligibility,
            # ── Mentoring ─────────────────────────────────────────────
            "mentoring":              mentoring,
            # ── Library ───────────────────────────────────────────────
            "library":                raw.get("library", []),
        }


    # ── Chat Queries ──────────────────────────────────────────────────────────

    async def create_chat_session(self, student_db_id: int, title: str = None) -> str:
        """Create a new chat session and return its UUID."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO chat_sessions (student_id, title) VALUES ($1, $2) RETURNING id",
                student_db_id, title,
            )
            return str(row["id"])

    async def ensure_chat_session(self, session_id: str, student_db_id: int, title: str = "Chat Session") -> None:
        """Ensure a chat session exists with the given session ID."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_sessions (id, student_id, title) 
                VALUES ($1, $2, $3) 
                ON CONFLICT (id) DO NOTHING
                """,
                session_id, student_db_id, title
            )

    async def get_chat_sessions(self, student_db_id: int, limit: int = 15) -> list[dict]:
        """Retrieve recent chat sessions for a student."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, created_at, last_active 
                FROM chat_sessions 
                WHERE student_id=$1 
                ORDER BY last_active DESC LIMIT $2
                """,
                student_db_id, limit,
            )
            return [dict(r) for r in rows]

    async def save_message(self, session_id: str, student_db_id: int, role: str, content: str,
                           agent: str = None, citations: list = None, model_used: str = None, lang: str = "en") -> str:
        """Persist a chat message. Returns message UUID."""
        import json
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO messages (session_id, student_id, role, content, agent, citations, model_used, lang)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                session_id, student_db_id, role, content, agent,
                json.dumps(citations or []), model_used, lang,
            )
            await conn.execute("UPDATE chat_sessions SET last_active = NOW() WHERE id = $1", session_id)
            return str(row["id"])

    async def get_chat_history(self, session_id: str, limit: int = 20) -> list[dict]:
        """Retrieve recent messages for a chat session."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role, content, agent, citations, created_at FROM messages WHERE session_id=$1 ORDER BY created_at ASC LIMIT $2",
                session_id, limit,
            )
            return [dict(r) for r in rows]

    # ── ERP Section Queries ───────────────────────────────────────────────────

    async def get_attendance_detail(self, student_db_id: int, subject_code: str = None) -> list[dict]:
        """Period-wise attendance — detect bunk patterns by day/period."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            if subject_code:
                rows = await conn.fetch(
                    "SELECT date, period_number, status FROM attendance_records WHERE student_id=$1 AND subject_code=$2 ORDER BY date DESC LIMIT 60",
                    student_db_id, subject_code,
                )
            else:
                rows = await conn.fetch(
                    "SELECT subject_code, date, period_number, status FROM attendance_records WHERE student_id=$1 ORDER BY date DESC LIMIT 100",
                    student_db_id,
                )
            return [dict(r) for r in rows]

    async def get_syllabus_coverage(self, semester: int) -> list[dict]:
        """Per-unit syllabus coverage from teacher-side data."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM syllabus_coverage WHERE semester=$1 ORDER BY subject_code, unit_number",
                semester,
            )
            return [dict(r) for r in rows]

    async def get_placement_records(self, student_db_id: int) -> list[dict]:
        """Company drives, offer statuses, packages."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM placement_records WHERE student_id=$1 ORDER BY drive_date DESC",
                student_db_id,
            )
            return [dict(r) for r in rows]

    async def get_activities(self, student_db_id: int) -> list[dict]:
        """Certifications, hackathons, clubs, internships."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM activities WHERE student_id=$1 ORDER BY end_date DESC",
                student_db_id,
            )
            return [dict(r) for r in rows]

    async def get_assignments(self, student_db_id: int, semester: int) -> list[dict]:
        """Assignment submission history with scores."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM assignments WHERE student_id=$1 AND semester=$2 ORDER BY due_date DESC",
                student_db_id, semester,
            )
            return [dict(r) for r in rows]

    async def get_topic_mastery(self, student_db_id: int) -> dict:
        """Summarize topic-level mastery from bloom_progress and student_attempts."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            topic_rows = await conn.fetch(
                """
                SELECT subject_code,
                       COALESCE(topic, '') AS topic,
                       MAX(bloom_level) AS bloom_level,
                       BOOL_OR(achieved) AS achieved,
                       AVG(quiz_score) AS avg_score,
                       MAX(updated_at) AS last_seen
                FROM bloom_progress
                WHERE student_id = $1
                GROUP BY subject_code, topic
                ORDER BY subject_code, topic
                """,
                student_db_id,
            )

            attempt_rows = await conn.fetch(
                """
                SELECT subject,
                       MAX(total_score) AS total_score,
                       MAX(l1_score) AS l1_score,
                       MAX(l2_score) AS l2_score,
                       MAX(l3_score) AS l3_score,
                       MAX(timestamp) AS last_attempt
                FROM student_attempts
                WHERE student_id = $1
                GROUP BY subject
                ORDER BY subject
                """,
                student_db_id,
            )

        topics = [
            {
                "subject_code": r["subject_code"],
                "topic": r["topic"],
                "bloom_level": int(r["bloom_level"] or 1),
                "achieved": bool(r["achieved"]),
                "avg_score": float(r["avg_score"] or 0),
                "last_seen": str(r["last_seen"]) if r["last_seen"] else None,
            }
            for r in topic_rows
        ]

        attempts = [
            {
                "subject": r["subject"],
                "total_score": float(r["total_score"] or 0),
                "l1_score": float(r["l1_score"] or 0),
                "l2_score": float(r["l2_score"] or 0),
                "l3_score": float(r["l3_score"] or 0),
                "last_attempt": str(r["last_attempt"]) if r["last_attempt"] else None,
            }
            for r in attempt_rows
        ]

        return {"topics": topics, "attempts": attempts}

    async def get_peer_benchmark(self, student_college_id: str) -> dict | None:
        """
        Anonymous peer benchmarking: CGPA and attendance percentiles within
        same department and semester. No PII exposed.
        """
        row = await self._fetchrow_from_pool(
            "SELECT id, dept, current_semester, cgpa, attendance_overall FROM students WHERE college_id = $1",
            student_college_id,
        )
        if not row:
            return None

        dept = row["dept"] or "CSBS"
        sem = row["current_semester"] or 1
        cgpa = float(row["cgpa"] or 0)
        att = float(row["attendance_overall"] or 0)

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Department averages
            avg_row = await conn.fetchrow(
                """
                SELECT
                    AVG(cgpa) AS avg_cgpa,
                    AVG(attendance_overall) AS avg_attendance,
                    COUNT(*) AS peer_count
                FROM students
                WHERE dept = $1 AND current_semester = $2
                """,
                dept, sem,
            )

            # Percentile: % of peers with LOWER cgpa (higher = better)
            pct_row = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM students s2
                     WHERE s2.dept = $1 AND s2.current_semester = $2 AND s2.cgpa < $3) * 100.0
                    / NULLIF((SELECT COUNT(*) FROM students s2 WHERE s2.dept = $1 AND s2.current_semester = $2), 0)
                    AS cgpa_percentile,
                    (SELECT COUNT(*) FROM students s2
                     WHERE s2.dept = $1 AND s2.current_semester = $2 AND COALESCE(s2.attendance_overall, 0) < $4) * 100.0
                    / NULLIF((SELECT COUNT(*) FROM students s2 WHERE s2.dept = $1 AND s2.current_semester = $2), 0)
                    AS attendance_percentile
                """,
                dept, sem, cgpa, att,
            )

        avg_cgpa = float(avg_row["avg_cgpa"] or 0)
        avg_att = float(avg_row["avg_attendance"] or 0)
        peer_count = int(avg_row["peer_count"] or 0)
        cgpa_pct = float(pct_row["cgpa_percentile"] or 0)
        att_pct = float(pct_row["attendance_percentile"] or 0)

        return {
            "student_id": student_college_id,
            "department": dept,
            "semester": sem,
            "peer_count": peer_count,
            "cgpa": round(cgpa, 2),
            "cgpa_percentile": round(cgpa_pct, 1),
            "cgpa_vs_avg": round(cgpa - avg_cgpa, 2),
            "dept_avg_cgpa": round(avg_cgpa, 2),
            "attendance": round(att, 1),
            "attendance_percentile": round(att_pct, 1),
            "attendance_vs_avg": round(att - avg_att, 1),
            "dept_avg_attendance": round(avg_att, 1),
        }

    # ── Vector / RAG Queries ──────────────────────────────────────────────────

    async def insert_document_chunk(
        self,
        filename: str,
        content: str,
        embedding: list[float],
        subject_code: str = None,
        student_db_id: int = None,
        doc_type: str | None = None,
    ) -> str:
        """Insert a vectorized chunk of text into the documents table."""
        import json
        pool = await get_pool()
        # pgvector needs compact JSON array format '[0.1,0.2,...]' — NOT Python's str() which adds spaces
        vector_str = json.dumps(embedding)
        async with pool.acquire() as conn:
            if doc_type:
                row = await conn.fetchrow(
                    """
                    INSERT INTO documents (filename, content, embedding, subject_code, student_id, doc_type)
                    VALUES ($1, $2, $3::extensions.vector, $4, $5, $6)
                    RETURNING id
                    """,
                    filename, content, vector_str, subject_code, student_db_id, doc_type,
                )
            else:
                row = await conn.fetchrow(
                    """
                    INSERT INTO documents (filename, content, embedding, subject_code, student_id)
                    VALUES ($1, $2, $3::extensions.vector, $4, $5)
                    RETURNING id
                    """,
                    filename, content, vector_str, subject_code, student_db_id,
                )
            return str(row["id"])

    async def search_documents(
        self,
        query_embedding: list[float],
        student_db_id: int = None,
        limit: int = 5,
        doc_type: str | None = None,
    ) -> list[dict]:
        """
        Semantic search over documents using pgvector cosine similarity.
        Returns top-k most relevant document chunks.
        """
        import json
        pool = await get_pool()
        # pgvector needs compact JSON array format '[0.1,0.2,...]' — NOT Python's str() which adds spaces
        vector_str = json.dumps(query_embedding)
        async with pool.acquire() as conn:
            if student_db_id and doc_type:
                rows = await conn.fetch(
                    """
                    SELECT filename, content, subject_code, doc_type,
                           1 - (embedding <=> $1::extensions.vector) AS similarity
                    FROM documents
                    WHERE student_id = $2
                      AND doc_type = $3
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> $1::extensions.vector
                    LIMIT $4
                    """,
                    vector_str, student_db_id, doc_type, limit,
                )
            elif student_db_id:
                rows = await conn.fetch(
                    """
                    SELECT filename, content, subject_code, doc_type,
                           1 - (embedding <=> $1::extensions.vector) AS similarity
                    FROM documents
                    WHERE student_id = $2
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> $1::extensions.vector
                    LIMIT $3
                    """,
                    vector_str, student_db_id, limit,
                )
            elif doc_type:
                rows = await conn.fetch(
                    """
                    SELECT filename, content, subject_code, doc_type,
                           1 - (embedding <=> $1::extensions.vector) AS similarity
                    FROM documents
                    WHERE doc_type = $2
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> $1::extensions.vector
                    LIMIT $3
                    """,
                    vector_str, doc_type, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT filename, content, subject_code, doc_type,
                           1 - (embedding <=> $1::extensions.vector) AS similarity
                    FROM documents
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> $1::extensions.vector
                    LIMIT $2
                    """,
                    vector_str, limit,
                )
            return [dict(r) for r in rows]

    # ── Audit ─────────────────────────────────────────────────────────────────

    async def log_action(self, student_db_id: int, action: str, table: str = None):
        """DPDP Act 2023 audit trail."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO audit_log (student_id, action, table_name) VALUES ($1, $2, $3)",
                student_db_id, action, table,
            )

    # ── Proactive Alerts ──────────────────────────────────────────────────────

    async def create_alert_if_not_exists(
        self,
        student_college_id: str,
        alert_type: str,          # "attendance" | "emotional" | "exam" | "assignment"
        subject_code: str | None,
        severity: str,            # "critical" | "warning" | "notice"
        message: str,
    ) -> bool:
        """
        Idempotent alert creation — skips if an unread alert for the same
        student + alert_type + subject already exists.
        Returns True if a new alert was created, False if skipped.
        """
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                # Check for existing unread alert
                existing = await conn.fetchval(
                    """
                    SELECT id FROM proactive_alerts
                    WHERE student_college_id = $1
                      AND alert_type = $2
                      AND (subject_code = $3 OR ($3 IS NULL AND subject_code IS NULL))
                      AND read_at IS NULL
                    LIMIT 1
                    """,
                    student_college_id, alert_type, subject_code,
                )
                if existing:
                    return False

                await conn.execute(
                    """
                    INSERT INTO proactive_alerts
                        (student_college_id, alert_type, subject_code, severity, message)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    student_college_id, alert_type, subject_code, severity, message,
                )
                return True
        except Exception as e:
            logger.warning(f"create_alert_if_not_exists failed (non-fatal): {e}")
            return False

    async def get_unread_alerts(
        self,
        student_college_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Return unread proactive alerts for a student, newest + most severe first."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, alert_type, subject_code, severity, message, created_at
                    FROM proactive_alerts
                    WHERE student_college_id = $1 AND read_at IS NULL
                    ORDER BY
                        CASE severity
                            WHEN 'critical' THEN 1
                            WHEN 'warning'  THEN 2
                            WHEN 'notice'   THEN 3
                            ELSE 4
                        END,
                        created_at DESC
                    LIMIT $2
                    """,
                    student_college_id, limit,
                )
                return [
                    {
                        "id":           str(r["id"]),
                        "type":         r["alert_type"],
                        "subject_code": r["subject_code"],
                        "severity":     r["severity"],
                        "message":      r["message"],
                        "created_at":   r["created_at"].isoformat(),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning(f"get_unread_alerts failed: {e}")
            return []

    async def mark_alert_read(self, alert_id: str, student_college_id: str) -> bool:
        """Mark a specific alert as read (dismissed). Verifies ownership."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE proactive_alerts
                    SET read_at = NOW()
                    WHERE id = $1 AND student_college_id = $2 AND read_at IS NULL
                    """,
                    alert_id, student_college_id,
                )
                return result == "UPDATE 1"
        except Exception as e:
            logger.warning(f"mark_alert_read failed: {e}")
            return False

    async def get_alert_count(self, student_college_id: str) -> int:
        """Fast unread alert count — used for the nav notification badge."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT COUNT(*) FROM proactive_alerts WHERE student_college_id = $1 AND read_at IS NULL",
                    student_college_id,
                ) or 0
        except Exception:
            return 0

    async def get_parent_summary(self, student_college_id: str) -> dict | None:
        """
        Weekly-style parent engagement report: attendance, risk subjects, fees, alerts.
        No sensitive PII beyond what a parent would expect (child's academic summary).
        """
        row = await self._fetchrow_from_pool(
            """
            SELECT s.id, s.name, s.college_id, s.dept, s.current_semester,
                   s.cgpa, s.attendance_overall, s.arrear_count
            FROM students s
            WHERE s.college_id = $1
            """,
            student_college_id,
        )
        if not row:
            return None

        sid = row["id"]
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Risk subjects (current semester)
            risk_rows = await conn.fetch(
                """
                SELECT code, name, grade, attendance, status
                FROM subject_profiles
                WHERE student_id = $1 AND semester = (SELECT current_semester FROM students WHERE id = $1)
                  AND status IN ('risk', 'watch')
                ORDER BY grade ASC
                """,
                sid, sid,
            )
            # Fee due
            fee_rows = await conn.fetch(
                """
                SELECT fee_type, amount_due, amount_paid, status, semester
                FROM fee_records WHERE student_id = $1
                """,
                sid,
            )
            # Unread alerts (last 7 days)
            alert_rows = await conn.fetch(
                """
                SELECT alert_type, severity, message, created_at
                FROM proactive_alerts
                WHERE student_college_id = $1 AND read_at IS NULL
                  AND created_at >= NOW() - INTERVAL '7 days'
                ORDER BY created_at DESC LIMIT 10
                """,
                student_college_id,
            )

        fee_due = sum(
            float(r.get("amount_due", 0) or 0) - float(r.get("amount_paid", 0) or 0)
            for r in fee_rows if r.get("status") in ("pending", "overdue")
        )
        risk_subjects = [
            {
                "code": r["code"],
                "name": r["name"] or r["code"],
                "grade": float(r["grade"] or 0),
                "attendance": float(r["attendance"] or 0),
                "status": r["status"],
            }
            for r in risk_rows
        ]
        alerts = [
            {
                "type": r["alert_type"],
                "severity": r["severity"],
                "message": r["message"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in alert_rows
        ]

        return {
            "student_name": row["name"],
            "college_id": row["college_id"],
            "department": row["dept"],
            "semester": row["current_semester"],
            "cgpa": round(float(row["cgpa"] or 0), 2),
            "attendance_pct": round(float(row["attendance_overall"] or 0), 1),
            "arrear_count": int(row["arrear_count"] or 0),
            "risk_subjects": risk_subjects,
            "fee_due": round(fee_due, 2),
            "alerts": alerts,
            "report_date": datetime.now().isoformat(),
        }



    async def append_sentiment_point(
        self,
        student_id: str,
        score: float,
        message_snippet: str = None,
    ) -> None:
        """Persist one sentiment data point after a chat interaction. Fire-and-forget."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO sentiment_history (student_college_id, score, message_snippet) VALUES ($1, $2, $3)",
                    student_id, score, (message_snippet or "")[:120],
                )
        except Exception as e:
            logger.warning(f"Sentiment write-back skipped (non-fatal): {e}")

    async def get_sentiment_history(
        self,
        student_id: str,
        limit: int = 30,
    ) -> list[dict]:
        """Retrieve last N sentiment data points ordered oldest-first for charting."""
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT score, recorded_at FROM sentiment_history WHERE student_college_id=$1 ORDER BY recorded_at DESC LIMIT $2",
                    student_id, limit,
                )
                return [{"score": float(r["score"]), "recorded_at": str(r["recorded_at"])} for r in reversed(rows)]
        except Exception as e:
            logger.warning(f"Sentiment history fetch failed: {e}")
            return []

    # ── Department Curriculum Queries ─────────────────────────────────────────

    async def get_department_curriculum(
        self,
        semester: int | None = None,
        subject_type: str | None = None,
    ) -> list[dict]:
        """
        Fetch CSBS department curriculum.
        - semester: 1-8 (None = all semesters)
        - subject_type: 'core'|'lab'|'professional_elective'|'open_elective'|
                        'management_elective'|'mandatory' (None = all types)

        Agents use this to answer:
        - "What subjects are in Sem 4?"
        - "What electives are available in Sem 5?"
        - "List all subjects for CSBS R2021"
        """
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                conditions = ["department = 'CSBS'", "regulation = 'R2021'"]
                args = []
                if semester is not None:
                    args.append(semester)
                    conditions.append(f"semester = ${len(args)}")
                if subject_type is not None:
                    args.append(subject_type)
                    conditions.append(f"subject_type = ${len(args)}")

                where = " AND ".join(conditions)
                rows = await conn.fetch(
                    f"""
                    SELECT semester, subject_code, subject_title, category,
                           credits, subject_type, elective_vertical,
                           open_elective_slot, is_lab, notes
                    FROM department_curriculum
                    WHERE {where}
                    ORDER BY semester, subject_type, subject_code
                    """,
                    *args,
                )
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Curriculum fetch failed: {e}")
            return []

    async def get_elective_options(
        self,
        vertical: str | None = None,
        oe_slot: str | None = None,
    ) -> list[dict]:
        """
        Fetch professional or open elective options.
        - vertical: 'I'|'II'|'III'|'IV'|'V'|'VI' → PE vertical
        - oe_slot:  'OE1'|'OE2'|'OE3'|'OE4'      → Open elective slot

        Used by agent to answer:
        - "What are my elective options for Vertical IV (AI/ML)?"
        - "What can I take as OE-II in Sem 7?"
        """
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                if vertical:
                    rows = await conn.fetch(
                        "SELECT subject_code, subject_title, credits, elective_vertical "
                        "FROM department_curriculum "
                        "WHERE elective_vertical = $1 ORDER BY subject_code",
                        vertical,
                    )
                elif oe_slot:
                    rows = await conn.fetch(
                        "SELECT subject_code, subject_title, credits, open_elective_slot "
                        "FROM department_curriculum "
                        "WHERE open_elective_slot = $1 ORDER BY subject_code",
                        oe_slot,
                    )
                else:
                    rows = await conn.fetch(
                        "SELECT subject_code, subject_title, credits, subject_type, "
                        "elective_vertical, open_elective_slot "
                        "FROM department_curriculum "
                        "WHERE subject_type IN ('professional_elective','open_elective','management_elective') "
                        "ORDER BY subject_type, elective_vertical, subject_code"
                    )
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Elective options fetch failed: {e}")
            return []

    async def get_curriculum_summary(self) -> dict:
        """
        Returns a summary dict of the full CSBS curriculum grouped by semester.
        Ideal for RAG context injection: gives the agent an instant overview.
        """
        try:
            all_rows = await self.get_department_curriculum()
            by_sem: dict = {}
            for r in all_rows:
                sem = str(r["semester"])
                if sem not in by_sem:
                    by_sem[sem] = {"core": [], "labs": [], "electives": []}
                if r["subject_type"] in ("core",):
                    by_sem[sem]["core"].append(f"{r['subject_code']} – {r['subject_title']} ({r['credits']} cr)")
                elif r["subject_type"] == "lab":
                    by_sem[sem]["labs"].append(f"{r['subject_code']} – {r['subject_title']}")
                else:
                    tag = r.get("elective_vertical") or r.get("open_elective_slot") or r["subject_type"]
                    by_sem[sem]["electives"].append(f"[{tag}] {r['subject_code']} – {r['subject_title']}")
            return by_sem
        except Exception as e:
            logger.warning(f"Curriculum summary failed: {e}")
            return {}

    async def get_subject_syllabus(
        self,
        subject_code: str | None = None,
        semester: int | None = None,
    ) -> list[dict]:
        """
        Fetch unit-wise syllabus topics.
        - subject_code: get all 5 units for one subject
        - semester: get all units for all subjects in that semester
        - None, None: get everything (for full RAG dump)

        Agents use this to answer:
        - "What are the topics in OS Unit 3?"
        - "What does Unit II of ML cover?"
        """
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                if subject_code:
                    rows = await conn.fetch(
                        "SELECT subject_code, subject_title, unit_number, unit_title, topics "
                        "FROM subject_syllabus WHERE subject_code = $1 ORDER BY unit_number",
                        subject_code,
                    )
                elif semester:
                    rows = await conn.fetch(
                        """
                        SELECT ss.subject_code, ss.subject_title, ss.unit_number, ss.unit_title, ss.topics
                        FROM subject_syllabus ss
                        JOIN department_curriculum dc ON dc.subject_code = ss.subject_code
                        WHERE dc.semester = $1
                        ORDER BY ss.subject_code, ss.unit_number
                        """,
                        semester,
                    )
                else:
                    rows = await conn.fetch(
                        "SELECT subject_code, subject_title, unit_number, unit_title, topics "
                        "FROM subject_syllabus ORDER BY subject_code, unit_number"
                    )
                return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Subject syllabus fetch failed: {e}")
            return []

    async def get_tutor_options(self, student_college_id: str) -> dict:
        """
        Fetch tutor UI options from DB only: subjects (from profile) and
        topics per subject (from subject_syllabus). No hardcoded data.
        Returns: { subjects: [{ code, name, bloomLevel, ... }], topics_by_subject: { "CODE": ["topic1", ...] } }
        """
        try:
            profile = await self.get_student_by_college_id(student_college_id)
            if not profile:
                return {"subjects": [], "topics_by_subject": {}}

            subjects = profile.get("subjects", [])
            if not subjects:
                # Fallback: current semester curriculum from department_curriculum so options still come from DB
                sem = profile.get("current_semester") or profile.get("semester")
                if sem is not None:
                    rows = await self._fetch_from_pool(
                        """
                        SELECT subject_code AS code, subject_title AS name
                        FROM department_curriculum WHERE semester = $1
                        ORDER BY subject_type, subject_code
                        """,
                        sem,
                    )
                    subjects = [{"code": r["code"], "name": r["name"], "bloomLevel": 2} for r in rows]

            topics_by_subject = {}
            for subj in subjects:
                code = subj.get("code") or subj.get("subject_code")
                if not code:
                    continue
                syllabus = await self.get_subject_syllabus(subject_code=code)
                topic_list = []
                for row in syllabus:
                    # 1. Add Unit Title as a primary topic
                    unit_title = (row.get("unit_title") or "").strip()
                    if unit_title and unit_title not in topic_list:
                        topic_list.append(unit_title)
                    
                    # 2. Add granular topics if present
                    raw = row.get("topics")
                    if raw:
                        # Handle both ARRAY (list) and string formats
                        parts = []
                        if isinstance(raw, list):
                            parts = raw
                        elif isinstance(raw, str):
                            parts = raw.replace("\n", ",").split(",")
                        
                        for p in parts:
                            if isinstance(p, str):
                                t = p.strip()
                                if t and t not in topic_list:
                                    topic_list.append(t)
                                    
                topics_by_subject[code] = topic_list

            return {
                "subjects": subjects,
                "topics_by_subject": topics_by_subject,
            }
        except Exception as e:
            logger.warning(f"get_tutor_options failed: {e}")
            return {"subjects": [], "topics_by_subject": {}}

    async def authenticate_student(self, college_id: str, password: str) -> dict | None:
        """
        Verify college_id + password against the DB.
        Returns the full student profile dict on success, None on failure.
        Uses bcrypt to check the stored password_hash.
        """
        import bcrypt
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, college_id, name, email, dept, year, current_semester,
                           college, cgpa, predicted_cgpa, attendance_overall, arrear_count,
                           password_hash
                    FROM students WHERE college_id = $1
                    """,
                    college_id,
                )
            if not row:
                return None
            row_dict = dict(row)
            stored_hash = row_dict.pop("password_hash", None)
            if not stored_hash:
                return None
            # bcrypt.checkpw needs bytes
            if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
                return row_dict
            return None
        except Exception as e:
            logger.warning(f"authenticate_student failed: {e}")
            return None


    # ════════════════════════════════════════════════════════════════════════
    # V1 TEACHING CORE — Lesson Completion, Confusion, Spaced Repetition
    # ════════════════════════════════════════════════════════════════════════

    async def record_lesson_completion(
        self,
        student_id: str,
        subject_code: str,
        topic: str,
        steps_completed: int,
        bloom_level: int,
    ) -> None:
        """
        Write back after a tutor lesson ends.
        Upserts into bloom_progress to track last_reviewed_at for spaced repetition.
        Uses student college_id to look up the DB int id.
        """
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                student_row = await conn.fetchrow(
                    "SELECT id FROM students WHERE college_id = $1", student_id
                )
                if not student_row:
                    return
                db_id = student_row["id"]

                await conn.execute(
                    """
                    INSERT INTO bloom_progress
                        (student_id, subject_code, topic, bloom_level, achieved, quiz_score, updated_at)
                    VALUES ($1, $2, $3, $4, false, 0, NOW())
                    ON CONFLICT (student_id, subject_code, topic)
                    DO UPDATE SET
                        bloom_level = GREATEST(bloom_progress.bloom_level, $4),
                        updated_at  = NOW()
                    """,
                    db_id, subject_code, topic, bloom_level,
                )
                logger.info(
                    f"Lesson completion recorded: student={student_id} "
                    f"subject={subject_code} topic={topic} steps={steps_completed}"
                )
        except Exception as e:
            logger.warning(f"record_lesson_completion failed (non-fatal): {e}")

    async def flag_confusion_topic(
        self,
        student_id: str,
        topic_name: str,
        subject_code: str,
    ) -> None:
        """
        Flag a topic as confusing in the student's Learning DNA weak_topics list.
        Called when the student asks the same concept 3+ times in a session.
        """
        try:
            entry = {"topic": topic_name, "subject_code": subject_code, "flagged": "confusion"}
            await self.update_learning_dna(
                student_college_id=student_id,
                weak_topics_append=[entry],
            )
            logger.info(f"Confusion flagged: student={student_id} topic={topic_name}")
        except Exception as e:
            logger.warning(f"flag_confusion_topic failed (non-fatal): {e}")

    async def get_due_topics(self, student_id: str) -> list[dict]:
        """
        Spaced Repetition — SM-2 inspired query.
        Returns topics due for review based on bloom_progress.updated_at.
        Spacing intervals: 1d → 3d → 7d → 14d → 30d based on bloom_level.
        """
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                student_row = await conn.fetchrow(
                    "SELECT id FROM students WHERE college_id = $1", student_id
                )
                if not student_row:
                    return []
                db_id = student_row["id"]

                rows = await conn.fetch(
                    """
                    SELECT
                        subject_code,
                        COALESCE(topic, '') AS topic,
                        bloom_level,
                        achieved,
                        avg_score,
                        updated_at,
                        NOW() - updated_at AS time_since
                    FROM bloom_progress
                    WHERE student_id = $1
                      AND updated_at IS NOT NULL
                    ORDER BY updated_at ASC
                    LIMIT 20
                    """,
                    db_id,
                )

            # SM-2 interval schedule based on bloom_level
            # Bloom 1-2 → review after 1d, Bloom 3-4 → 3d, Bloom 5-6 → 7d
            due_topics = []
            for r in rows:
                bloom = int(r["bloom_level"] or 1)
                if bloom <= 2:
                    interval_days = 1
                elif bloom <= 4:
                    interval_days = 3
                else:
                    interval_days = 7

                age_seconds = r["time_since"].total_seconds() if r["time_since"] else 0
                age_days = age_seconds / 86400
                due_in_days = max(0, interval_days - age_days)
                is_due = age_days >= interval_days

                if is_due:
                    due_topics.append({
                        "subject_code":  r["subject_code"],
                        "topic":         r["topic"],
                        "bloom_level":   bloom,
                        "achieved":      bool(r["achieved"]),
                        "avg_score":     float(r["avg_score"] or 0),
                        "last_reviewed": str(r["updated_at"]) if r["updated_at"] else None,
                        "due_in_days":   round(due_in_days, 1),
                        "priority":      "high" if age_days > interval_days * 2 else "normal",
                    })

            return due_topics[:5]  # Top 5 most overdue

        except Exception as e:
            logger.warning(f"get_due_topics failed (non-fatal): {e}")
            return []

    async def update_checkpoint_result(
        self,
        student_id: str,
        subject_code: str,
        topic: str,
        correct: bool,
        bloom_level: int,
    ) -> None:
        """
        After a checkpoint answer, update bloom_progress and Learning DNA.
        Correct → achieves current bloom level, increments correct_answers.
        Wrong   → flags weak topic in Learning DNA.
        """
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                student_row = await conn.fetchrow(
                    "SELECT id FROM students WHERE college_id = $1", student_id
                )
                if not student_row:
                    return
                db_id = student_row["id"]

                if correct:
                    await conn.execute(
                        """
                        INSERT INTO bloom_progress
                            (student_id, subject_code, topic, bloom_level, achieved, quiz_score, updated_at)
                        VALUES ($1, $2, $3, $4, true, 8, NOW())
                        ON CONFLICT (student_id, subject_code, topic)
                        DO UPDATE SET
                            achieved    = true,
                            bloom_level = GREATEST(bloom_progress.bloom_level, $4),
                            quiz_score  = 8,
                            updated_at  = NOW()
                        """,
                        db_id, subject_code, topic, bloom_level,
                    )
                    await self.update_learning_dna(
                        student_college_id=student_id,
                        questions_delta=1,
                        correct_delta=1,
                        strong_topics_append=[{"topic": topic, "subject_code": subject_code}],
                    )
                else:
                    await self.update_learning_dna(
                        student_college_id=student_id,
                        questions_delta=1,
                        weak_topics_append=[{"topic": topic, "subject_code": subject_code}],
                    )

        except Exception as e:
            logger.warning(f"update_checkpoint_result failed (non-fatal): {e}")


# Singleton
db = Database()

