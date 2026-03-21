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

@router.post("/student/{student_id}/career/resume-review")
async def review_resume(student_id: str, body: dict):
    """
    AI-powered resume review with ATS scoring.
    Body: { resume_text }
    Returns: { ats_score, strengths, gaps, improvements, keyword_suggestions }
    """
    import re as _re
    from groq import AsyncGroq

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    resume_text = (body.get("resume_text") or "").strip()
    if not resume_text:
        raise HTTPException(status_code=400, detail="'resume_text' is required")

    # Get career domain for context
    domain = "Software Developer"
    try:
        from agents.career import compute_career_profile
        profile = await db.get_student_full_profile(student_id)
        career_data = compute_career_profile(profile or {})
        domain = career_data.get("primary_domain", domain)
    except Exception:
        pass

    prompt = f"""You are an expert ATS-aware resume reviewer for Indian engineering students.

Target Career Domain: {domain}
Resume Text:
{resume_text[:4000]}

Perform a comprehensive ATS review. Return ONLY valid JSON:
{{
  "ats_score": <0-100, ATS compatibility score>,
  "overall_rating": "poor|fair|good|excellent",
  "summary": "<2-sentence overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "gaps": ["<gap 1>", "<gap 2>"],
  "improvements": [
    {{
      "section": "<Resume section>",
      "issue": "<what's wrong>",
      "fix": "<exact fix suggestion>"
    }}
  ],
  "keyword_suggestions": ["<keyword to add>", ...],
  "action_score": <0-100, how action-verb driven the bullets are>,
  "quantification_score": <0-100, how well achievements are quantified>
}}

Scoring criteria:
- ATS keywords present for {domain}
- Clear contact info and formatting
- Action verbs (Developed, Built, Designed, Implemented)
- Quantified achievements (%, numbers, scale)
- Relevant projects/internships
- Education section completeness
"""

    try:
        groq_client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an ATS expert. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()
        match = _re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group() if match else raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {str(e)}")

    result["domain"] = domain
    return result


@router.post("/student/{student_id}/career/interview-prep")
async def generate_interview_prep(student_id: str, body: dict):
    """
    Generate domain-specific interview Q&A.
    Body: { domain?: str, topics?: [str], count?: int }
    Returns: { domain, questions: [{ q, a, tips, difficulty }] }
    """
    import re as _re
    from groq import AsyncGroq

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    domain = (body.get("domain") or "").strip()
    topics = body.get("topics") or []
    count  = min(int(body.get("count", 10)), 15)

    if not domain:
        try:
            from agents.career import compute_career_profile
            profile = await db.get_student_full_profile(student_id)
            career_data = compute_career_profile(profile or {})
            domain = career_data.get("primary_domain", "Software Developer")
        except Exception:
            domain = "Software Developer"

    topics_str = f"Focus topics: {', '.join(topics)}" if topics else ""

    prompt = f"""You are an expert technical interview coach for Indian engineering students.
Career Domain: {domain}
{topics_str}

Generate {count} interview questions with expert answers.

Return ONLY valid JSON:
{{
  "questions": [
    {{
      "q":           "<interview question>",
      "a":           "<comprehensive answer>",
      "tips":        "<1-2 tips for answering this well in an interview>",
      "difficulty":  "easy|medium|hard",
      "type":        "technical|behavioral|system_design|coding_logic"
    }}
  ]
}}

Rules:
- Mix: 60% technical, 20% behavioral, 20% project/system design
- Answers: 3-5 sentences, concrete and structured
- Include STAR method hints for behavioral questions
- Reflect actual questions asked by Indian product companies in 2025
"""

    try:
        groq_client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an interview coach. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
        )
        raw = resp.choices[0].message.content.strip()
        match = _re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group() if match else raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Interview prep failed: {str(e)}")

    result["domain"] = domain
    return result


