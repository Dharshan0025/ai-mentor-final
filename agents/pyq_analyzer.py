"""
PYQ Analyzer Agent — Phase 5 V7 Knowledge Engine
Extracts topics, Bloom levels, and exam weights from Past Year Question papers.
Uses Groq LLM for semantic analysis.
"""
import json
import re
import logging
from groq import AsyncGroq
from config import settings

logger = logging.getLogger(__name__)

# Bloom's taxonomy descriptors for the LLM
BLOOM_DESCRIPTORS = {
    1: "Remember — recall facts, list, define, name",
    2: "Understand — explain, describe, summarize, interpret",
    3: "Apply — use, solve, compute, implement, demonstrate",
    4: "Analyze — compare, differentiate, examine, break down",
    5: "Evaluate — judge, argue, defend, critique, justify",
    6: "Create — design, construct, develop, formulate",
}


async def analyze_pyq(text: str, subject_code: str) -> dict:
    """
    Analyze a Past Year Question paper.
    Returns:
        {
            topics: [{ name, bloom_level, bloom_desc, frequency, weight_pct, likely_exam }],
            total_questions: int,
            topics_count: int,
            high_weight_topics: [str],
            summary: str
        }
    """
    if not text or not text.strip():
        return {"topics": [], "total_questions": 0, "topics_count": 0}

    prompt = f"""You are an expert exam analyst for engineering students.
Analyze the following Past Year Question paper for subject code: {subject_code}

QUESTION PAPER:
{text[:6000]}

Extract all distinct topics/concepts tested. For each topic:
- Count how many questions test it (frequency)
- Assign Bloom's Taxonomy level (1-6)
- Calculate approximate exam weight percentage

Return ONLY valid JSON (no markdown, no explanation):
{{
  "total_questions": <int>,
  "topics": [
    {{
      "name": "<topic name>",
      "bloom_level": <1-6>,
      "frequency": <int, how many questions cover this topic>,
      "weight_pct": <float, 0-100, percentage of marks this topic carries>,
      "likely_exam": <true|false, if this topic is high-probability for future exams>
    }}
  ],
  "summary": "<2-sentence analysis of the paper pattern>"
}}

Rules:
- bloom_level 1=Remember, 2=Understand, 3=Apply, 4=Analyze, 5=Evaluate, 6=Create
- weight_pct values must sum to approximately 100
- Sort topics by weight_pct descending
- Merge very similar topics into one
- Be specific: "Binary Search Trees" not just "Trees"
"""

    try:
        groq = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert exam analyst. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()

        # Extract JSON from response
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            result = json.loads(raw)

        # Normalize and enrich topics
        topics = result.get("topics", [])
        for t in topics:
            bloom = int(t.get("bloom_level", 2))
            t["bloom_level"] = max(1, min(6, bloom))
            t["bloom_desc"] = BLOOM_DESCRIPTORS.get(t["bloom_level"], "")
            t["weight_pct"] = round(float(t.get("weight_pct", 0)), 1)
            t["frequency"] = int(t.get("frequency", 1))
            t["likely_exam"] = bool(t.get("likely_exam", t["weight_pct"] > 10))

        # Sort by weight descending
        topics.sort(key=lambda x: x["weight_pct"], reverse=True)

        high_weight = [t["name"] for t in topics if t["weight_pct"] >= 15]

        return {
            "topics": topics,
            "total_questions": int(result.get("total_questions", len(topics))),
            "topics_count": len(topics),
            "high_weight_topics": high_weight,
            "summary": result.get("summary", ""),
        }

    except Exception as e:
        logger.error(f"PYQ analysis error: {e}", exc_info=True)
        # Fallback: basic word frequency analysis
        return {
            "topics": [],
            "total_questions": 0,
            "topics_count": 0,
            "high_weight_topics": [],
            "summary": f"Analysis failed: {str(e)}",
            "error": str(e),
        }


async def save_pyq_analysis(
    pool, student_db_id: int, subject_code: str,
    raw_text: str, analysis: dict, title: str = None,
) -> int:
    """Save a PYQ analysis result to the database. Returns the inserted row ID."""
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            """
            INSERT INTO pyq_analysis
                (student_db_id, subject_code, title, raw_text, analysis_json,
                 total_questions, topics_count)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            RETURNING id
            """,
            student_db_id,
            subject_code,
            title or f"{subject_code} PYQ Analysis",
            raw_text[:5000],
            json.dumps(analysis),
            analysis.get("total_questions", 0),
            analysis.get("topics_count", 0),
        )
    return row_id


async def get_pyq_history(pool, student_db_id: int, limit: int = 10) -> list[dict]:
    """Fetch past PYQ analyses for a student."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, subject_code, title, total_questions, topics_count, created_at
            FROM pyq_analysis
            WHERE student_db_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            student_db_id, limit,
        )
    return [dict(r) for r in rows]
