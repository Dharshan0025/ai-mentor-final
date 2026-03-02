"""
AI-Mentor Proactive Scheduler — Attendance Cliff Warning
Runs as a background APScheduler attached to the FastAPI lifespan.

Jobs:
  - attendance_cliff_scan: runs daily at 18:00 IST
    Scans every student, creates alerts for attendance danger zones.
"""
import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


# ── Attendance thresholds ─────────────────────────────────────────────────────
DETENTION_THRESHOLD = 65   # alert type: critical
WARNING_THRESHOLD   = 75   # alert type: warning
WATCH_THRESHOLD     = 80   # alert type: notice


async def attendance_cliff_scan():
    """
    Nightly scan — checks every student's subject-wise attendance.
    Creates proactive alerts for danger zones.
    Skips if an unread alert for the same student+subject already exists.
    """
    from db import db, get_pool

    logger.info("Proactive scan: attendance_cliff_scan starting...")
    pool = await get_pool()

    try:
        # Fetch all active students (year <= 4, not graduated)
        async with pool.acquire() as conn:
            students = await conn.fetch(
                "SELECT id, college_id, name, current_semester, year FROM students ORDER BY id"
            )

        created = 0
        skipped = 0

        for student in students:
            college_id = student["college_id"]
            student_db_id = student["id"]

            # Get their current semester subject attendance
            try:
                current_sem = student["current_semester"] or 1
                async with pool.acquire() as conn:
                    subjects = await conn.fetch(
                        """
                        SELECT subject_code, subject_name, attendance_percentage,
                               classes_attended, total_classes
                        FROM subject_enrollments
                        WHERE student_id = $1 AND semester = $2
                        """,
                        student_db_id, current_sem
                    )
            except Exception as e:
                logger.debug(f"Subject fetch failed for {college_id}: {e}")
                continue

            for subj in subjects:
                att = float(subj.get("attendance_percentage") or 0)
                name = subj.get("subject_name") or subj.get("subject_code", "")
                code = subj.get("subject_code", "")

                if att < DETENTION_THRESHOLD:
                    severity = "critical"
                    message = (
                        f"{name} ({code}): Attendance at {att:.0f}% — DETENTION RISK. "
                        f"You need to attend every remaining class without exception."
                    )
                elif att < WARNING_THRESHOLD:
                    # Calculate classes needed to reach 75%
                    attended = int(subj.get("classes_attended") or 0)
                    total = int(subj.get("total_classes") or 1)
                    needed = max(0, int((0.75 * total - attended) / 0.25) + 1)
                    severity = "warning"
                    message = (
                        f"{name} ({code}): {att:.0f}% attendance (below 75% threshold). "
                        f"Attend the next {needed} class(es) consecutively to become safe."
                    )
                elif att < WATCH_THRESHOLD:
                    severity = "notice"
                    message = (
                        f"{name} ({code}): {att:.0f}% — approaching the 75% danger zone. "
                        f"Do not miss any more classes."
                    )
                else:
                    continue  # Student is safe, no alert needed

                # Check if same alert already exists and is unread
                ok = await db.create_alert_if_not_exists(
                    student_college_id=college_id,
                    alert_type="attendance",
                    subject_code=code,
                    severity=severity,
                    message=message,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1

        logger.info(
            f"attendance_cliff_scan done: {created} alerts created, {skipped} duplicates skipped"
        )

    except Exception as e:
        logger.error(f"attendance_cliff_scan failed: {e}", exc_info=True)


# ── Sentiment crash scanner ───────────────────────────────────────────────────

async def sentiment_crash_scan():
    """
    Check students with consistently negative sentiment (3+ days avg < -0.4).
    Creates an emotional support alert.
    """
    from db import db, get_pool

    logger.info("Proactive scan: sentiment_crash_scan starting...")
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            students = await conn.fetch("SELECT id, college_id, name FROM students")

        for student in students:
            college_id = student["college_id"]
            history = await db.get_sentiment_history(college_id, limit=3)
            if len(history) < 3:
                continue

            recent_avg = sum(p["score"] for p in history) / len(history)
            if recent_avg < -0.4:
                await db.create_alert_if_not_exists(
                    student_college_id=college_id,
                    alert_type="emotional",
                    subject_code=None,
                    severity="notice",
                    message=(
                        "Your recent interactions suggest you might be under significant stress. "
                        "Your AI Mentor is here — talk to it anytime, or consider speaking to a counselor."
                    ),
                )

    except Exception as e:
        logger.error(f"sentiment_crash_scan failed: {e}", exc_info=True)


# ── Grade velocity scanner ─────────────────────────────────────────────────────

async def grade_velocity_scan():
    """
    Nightly scan — checks subjects where predicted grade indicates arrear risk.
    Creates proactive 'grade' alerts when predicted grade falls below threshold.
    """
    from db import db, get_pool

    logger.info("Proactive scan: grade_velocity_scan starting...")
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            students = await conn.fetch(
                "SELECT id, college_id, current_semester FROM students ORDER BY id"
            )

        created = 0
        skipped = 0

        for student in students:
            college_id = student["college_id"]
            student_db_id = student["id"]
            current_sem = student["current_semester"] or 1

            # Fetch current semester subject profiles with predictions
            try:
                async with pool.acquire() as conn:
                    subjects = await conn.fetch(
                        """
                        SELECT code, name, grade, predicted, status
                        FROM subject_profiles
                        WHERE student_id = $1 AND semester = $2
                        """,
                        student_db_id, current_sem,
                    )
            except Exception as e:
                logger.debug(f"Grade velocity subject fetch failed for {college_id}: {e}")
                continue

            for subj in subjects:
                code = subj.get("code") or ""
                name = subj.get("name") or code
                predicted = float(subj.get("predicted") or 0)
                grade = float(subj.get("grade") or 0)
                status = (subj.get("status") or "safe").lower()

                # Threshold-based arrear risk: predicted grade below 5.5
                if predicted <= 0:
                    continue
                if predicted >= 5.5:
                    continue

                if status == "risk" or grade < 5.5:
                    severity = "critical"
                else:
                    severity = "warning"

                message = (
                    f"{name} ({code}): Predicted grade {predicted:.1f} suggests high arrear risk. "
                    f"Focus on this subject with extra practice and assignments."
                )

                ok = await db.create_alert_if_not_exists(
                    student_college_id=college_id,
                    alert_type="grade",
                    subject_code=code,
                    severity=severity,
                    message=message,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1

        logger.info(
            f"grade_velocity_scan done: {created} alerts created, {skipped} duplicates skipped"
        )

    except Exception as e:
        logger.error(f"grade_velocity_scan failed: {e}", exc_info=True)


# ── Revision / spaced repetition scanner ─────────────────────────────────────--

async def revision_scan():
    """
    Spaced repetition helper — finds topics that need revision based on
    bloom_progress and creates 'revision' proactive alerts.
    """
    from db import db, get_pool

    logger.info("Proactive scan: revision_scan starting...")
    pool = await get_pool()

    try:
        # Fetch all students with any bloom_progress entries
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT s.college_id
                FROM students s
                JOIN bloom_progress bp ON bp.student_id = s.id
                """
            )

        for row in rows:
            college_id = row["college_id"]
            try:
                async with pool.acquire() as conn:
                    progress_rows = await conn.fetch(
                        """
                        SELECT subject_code, topic, bloom_level, achieved, quiz_score
                        FROM bloom_progress bp
                        JOIN students s ON s.id = bp.student_id
                        WHERE s.college_id = $1
                        """,
                        college_id,
                    )
            except Exception as e:
                logger.debug(f"revision_scan progress fetch failed for {college_id}: {e}")
                continue

            for p in progress_rows:
                topic = p.get("topic") or ""
                subject_code = p.get("subject_code")
                score = float(p.get("quiz_score") or 0)
                achieved = bool(p.get("achieved"))

                # Simple rule: suggest revision if not achieved or score < 0.7
                if achieved and score >= 0.7:
                    continue

                message = (
                    f"Revision suggested for {topic or subject_code}: "
                    f"your recent quiz score indicates this topic needs another quick review."
                )

                await db.create_alert_if_not_exists(
                    student_college_id=college_id,
                    alert_type="revision",
                    subject_code=subject_code,
                    severity="notice",
                    message=message,
                )

        logger.info("revision_scan done")

    except Exception as e:
        logger.error(f"revision_scan failed: {e}", exc_info=True)


# ── Scheduler setup ───────────────────────────────────────────────────────────

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

        # Daily attendance scan at 6 PM IST
        _scheduler.add_job(
            attendance_cliff_scan,
            CronTrigger(hour=18, minute=0),
            id="attendance_cliff_scan",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Sentiment check at 9 PM IST
        _scheduler.add_job(
            sentiment_crash_scan,
            CronTrigger(hour=21, minute=0),
            id="sentiment_crash_scan",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Grade velocity scan at 8 PM IST
        _scheduler.add_job(
            grade_velocity_scan,
            CronTrigger(hour=20, minute=0),
            id="grade_velocity_scan",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Revision / spaced repetition scan at 7 PM IST
        _scheduler.add_job(
            revision_scan,
            CronTrigger(hour=19, minute=0),
            id="revision_scan",
            replace_existing=True,
            misfire_grace_time=3600,
        )

    return _scheduler


async def run_scan_now():
    """Trigger all proactive scans immediately — used by the manual trigger endpoint."""
    await attendance_cliff_scan()
    await sentiment_crash_scan()
    await grade_velocity_scan()
    await revision_scan()
