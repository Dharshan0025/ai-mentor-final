"""
memory_worker.py — Episodic Memory Async Observer

After each chat turn, this worker:
1. Sends the user message + AI response to a lightweight Groq call
2. Extracts structured facts about the student (struggles, patterns, goals)
3. Upserts those facts into the student_memory Supabase table

This runs as a fire-and-forget background task from the /chat endpoint.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from config import settings

logger = logging.getLogger(__name__)

MEMORY_EXTRACTION_PROMPT = """You are an educational AI observing a student-mentor conversation.
Extract 0-3 short factual observations about this student's LEARNING PATTERNS and KNOWLEDGE STATE.

Only extract facts that are clear from the conversation — do NOT infer or hallucinate.
Focus on: weak topics, strong topics, emotional state, learning preferences, specific goals.

User message: {message}
Mentor response (excerpt): {response_excerpt}
Student profile summary: {profile_summary}

Respond ONLY with a valid JSON array. Each object must have:
  "fact":         string  (max 80 chars, e.g. "Struggles with memory paging in OS")
  "category":     one of: weak_topic | strong_topic | learning_style | emotional | goal
  "subject_code": string or null
  "confidence":   float 0.0-1.0

Example: [{{"fact": "Struggles with dynamic programming", "category": "weak_topic", "subject_code": "CS701", "confidence": 0.85}}]

If nothing clear to extract, return: []
"""


async def extract_and_store_memories(
    *,
    student_id: str,
    session_id: str,
    message: str,
    response: str,
    student_profile: dict,
    db,
) -> None:
    """Fire-and-forget: extract facts from a chat turn and store them."""
    try:
        llm = ChatGroq(
            api_key=settings.groq_api_key,
            model="llama-3.1-8b-instant",  # smallest model — fast + cheap
            temperature=0.0,
            max_tokens=400,
        )

        profile_summary = _build_profile_summary(student_profile)
        response_excerpt = response[:500]  # only first 500 chars to save tokens

        prompt = MEMORY_EXTRACTION_PROMPT.format(
            message=message,
            response_excerpt=response_excerpt,
            profile_summary=profile_summary,
        )

        result = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = result.content.strip()

        # Parse JSON safely
        if "```json" in raw:
            raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw:
            raw = raw.split("```", 1)[1].split("```", 1)[0].strip()

        facts: list[dict] = json.loads(raw)
        if not isinstance(facts, list):
            return

        # Filter to high-confidence facts only
        quality_facts = [
            f for f in facts
            if isinstance(f, dict)
            and f.get("fact")
            and isinstance(f.get("confidence", 0), (int, float))
            and f.get("confidence", 0) >= 0.7
        ]

        if not quality_facts:
            return

        # Upsert to Supabase via db helper
        await _store_facts(db, student_id, session_id, quality_facts)
        logger.info(
            "Memory worker stored %d facts for student %s", len(quality_facts), student_id
        )

    except Exception as exc:
        # Memory is non-critical — never propagate
        logger.debug("Memory extraction skipped: %s", exc)


async def _store_facts(db, student_id: str, session_id: str, facts: list[dict]) -> None:
    """Insert facts into student_memory via raw Supabase pool."""
    try:
        pool = db._pool
        if pool is None:
            return

        rows = [
            {
                "student_id": student_id,
                "fact": f["fact"][:200],
                "category": f.get("category", "weak_topic"),
                "subject_code": f.get("subject_code"),
                "confidence": float(f.get("confidence", 0.8)),
                "source_session": session_id,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            for f in facts
        ]

        async with pool.acquire() as conn:
            # Use INSERT ... ON CONFLICT DO UPDATE so re-observed facts refresh confidence
            for row in rows:
                await conn.execute(
                    """
                    INSERT INTO student_memory
                        (student_id, fact, category, subject_code, confidence, source_session, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (student_id, fact)
                    DO UPDATE SET
                        confidence   = GREATEST(student_memory.confidence, EXCLUDED.confidence),
                        updated_at   = now(),
                        expires_at   = now() + interval '60 days'
                    """,
                    row["student_id"],
                    row["fact"],
                    row["category"],
                    row["subject_code"],
                    row["confidence"],
                    row["source_session"],
                    row["created_at"],
                    row["updated_at"],
                )
    except Exception as exc:
        logger.debug("Memory store DB write skipped: %s", exc)


async def get_recent_memories(db, student_id: str, limit: int = 10) -> list[dict]:
    """Retrieve the most recent non-expired facts for a student (used by RAG context)."""
    try:
        pool = db._pool
        if pool is None:
            return []
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT fact, category, subject_code, confidence
                FROM student_memory
                WHERE student_id = $1
                  AND (expires_at IS NULL OR expires_at > now())
                ORDER BY confidence DESC, updated_at DESC
                LIMIT $2
                """,
                student_id,
                limit,
            )
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.debug("Memory read skipped: %s", exc)
        return []


def _build_profile_summary(profile: dict) -> str:
    if not profile:
        return "No profile data."
    subjects = profile.get("subjects", [])
    risk_subjects = [s["name"] for s in subjects if s.get("status") == "risk"]
    return (
        f"Dept: {profile.get('department', 'CS')} | "
        f"Sem: {profile.get('semester', '?')} | "
        f"CGPA: {profile.get('currentCGPA', '?')} | "
        f"Risk subjects: {', '.join(risk_subjects) or 'none'}"
    )
