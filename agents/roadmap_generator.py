"""
Study Roadmap Generator — Phase 6 V10 Career Intelligence
Generates a personalized week-by-week study plan from SM-2 due topics,
PYQ high-weight topics, and exam date constraints.
"""
import json
import re
import logging
from groq import AsyncGroq
from config import settings

logger = logging.getLogger(__name__)


async def generate_roadmap(
    student_db_id: int,
    subjects: list[str],
    weeks: int = 4,
    exam_date: str = None,
    pool = None,
) -> dict:
    """
    Generate a personalized study roadmap.

    Args:
        subjects:   List of subject codes or names
        weeks:      Number of weeks to plan (default 4)
        exam_date:  Optional ISO date string for urgency shaping
        pool:       Asyncpg pool for SM-2 + PYQ data

    Returns:
        {
            weeks: [{ week, focus, topics: [{ name, priority, type, bloom_target, hours }] }],
            key_milestones: [{ week, milestone }],
            total_topics: int,
            exam_date: str
        }
    """
    # Gather SM-2 due + weak topics
    due_topics    = []
    pyq_topics    = []

    if pool:
        try:
            async with pool.acquire() as conn:
                # SM-2 weak areas (ease < 2.3 or few reps)
                rows = await conn.fetch(
                    """
                    SELECT concept, ease_factor, repetitions, subject_code
                    FROM student_learning_memory
                    WHERE student_db_id = $1
                      AND (ease_factor < 2.3 OR repetitions < 2)
                    ORDER BY ease_factor ASC
                    LIMIT 30
                    """,
                    student_db_id,
                )
                due_topics = [
                    {"topic": r["concept"], "subject": r["subject_code"], "type": "review", "priority": "high"}
                    for r in rows
                    if not subjects or r["subject_code"] in subjects
                ]

                # PYQ high-weight topics
                pyq_rows = await conn.fetch(
                    """
                    SELECT analysis_json, subject_code
                    FROM pyq_analysis
                    WHERE student_db_id = $1
                    ORDER BY created_at DESC
                    LIMIT 5
                    """,
                    student_db_id,
                )
                for pr in pyq_rows:
                    try:
                        analysis = pr["analysis_json"] or {}
                        topics = analysis.get("topics", [])
                        for t in topics:
                            if t.get("weight_pct", 0) >= 12:
                                pyq_topics.append({
                                    "topic":    t["name"],
                                    "subject":  pr["subject_code"],
                                    "type":     "pyq_priority",
                                    "priority": "high" if t["weight_pct"] >= 20 else "medium",
                                    "weight":   t["weight_pct"],
                                })
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Roadmap data fetch error: {e}")

    # Build LLM prompt
    context_block = ""
    if due_topics:
        context_block += f"\nWeak/Due Topics (SM-2): {json.dumps(due_topics[:15], indent=0)}"
    if pyq_topics:
        context_block += f"\nHigh-Weight PYQ Topics: {json.dumps(pyq_topics[:15], indent=0)}"
    if not context_block:
        context_block = f"\nSubjects to cover: {', '.join(subjects)}"

    exam_note = f"\nExam date: {exam_date} — prioritize urgency!" if exam_date else ""

    prompt = f"""You are an expert academic coach for engineering students.
Create a personalized {weeks}-week study roadmap.

Subjects: {', '.join(subjects) if subjects else 'All semester subjects'}
{context_block}
{exam_note}

Generate a structured roadmap. Return ONLY valid JSON:
{{
  "weeks": [
    {{
      "week": 1,
      "focus": "<theme for this week>",
      "topics": [
        {{
          "name": "<topic>",
          "subject": "<subject code>",
          "type": "review|new|pyq_priority|practice",
          "bloom_target": <2-5>,
          "hours": <1-4>,
          "priority": "high|medium|low"
        }}
      ],
      "milestone": "<what should be achieved by end of this week>"
    }}
  ],
  "key_milestones": [
    {{ "week": <int>, "milestone": "<achievement>" }}
  ],
  "study_tips": ["<tip 1>", "<tip 2>", "<tip 3>"]
}}

Rules:
- Prioritize: high priority SM-2 weak topics FIRST in week 1
- PYQ high-weight topics go in weeks 2-3 (peak exam prep zone)
- Practice/revision in final week
- Max 5 topics per week (realistic load)
- bloom_target: week 1-2 = understanding (2-3), week 3-4 = apply/analyze (3-4)
- hours per topic: 1=quick review, 2=standard, 3=deep study, 4=full conquest
"""

    try:
        groq = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert academic coach. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
        )
        raw = resp.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group() if match else raw)
    except Exception as e:
        logger.error(f"Roadmap LLM error: {e}")
        # Fallback: distribute topics evenly across weeks
        all_topics = [t["topic"] for t in (due_topics + pyq_topics)]
        per_week = max(1, len(all_topics) // max(weeks, 1))
        result = {
            "weeks": [
                {
                    "week": w + 1,
                    "focus": f"Week {w + 1} Study",
                    "topics": [
                        {"name": t, "subject": "N/A", "type": "review",
                         "bloom_target": 3, "hours": 2, "priority": "medium"}
                        for t in all_topics[w * per_week: (w + 1) * per_week]
                    ],
                    "milestone": f"Complete week {w + 1} topics",
                }
                for w in range(weeks)
            ],
            "key_milestones": [{"week": weeks, "milestone": "All topics reviewed"}],
            "study_tips": ["Review notes daily", "Practice past questions", "Use spaced repetition"],
        }

    # Count total topics
    total = sum(len(w.get("topics", [])) for w in result.get("weeks", []))
    result["total_topics"]  = total
    result["weeks_planned"] = weeks
    result["exam_date"]     = exam_date
    result["subjects"]      = subjects

    return result


async def save_roadmap(pool, student_db_id: int, roadmap: dict, subjects: list, weeks: int, exam_date: str = None) -> int:
    """Save generated roadmap to DB. Returns row ID."""
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            """
            INSERT INTO study_roadmaps (student_db_id, roadmap_json, subjects, weeks_count, exam_date)
            VALUES ($1, $2::jsonb, $3::jsonb, $4, $5)
            RETURNING id
            """,
            student_db_id,
            json.dumps(roadmap),
            json.dumps(subjects),
            weeks,
            exam_date,
        )
    return row_id


async def get_latest_roadmap(pool, student_db_id: int) -> dict | None:
    """Fetch the most recent roadmap for a student."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT roadmap_json, generated_at
            FROM study_roadmaps
            WHERE student_db_id = $1
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            student_db_id,
        )
    if not row:
        return None
    data = dict(row["roadmap_json"])
    data["generated_at"] = str(row["generated_at"])
    return data
