"""
Memory Agent — V4 Student Long-Term Memory Layer
Manages per-concept knowledge state using the SM-2 Spaced Repetition algorithm.

SM-2 Algorithm:
  - Each concept has: ease_factor (EF), interval (days), repetitions (n)
  - After a correct checkpoint (score q ≥ 3 on 0–5 scale):
      if n == 0: interval = 1
      if n == 1: interval = 6
      else:      interval = round(interval * EF)
      EF = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
      if EF < 1.3: EF = 1.3
      n += 1
  - After incorrect (q < 3):
      n = 0, interval = 1
      EF unchanged
  - next_review_at = now + interval days

Tables used:
  - student_learning_memory  (SM-2 state per concept)
  - student_learning_dna     (overall learning profile)
  - tutor_checkpoints        (checkpoint history for analytics)
  - study_sessions           (per-lesson session records)
  - bloom_progress           (Bloom's taxonomy progression)
"""
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from db import db, get_pool

logger = logging.getLogger(__name__)

# ── SM-2 Algorithm ─────────────────────────────────────────────────────────

def sm2_update(
    *,
    ease_factor: float = 2.5,
    interval_days: int = 1,
    repetitions: int = 0,
    score: float,               # 0–5 scale (0=wrong, 3=ok, 5=perfect)
) -> tuple[float, int, int]:
    """
    Apply one SM-2 review cycle.
    Returns (new_ease_factor, new_interval_days, new_repetitions).
    """
    q = min(5.0, max(0.0, score * 5.0))          # normalize 0–1 score to 0–5

    if q >= 3.0:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = max(1, round(interval_days * ease_factor))
        new_ef = ease_factor + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        new_ef = max(1.3, new_ef)
        new_reps = repetitions + 1
    else:
        new_interval = 1
        new_ef = ease_factor   # EF unchanged on failure
        new_reps = 0

    return new_ef, new_interval, new_reps


def score_from_checkpoint(is_correct: bool, score: float) -> float:
    """Convert checkpoint result to SM-2 0-5 scale."""
    if is_correct:
        return max(0.6, min(1.0, score or 1.0))
    return min(0.5, score or 0.0)


# ── Memory Read/Write ───────────────────────────────────────────────────────

class MemoryAgent:
    """
    Manages long-term student memory using SM-2 spaced repetition.
    All methods use the shared asyncpg pool from db.py.
    """

    async def get_memory(
        self,
        student_db_id: int,
        subject_code: str,
        topic: str,
    ) -> list[dict]:
        """
        Retrieve all concept memories for a student/subject/topic.
        Returns list of concept rows sorted by next_review_at ASC.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, concept, times_taught, times_correct, times_wrong,
                       avg_score, last_studied, difficulty_level, notes,
                       ease_factor, interval_days, repetitions, next_review_at,
                       last_score, confusion_count
                FROM student_learning_memory
                WHERE student_id = $1 AND subject_code = $2 AND topic = $3
                ORDER BY next_review_at ASC
                """,
                student_db_id, subject_code, topic,
            )
        return [dict(r) for r in rows]

    async def upsert_concept(
        self,
        *,
        student_db_id: int,
        subject_code: str,
        topic: str,
        concept: str,
        is_correct: bool,
        score: float = 0.0,
        session_id: str | None = None,
        notes: str | None = None,
    ) -> dict:
        """
        Upsert SM-2 state for one concept after a checkpoint.
        Creates the row if it doesn't exist (UPSERT on unique constraint).
        Returns the updated memory row.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Fetch current state
            existing = await conn.fetchrow(
                """
                SELECT ease_factor, interval_days, repetitions, times_taught,
                       times_correct, times_wrong, avg_score, confusion_count
                FROM student_learning_memory
                WHERE student_id = $1 AND subject_code = $2 AND topic = $3 AND concept = $4
                """,
                student_db_id, subject_code, topic, concept,
            )

            if existing:
                ef = float(existing["ease_factor"] or 2.5)
                iv = int(existing["interval_days"] or 1)
                reps = int(existing["repetitions"] or 0)
                taught = int(existing["times_taught"] or 0)
                correct = int(existing["times_correct"] or 0)
                wrong = int(existing["times_wrong"] or 0)
                old_avg = float(existing["avg_score"] or 0.0)
                confusion = int(existing["confusion_count"] or 0)
            else:
                ef, iv, reps = 2.5, 1, 0
                taught, correct, wrong, old_avg, confusion = 0, 0, 0, 0.0, 0

            # Apply SM-2
            sm2_score = score_from_checkpoint(is_correct, score)
            new_ef, new_iv, new_reps = sm2_update(
                ease_factor=ef, interval_days=iv, repetitions=reps, score=sm2_score,
            )
            next_review = datetime.now(timezone.utc) + timedelta(days=new_iv)

            # Counters
            new_taught = taught + 1
            new_correct = correct + (1 if is_correct else 0)
            new_wrong = wrong + (0 if is_correct else 1)
            new_avg = round(((old_avg * taught) + score) / new_taught, 4)
            new_confusion = confusion + (1 if not is_correct else 0)
            difficulty = round(max(0.0, min(1.0, 1.0 - new_avg)), 4)

            row = await conn.fetchrow(
                """
                INSERT INTO student_learning_memory
                    (student_id, subject_code, topic, concept,
                     times_taught, times_correct, times_wrong, avg_score,
                     difficulty_level, last_studied,
                     ease_factor, interval_days, repetitions, next_review_at,
                     last_score, confusion_count, session_id, notes, updated_at)
                VALUES
                    ($1, $2, $3, $4,
                     $5, $6, $7, $8,
                     $9, NOW(),
                     $10, $11, $12, $13,
                     $14, $15, $16, $17, NOW())
                ON CONFLICT (student_id, subject_code, topic, concept)
                DO UPDATE SET
                    times_taught   = $5,
                    times_correct  = $6,
                    times_wrong    = $7,
                    avg_score      = $8,
                    difficulty_level = $9,
                    last_studied   = NOW(),
                    ease_factor    = $10,
                    interval_days  = $11,
                    repetitions    = $12,
                    next_review_at = $13,
                    last_score     = $14,
                    confusion_count = $15,
                    session_id     = COALESCE($16, student_learning_memory.session_id),
                    notes          = COALESCE($17, student_learning_memory.notes),
                    updated_at     = NOW()
                RETURNING *
                """,
                student_db_id, subject_code, topic, concept,
                new_taught, new_correct, new_wrong, new_avg,
                difficulty,
                new_ef, new_iv, new_reps, next_review,
                round(score, 4), new_confusion, session_id, notes,
            )
        return dict(row)

    async def record_checkpoint(
        self,
        *,
        student_db_id: int,
        subject_code: str,
        topic: str,
        question: str,
        question_type: str,
        student_answer: str,
        correct_answer: str,
        is_correct: bool,
        score: float,
        feedback: str | None = None,
        response_time_ms: int | None = None,
        bloom_level: int = 2,
        after_step: int | None = None,
        session_id: str | None = None,
    ) -> str:
        """
        Persist a checkpoint attempt in tutor_checkpoints table.
        Also updates student_learning_memory (SM-2) for the topic concept.
        Returns the checkpoint UUID.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tutor_checkpoints
                    (student_id, session_id, subject_code, topic, question,
                     question_type, student_answer, correct_answer, is_correct,
                     score, feedback, response_time_ms, bloom_level, after_step)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING id
                """,
                student_db_id, session_id, subject_code, topic, question,
                question_type, student_answer, correct_answer, is_correct,
                round(score, 4), feedback, response_time_ms, bloom_level, after_step,
            )
        checkpoint_id = str(row["id"])

        # Update SM-2 memory (the topic itself as concept)
        await self.upsert_concept(
            student_db_id=student_db_id,
            subject_code=subject_code,
            topic=topic,
            concept=topic,        # topic-level memory
            is_correct=is_correct,
            score=score,
            session_id=session_id,
        )

        return checkpoint_id

    async def get_due_topics(
        self,
        student_db_id: int,
        limit: int = 10,
        horizon_hours: int = 24,
    ) -> list[dict]:
        """
        Return topics due for spaced repetition review.
        `horizon_hours`: how many hours ahead to look (default = due within 24h).
        Returns rows sorted by urgency (overdue first).
        """
        pool = await get_pool()
        horizon = datetime.now(timezone.utc) + timedelta(hours=horizon_hours)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT subject_code, topic, concept,
                       next_review_at, interval_days, ease_factor,
                       times_wrong, avg_score, confusion_count
                FROM student_learning_memory
                WHERE student_id = $1
                  AND next_review_at <= $2
                ORDER BY next_review_at ASC, confusion_count DESC
                LIMIT $3
                """,
                student_db_id, horizon, limit,
            )
        return [dict(r) for r in rows]

    async def get_weak_areas(
        self,
        student_db_id: int,
        subject_code: str | None = None,
        top_n: int = 10,
    ) -> list[dict]:
        """
        Identify weak areas (high difficulty, low avg_score, many wrong answers).
        Returns top N concepts sorted by weakness score (descending).
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            if subject_code:
                rows = await conn.fetch(
                    """
                    SELECT subject_code, topic, concept, avg_score,
                           times_wrong, times_correct, difficulty_level,
                           confusion_count, last_studied
                    FROM student_learning_memory
                    WHERE student_id = $1 AND subject_code = $2
                    ORDER BY difficulty_level DESC, confusion_count DESC, avg_score ASC
                    LIMIT $3
                    """,
                    student_db_id, subject_code, top_n,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT subject_code, topic, concept, avg_score,
                           times_wrong, times_correct, difficulty_level,
                           confusion_count, last_studied
                    FROM student_learning_memory
                    WHERE student_id = $1
                    ORDER BY difficulty_level DESC, confusion_count DESC, avg_score ASC
                    LIMIT $2
                    """,
                    student_db_id, top_n,
                )
        return [dict(r) for r in rows]

    async def get_progress_summary(self, student_db_id: int, subject_code: str | None = None) -> dict:
        """
        Return a high-level progress summary across all topics.
        Used for the Progress Dashboard page.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            base = "WHERE student_id = $1"
            args = [student_db_id]
            if subject_code:
                base += " AND subject_code = $2"
                args.append(subject_code)

            agg = await conn.fetchrow(
                f"""
                SELECT COUNT(DISTINCT topic) AS total_topics,
                       COUNT(*) AS total_concepts,
                       AVG(avg_score) AS overall_avg_score,
                       SUM(times_correct) AS total_correct,
                       SUM(times_wrong) AS total_wrong,
                       SUM(confusion_count) AS total_confusion,
                       COUNT(*) FILTER (WHERE avg_score >= 0.7) AS mastered_concepts,
                       COUNT(*) FILTER (WHERE avg_score < 0.4 AND times_taught > 0) AS struggling_concepts,
                       COUNT(*) FILTER (WHERE next_review_at <= NOW()) AS due_for_review
                FROM student_learning_memory
                {base}
                """,
                *args,
            )

            by_subject = await conn.fetch(
                f"""
                SELECT subject_code,
                       COUNT(DISTINCT topic) AS topics,
                       AVG(avg_score) AS avg_score,
                       COUNT(*) FILTER (WHERE avg_score >= 0.7) AS mastered,
                       COUNT(*) FILTER (WHERE next_review_at <= NOW()) AS due_count
                FROM student_learning_memory
                {base}
                GROUP BY subject_code
                ORDER BY avg_score ASC
                """,
                *args,
            )

            checkpoint_stats = await conn.fetchrow(
                f"""
                SELECT COUNT(*) AS total_checkpoints,
                       SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS passed,
                       AVG(score) AS avg_checkpoint_score,
                       AVG(response_time_ms) AS avg_response_ms
                FROM tutor_checkpoints
                WHERE student_id = $1
                {' AND subject_code = $2' if subject_code else ''}
                """,
                *args,
            )

        total = int(agg["total_concepts"] or 0)
        correct = int(agg["total_correct"] or 0)
        wrong = int(agg["total_wrong"] or 0)
        total_attempts = correct + wrong

        return {
            "total_topics":          int(agg["total_topics"] or 0),
            "total_concepts":        total,
            "mastered_concepts":     int(agg["mastered_concepts"] or 0),
            "struggling_concepts":   int(agg["struggling_concepts"] or 0),
            "due_for_review":        int(agg["due_for_review"] or 0),
            "overall_accuracy":      round((correct / max(total_attempts, 1)) * 100, 1),
            "overall_avg_score":     round(float(agg["overall_avg_score"] or 0), 3),
            "total_checkpoints":     int(checkpoint_stats["total_checkpoints"] or 0),
            "checkpoint_pass_rate":  round(
                (int(checkpoint_stats["passed"] or 0) /
                 max(int(checkpoint_stats["total_checkpoints"] or 1), 1)) * 100, 1
            ),
            "avg_checkpoint_score":  round(float(checkpoint_stats["avg_checkpoint_score"] or 0), 3),
            "avg_response_ms":       int(checkpoint_stats["avg_response_ms"] or 0),
            "by_subject":            [dict(r) for r in by_subject],
        }

    async def update_study_session(
        self,
        *,
        student_db_id: int,
        subject_code: str,
        topic: str,
        session_id: str | None = None,
        duration_minutes: int = 0,
        concepts_covered: int = 0,
        concepts_mastered: int = 0,
        concepts_struggled: int = 0,
        score_avg: float | None = None,
        checkpoint_pass_rate: float | None = None,
        teaching_style: str = "visual + example-based",
    ) -> str:
        """Record or update a study session row. Returns session UUID."""
        pool = await get_pool()
        now = datetime.now(timezone.utc)
        peak_hour = now.hour
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO study_sessions
                    (student_id, subject_code, topic, started_at, ended_at,
                     duration_minutes, concepts_covered, concepts_mastered, concepts_struggled,
                     peak_hour, score_avg, checkpoint_pass_rate, teaching_style, session_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                student_db_id, subject_code, topic,
                now - timedelta(minutes=duration_minutes), now,
                duration_minutes, concepts_covered, concepts_mastered, concepts_struggled,
                peak_hour, score_avg, checkpoint_pass_rate, teaching_style, session_id,
            )
        return str(row["id"]) if row else ""

    async def update_learning_dna_from_lesson(
        self,
        student_college_id: str,
        *,
        teaching_style: str | None = None,
        weak_topics_append: list[dict] | None = None,
        strong_topics_append: list[dict] | None = None,
        quiz_result: dict | None = None,
        questions_delta: int = 0,
        correct_delta: int = 0,
    ) -> None:
        """After a lesson completes, update the student's learning DNA profile."""
        try:
            await db.update_learning_dna(
                student_college_id,
                preferred_style=teaching_style,
                weak_topics_append=weak_topics_append,
                strong_topics_append=strong_topics_append,
                quiz_history_entry=quiz_result,
                questions_delta=questions_delta,
                quizzes_delta=1 if questions_delta > 0 else 0,
                correct_delta=correct_delta,
                peak_hour_observation=datetime.now(timezone.utc).hour,
            )
        except Exception as e:
            logger.warning(f"Learning DNA update failed: {e}")


# ── Module-level singleton ─────────────────────────────────────────────────
_memory_agent: MemoryAgent | None = None


def get_memory_agent() -> MemoryAgent:
    global _memory_agent
    if _memory_agent is None:
        _memory_agent = MemoryAgent()
    return _memory_agent
