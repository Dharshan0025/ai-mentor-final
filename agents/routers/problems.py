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

@router.post("/student/{student_id}/problems/generate")
async def generate_student_problems(student_id: str, body: ProblemGenRequest):
    """Generate practice problems for a topic and save to problem bank."""
    # Get subject name
    subject_name = body.subject_code
    try:
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT name FROM subjects WHERE code = $1", body.subject_code
            )
            if row:
                subject_name = row["name"]
    except Exception:
        pass

    problems = await generate_problems(
        subject_name=subject_name,
        topic=body.topic,
        count=min(body.count, 10),
        mode=body.mode,
        difficulty=body.difficulty,
    )

    # Save to student_problem_bank
    saved_ids = []
    try:
        async with db.pool.acquire() as conn:
            for p in problems:
                row = await conn.fetchrow(
                    """INSERT INTO student_problem_bank
                       (student_id, subject_code, topic, type, question, options,
                        correct_index, correct_answer, hint, bloom_level, difficulty,
                        tags, explanation, mode)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                       RETURNING id""",
                    student_id, body.subject_code, body.topic,
                    p["type"], p["question"],
                    json.dumps(p.get("options", [])),
                    p.get("correct_index", 0), p.get("correct_answer", ""),
                    p.get("hint", ""), p.get("bloom_level", 3),
                    p.get("difficulty", body.difficulty),
                    json.dumps(p.get("tags", [])),
                    p.get("explanation", ""), body.mode
                )
                saved_ids.append(str(row["id"]))
    except Exception as e:
        logging.warning(f"[problems] Could not save to DB: {e}")

    return {"problems": problems, "saved_count": len(saved_ids)}


@router.get("/student/{student_id}/problems")
async def get_student_problems(
    student_id: str,
    subject_code: str = None,
    topic: str = None,
    limit: int = 20,
):
    """Get student's saved problem bank."""
    try:
        async with db.pool.acquire() as conn:
            query = """SELECT id, subject_code, topic, type, question, options,
                              correct_index, correct_answer, hint, bloom_level,
                              difficulty, tags, explanation, mode, attempted,
                              correct, created_at
                       FROM student_problem_bank
                       WHERE student_id = $1"""
            params = [student_id]
            if subject_code:
                params.append(subject_code)
                query += f" AND subject_code = ${len(params)}"
            if topic:
                params.append(topic)
                query += f" AND topic = ${len(params)}"
            query += f" ORDER BY created_at DESC LIMIT {limit}"
            rows = await conn.fetch(query, *params)
            problems = [dict(r) for r in rows]
            for p in problems:
                p["options"] = json.loads(p["options"]) if isinstance(p["options"], str) else p["options"]
                p["tags"]    = json.loads(p["tags"]) if isinstance(p["tags"], str) else p["tags"]
            return {"problems": problems}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/student/{student_id}/problems/{problem_id}/attempt")
async def attempt_problem(student_id: str, problem_id: str, body: dict):
    """Record a problem attempt (correct/incorrect)."""
    is_correct = body.get("is_correct", False)
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                """UPDATE student_problem_bank
                   SET attempted = true, correct = $1, attempted_at = NOW()
                   WHERE id = $2 AND student_id = $3""",
                is_correct, problem_id, student_id
            )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/student/{student_id}/problems/{problem_id}")
async def delete_problem(student_id: str, problem_id: str):
    """Delete a problem from student's bank."""
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM student_problem_bank WHERE id = $1 AND student_id = $2",
                problem_id, student_id
            )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


