import os, json, uuid, asyncio, logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, UploadFile, File, Response, Form
from fastapi.responses import StreamingResponse
from schemas import *
from config import settings
from db import db
from services import get_student_profile

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/student/{student_id}/session/break-log")
async def log_break(student_id: str, body: dict):
    """Log when a student took a study break (for analytics)."""
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO session_break_log (student_id, break_at, session_minutes)
                   VALUES ($1, NOW(), $2)
                   ON CONFLICT DO NOTHING""",
                student_id, body.get("session_minutes", 45)
            )
        return {"ok": True}
    except Exception:
        return {"ok": True}  # Non-critical, never fail


@router.post("/student/{student_id}/study-room/create")
async def create_study_room(student_id: str, body: dict):
    """Create a new study room. Returns room_code to share with peers."""
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    room_code    = _secrets.token_urlsafe(6).upper()[:8]
    topic        = (body.get("topic") or "General Study").strip()
    subject_code = (body.get("subject_code") or "").strip()

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO study_rooms (room_code, creator_id, topic, subject_code)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (room_code) DO NOTHING
                """,
                room_code, student_id, topic, subject_code,
            )
        return {"room_code": room_code, "topic": topic, "subject_code": subject_code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/study-room/{room_code}")
async def get_study_room(room_code: str):
    """Get info and recent messages for a study room."""
    from db import get_pool

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            room = await conn.fetchrow(
                "SELECT room_code, creator_id, topic, subject_code, created_at FROM study_rooms WHERE room_code = $1",
                room_code.upper(),
            )
            if not room:
                raise HTTPException(status_code=404, detail="Study room not found")
            messages = await conn.fetch(
                """
                SELECT id, sender_id, sender_name, message, sent_at
                FROM study_room_messages
                WHERE room_code = $1
                ORDER BY sent_at ASC LIMIT 100
                """,
                room_code.upper(),
            )
        return {
            "room": dict(room),
            "messages": [dict(m) for m in messages],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/study-room/{room_code}/message")
async def post_room_message(room_code: str, body: dict):
    """Post a message to a study room (simple polling-based)."""
    from db import get_pool

    sender_id   = (body.get("sender_id") or "").strip()
    sender_name = (body.get("sender_name") or "Student").strip()
    message     = (body.get("message") or "").strip()

    if not sender_id or not message:
        raise HTTPException(status_code=400, detail="'sender_id' and 'message' are required")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            room = await conn.fetchval("SELECT room_code FROM study_rooms WHERE room_code = $1", room_code.upper())
            if not room:
                raise HTTPException(status_code=404, detail="Study room not found")
            row = await conn.fetchrow(
                """
                INSERT INTO study_room_messages (room_code, sender_id, sender_name, message)
                VALUES ($1, $2, $3, $4)
                RETURNING id, sent_at
                """,
                room_code.upper(), sender_id, sender_name[:100], message[:2000],
            )
            # Update last_activity
            await conn.execute(
                "UPDATE study_rooms SET last_activity = NOW() WHERE room_code = $1", room_code.upper()
            )
        return {"message_id": row["id"], "sent_at": str(row["sent_at"])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/student/{student_id}/analytics/attention")
async def record_attention_heartbeat(student_id: str, body: dict):
    """
    Receive a visibility heartbeat from the frontend.
    Body: { is_visible: bool, session_id?: str }
    """
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        return {"ok": True}  # silently ignore

    is_visible = bool(body.get("is_visible", True))
    session_id = body.get("session_id", "")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO session_attention_log (student_db_id, session_id, is_visible)
                VALUES ($1, $2, $3)
                """,
                student["db_id"], session_id or "", is_visible,
            )
    except Exception as e:
        logger.debug(f"Attention heartbeat save error (non-critical): {e}")

    return {"ok": True}


@router.get("/student/{student_id}/analytics/burnout")
async def get_burnout_analysis(student_id: str):
    """
    Analyze recent session patterns and break logs to detect burnout risk.
    Returns: { burnout_score, risk_level, signals, recommendation }
    """
    from db import get_pool
    from adaptive_engine import detect_burnout

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Get last 7 days of break logs
            break_rows = await conn.fetch(
                """
                SELECT session_minutes, break_at
                FROM session_break_log
                WHERE student_id = $1
                  AND break_at > NOW() - INTERVAL '7 days'
                ORDER BY break_at DESC
                """,
                student_id,
            )
            # Get attention data
            attention_rows = await conn.fetch(
                """
                SELECT is_visible, heartbeat_at
                FROM session_attention_log
                WHERE student_db_id = $1
                  AND heartbeat_at > NOW() - INTERVAL '1 day'
                ORDER BY heartbeat_at ASC
                """,
                student["db_id"],
            )
    except Exception:
        break_rows = []
        attention_rows = []

    break_log = [
        {"session_minutes": r["session_minutes"], "break_at": str(r["break_at"])}
        for r in break_rows
    ]
    attention_log = [
        {"is_visible": r["is_visible"], "ts": str(r["heartbeat_at"])}
        for r in attention_rows
    ]

    return detect_burnout(break_log, attention_log)


@router.post("/student/{student_id}/analytics/silence-alert")
async def handle_silence_alert(student_id: str, body: dict):
    """
    Called by frontend when student hasn't interacted for > 45s during lesson.
    Returns: { confusion_suspected, suggestion, directive }
    """
    from adaptive_engine import check_silence_confusion

    student = await db.get_student_by_college_id(student_id)
    if not student:
        return {"confusion_suspected": False, "suggestion": "Continue studying!"}

    silence_ms = int(body.get("silence_ms", 45000))
    topic      = body.get("topic", "")
    step       = int(body.get("step_num", 0))

    return check_silence_confusion(silence_ms, topic, step)


@router.get("/student/{student_id}/analytics/attention-score")
async def get_attention_score(student_id: str):
    """
    Compute attention score from recent heartbeats.
    Returns: { score, hidden_pct, total_heartbeats, recommendation }
    """
    from db import get_pool
    from adaptive_engine import estimate_attention_score

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT is_visible, heartbeat_at
                FROM session_attention_log
                WHERE student_db_id = $1
                  AND heartbeat_at > NOW() - INTERVAL '2 hours'
                ORDER BY heartbeat_at ASC
                """,
                student["db_id"],
            )
        heartbeats = [{"is_visible": r["is_visible"]} for r in rows]
        return estimate_attention_score(heartbeats)
    except Exception as e:
        return {"score": 1.0, "hidden_pct": 0, "total_heartbeats": 0, "recommendation": "Keep studying!"}


