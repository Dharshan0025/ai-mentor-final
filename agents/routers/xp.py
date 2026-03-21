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

@router.get("/student/{student_id}/xp")
async def get_student_xp(student_id: str):
    """
    Get full XP summary: total_xp, level, streak, level_progress,
    xp_to_next_level, badges [], recent_ledger [].
    Used by Progress dashboard and Tutor XP ring.
    """
    from gamification import get_gamification_agent

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    gami = await get_gamification_agent()
    summary = await gami.get_xp_summary(student["db_id"])
    summary["student_id"] = student_id
    return summary


@router.post("/student/{student_id}/xp/award")
async def award_student_xp(student_id: str, body: dict):
    """
    Award XP for an action. Checks badge conditions.
    Body: { action, amount?, metadata? }
    Returns: { total_xp, level, xp_gained, streak_days, level_progress, badges_earned }
    Valid actions: lesson_complete, checkpoint_pass, exam_complete, exam_perfect
    """
    from gamification import get_gamification_agent

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    action   = (body.get("action") or "lesson_complete").strip()
    amount   = body.get("amount")
    metadata = body.get("metadata") or {}

    gami = await get_gamification_agent()
    result = await gami.award_xp(
        student_db_id=student["db_id"],
        action=action,
        amount=int(amount) if amount is not None else None,
        metadata=metadata,
    )
    return result


