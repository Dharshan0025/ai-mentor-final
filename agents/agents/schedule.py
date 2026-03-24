"""
AI-Mentor — Enhanced Schedule Agent (v2)
LLM-powered. Groq generates a structured JSON weekly plan from real ERP data.
Inputs: subjects (bloom, grade, attendance), syllabus coverage, overdue assignments, Learning DNA.
Output: structured 7-day plan with per-slot topic, bloom badge, duration, pomodoro count, study tip.
"""
from utils.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings
import logging
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ── Bloom display names ───────────────────────────────────────────────────────
BLOOM_NAMES = {1: "Remember", 2: "Understand", 3: "Apply", 4: "Analyze", 5: "Evaluate", 6: "Create"}


# ── Schedule generation prompt ───────────────────────────────────────────────
SCHEDULE_JSON_PROMPT = """You are an expert academic study planner AI for a college student in India.

Generate a PERSONALIZED 7-day study schedule as a JSON array. Each day must have realistic, specific study sessions.

Student context:
{context}

Output ONLY a valid JSON array (no markdown, no explanation) with this exact structure:
[
  {{
    "day": "Mon",
    "date": "03 Mar",
    "slots": [
      {{
        "time": "08:00",
        "subject": "Operating Systems",
        "subject_code": "CS702",
        "topic": "Process Scheduling — Round Robin vs Priority",
        "type": "risk",
        "duration_min": 90,
        "bloom_level": 2,
        "pomodoro_count": 3,
        "study_tip": "Draw the scheduling Gantt chart by hand before reading theory"
      }}
    ]
  }}
]

Rules:
1. Generate all 7 days: Mon, Tue, Wed, Thu, Fri, Sat, Sun
2. Sunday is a lighter day (1-2 slots, revision only)
3. MUST use the student's actual subject names and codes exactly
4. Session start times must reflect the student's peak study hour ({peak_hour}:00)
5. Prioritize: risk subjects 40% → watch 30% → safe 20% → rest 10%
6. Topics must be SPECIFIC to the subject (not generic "study SUBJECT")
7. Pomodoro count = ceil(duration / 25)
8. Each study tip must be actionable and subject-specific
9. type must be exactly: "risk", "watch", or "safe"
10. bloom_level must match student's current level for that subject
11. No overlapping time slots on the same day
12. Max 5 slots per weekday, 2 on Sunday
"""


# ── Per-subject tip prompt ────────────────────────────────────────────────────
SUBJECT_TIP_PROMPT = """Give ONE specific, actionable study tip for a student struggling with {subject_name}.
Their current grade is {grade}, Bloom level {bloom}/6, attendance {att}%.
Key weakness: {weakness}
Response: one sentence, max 20 words, no filler phrases."""


# ── Context builder ───────────────────────────────────────────────────────────

def _build_llm_context(
    profile: dict,
    learning_dna: dict,
    peak_hour: int,
) -> str:
    subjects = profile.get("subjects", profile.get("subject_profiles", []))
    risk   = [s for s in subjects if s.get("status") == "risk"]
    watch  = [s for s in subjects if s.get("status") == "watch"]
    safe   = [s for s in subjects if s.get("status") == "safe"]
    exam_days = profile.get("examDays") or profile.get("exam_days") or "unknown"

    def fmt(lst):
        return ", ".join(
            f"{s.get('name')} [{s.get('code','?')}] grade={s.get('grade','?')} att={s.get('live_attendance') or s.get('attendance','?')}% bloom={s.get('bloomLevel') or s.get('bloom_level',1)}/6"
            for s in lst
        ) or "None"

    # Syllabus coverage gaps
    coverage = profile.get("syllabusCoverage", profile.get("syllabus_coverage", []))
    low_cov = [
        f"{c.get('subject_name','?')} {c.get('unit_title','?')} ({c.get('coverage_pct',0)}% covered)"
        for c in coverage
        if float(c.get("coverage_pct") or 0) < 60
    ]

    # Overdue assignments
    assignments = profile.get("assignments", [])
    overdue = [
        f"{a.get('subject_code','?')}: {a.get('title','?')}"
        for a in assignments
        if a.get("submission_status") == "not_submitted"
    ]

    # Learning DNA
    weak_raw = learning_dna.get("weak_topics") or []
    weak_names = [
        w if isinstance(w, str) else str(w.get("topic") or w.get("subject_code") or "")
        for w in weak_raw[:4]
    ]
    pref_style = learning_dna.get("preferred_style") or "balanced"

    lines = [
        f"Student: {profile.get('name', 'Student')} | Semester {profile.get('semester')} | CGPA {profile.get('currentCGPA')}",
        f"Exam in: {exam_days} days",
        f"Peak study hour: {peak_hour}:00",
        f"Learning style: {pref_style}",
        f"",
        f"AT-RISK subjects (must prioritize daily): {fmt(risk)}",
        f"WATCH subjects: {fmt(watch)}",
        f"SAFE subjects: {fmt(safe)}",
    ]
    if low_cov:
        lines.append(f"Low syllabus coverage (self-study needed): {'; '.join(low_cov[:4])}")
    if overdue:
        lines.append(f"Overdue assignments: {', '.join(overdue[:4])}")
    if weak_names:
        lines.append(f"Known weak topics from learning history: {', '.join(weak_names)}")
    lines.append(f"Study streak: {profile.get('studyStreak', profile.get('study_streak', 0))} days")

    return "\n".join(lines)


# ── Deterministic fallback ────────────────────────────────────────────────────
_TOPIC_BANKS: dict[str, list[str]] = {
    "operating system": ["Process Scheduling", "Deadlock", "Memory Management", "Page Replacement", "File Systems"],
    "database": ["ER Diagrams", "SQL Joins", "Transactions & ACID", "Indexing", "Concurrency Control"],
    "network": ["TCP/IP Model", "Routing Protocols", "Network Security", "DNS & DHCP", "Flow Control"],
    "machine learning": ["Supervised Learning", "Neural Networks", "Feature Engineering", "Model Evaluation", "Overfitting"],
    "software engineering": ["SDLC Models", "UML Diagrams", "Agile & Scrum", "Testing Strategies", "Design Patterns"],
    "cloud": ["Deployment Models", "Virtualization", "AWS Core Services", "Load Balancing", "Serverless"],
    "data structure": ["Arrays & Linked Lists", "Trees & Graphs", "Sorting Algorithms", "Hashing", "Dynamic Programming"],
    "algorithm": ["Time Complexity", "Greedy Algorithms", "Divide & Conquer", "Graph Traversal", "DP Techniques"],
}
_BLOOM_SUFFIX = {1: "— definitions & recall", 2: "— concept explanation", 3: "— practice problems", 4: "— exam pattern analysis", 5: "— critical evaluation", 6: "— design & case study"}

def _fallback_topic(subject: dict, idx: int = 0) -> str:
    name = (subject.get("name") or "").lower()
    bloom = subject.get("bloomLevel") or subject.get("bloom_level") or 2
    for kw, bank in _TOPIC_BANKS.items():
        if kw in name:
            return f"{bank[idx % len(bank)]} {_BLOOM_SUFFIX.get(bloom, '')}"
    return f"Core concepts & revision {_BLOOM_SUFFIX.get(bloom, '')}"

def _deterministic_fallback(profile: dict, peak_hour: int) -> list[dict]:
    subjects = profile.get("subjects", profile.get("subject_profiles", []))
    risk  = [s for s in subjects if s.get("status") == "risk"]
    watch = [s for s in subjects if s.get("status") == "watch"]
    safe  = [s for s in subjects if s.get("status") == "safe"]
    days  = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today = datetime.now()
    week  = []
    for i, day in enumerate(days):
        date   = (today + timedelta(days=i)).strftime("%d %b")
        slots  = []
        if day == "Sun":
            week.append({"day": day, "date": date, "slots": [{
                "time": f"{peak_hour:02d}:00", "subject": (risk or watch or safe or [{}])[0].get("name", "Revision"),
                "subject_code": (risk or watch or safe or [{}])[0].get("code", ""),
                "topic": "Light revision & past paper review", "type": "safe",
                "duration_min": 60, "bloom_level": 2, "pomodoro_count": 2, "study_tip": "Review previous mistakes only."
            }]})
            continue
        h = peak_hour
        for j, s in enumerate(risk[:2]):
            slots.append({"time": f"{h:02d}:00", "subject": s.get("name"), "subject_code": s.get("code",""),
                "topic": _fallback_topic(s, i), "type": "risk", "duration_min": 90, "bloom_level": s.get("bloomLevel") or s.get("bloom_level",2), "pomodoro_count": 4, "study_tip": "Focus on past exam question patterns."})
            h += 2
        if watch:
            s = watch[i % len(watch)]
            slots.append({"time": f"{h:02d}:00", "subject": s.get("name"), "subject_code": s.get("code",""),
                "topic": _fallback_topic(s, i), "type": "watch", "duration_min": 60, "bloom_level": s.get("bloomLevel") or s.get("bloom_level",2), "pomodoro_count": 2, "study_tip": "Solve 3 textbook problems before moving on."})
            h += 1
        if safe:
            s = safe[i % len(safe)]
            slots.append({"time": f"{h:02d}:00", "subject": s.get("name"), "subject_code": s.get("code",""),
                "topic": "Revision & past papers", "type": "safe", "duration_min": 45, "bloom_level": s.get("bloomLevel") or s.get("bloom_level",3), "pomodoro_count": 2, "study_tip": "Self-quiz before reading notes."})
        week.append({"day": day, "date": date, "slots": slots})
    return week


# ── LLM schedule generator ────────────────────────────────────────────────────

async def generate_ai_schedule(
    profile: dict,
    learning_dna: dict,
) -> list[dict]:
    """
    Ask Groq to generate a personalized 7-day schedule as JSON.
    Falls back to deterministic generator if LLM fails.
    """
    peak_hour = learning_dna.get("peak_hour") or 8
    context = _build_llm_context(profile, learning_dna, peak_hour)

    llm, provider = get_llm(temperature=0.4, max_tokens=6000)

    prompt = SCHEDULE_JSON_PROMPT.format(context=context, peak_hour=peak_hour)

    try:
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = result.content.strip()

        # Strip markdown code fences if present
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        week = json.loads(raw)

        # Validate structure
        if not isinstance(week, list) or len(week) == 0:
            raise ValueError("LLM returned empty or non-list schedule")

        # Ensure required keys exist in each slot
        today = datetime.now()
        days_order = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        date_map = {days_order[i]: (today + timedelta(days=i)).strftime("%d %b") for i in range(7)}
        for day_obj in week:
            day_obj.setdefault("date", date_map.get(day_obj.get("day","Mon"), ""))
            for slot in day_obj.get("slots", []):
                slot.setdefault("pomodoro_count", max(1, round((slot.get("duration_min", 60)) / 25)))
                slot.setdefault("bloom_level", 2)
                slot.setdefault("study_tip", "Stay focused and take short breaks.")
                slot.setdefault("subject_code", "")

        logger.info("✅ LLM schedule generated successfully")
        return week, provider

    except Exception as e:
        logger.warning(f"LLM schedule generation failed ({e}), using deterministic fallback")
        return _deterministic_fallback(profile, peak_hour), "deterministic"


# ── Per-subject tips (LLM) ────────────────────────────────────────────────────

async def generate_subject_tips(
    subjects: list[dict],
    learning_dna: dict,
) -> dict[str, str]:
    """
    Generate one specific study tip per at-risk/watch subject using LLM.
    Returns {subject_code: tip_text}
    """
    llm, provider = get_llm(temperature=0.5, max_tokens=600)
    tips: dict[str, str] = {}
    priority = [s for s in subjects if s.get("status") in ("risk", "watch")]
    weak_raw = learning_dna.get("weak_topics") or []
    weak_set = set(
        w if isinstance(w, str) else str(w.get("topic") or w.get("subject_code") or "")
        for w in weak_raw
    )

    for s in priority[:4]:  # cap at 4 LLM calls
        code = s.get("code") or s.get("subject_code") or ""
        name = s.get("name") or s.get("subject_name") or ""
        weakness = next((w for w in weak_set if code.lower() in w.lower() or name.lower()[:4] in w.lower()), "general understanding")
        try:
            prompt = SUBJECT_TIP_PROMPT.format(
                subject_name=name,
                grade=s.get("grade", "?"),
                bloom=s.get("bloomLevel") or s.get("bloom_level", 2),
                att=s.get("live_attendance") or s.get("attendance", "?"),
                weakness=weakness,
            )
            res = await llm.ainvoke([HumanMessage(content=prompt)])
            tips[code] = res.content.strip().strip('"').strip(".")
        except Exception:
            tips[code] = f"Focus on past exam questions and practice {name} problems daily."

    return tips


# ── Rationale builder ─────────────────────────────────────────────────────────

def build_schedule_rationale(profile: dict, learning_dna: dict | None = None) -> str:
    subjects = profile.get("subjects", profile.get("subject_profiles", []))
    risk  = [s.get("name") for s in subjects if s.get("status") == "risk"]
    watch = [s.get("name") for s in subjects if s.get("status") == "watch"]
    exam  = profile.get("examDays") or profile.get("exam_days") or "?"
    dna   = learning_dna or {}
    peak  = dna.get("peak_hour")
    style = dna.get("preferred_style") or "balanced"

    parts = []
    if risk:
        parts.append(f"**{', '.join(risk[:2])}** prioritized as at-risk")
    if watch:
        parts.append(f"**{', '.join(watch[:2])}** in watch zone")
    if peak is not None:
        parts.append(f"sessions anchored to your **{peak}:00** peak study hour")
    if style and style != "balanced":
        parts.append(f"**{style}** learning style applied")

    base = f"Schedule generated for exam in **{exam} days**"
    return (base + " — " + "; ".join(parts) + ".") if parts else base + "."


# ── Subject breakdown ─────────────────────────────────────────────────────────

def build_subject_breakdown(week: list[dict]) -> dict[str, dict]:
    """Aggregate hours per subject across the week."""
    breakdown: dict[str, dict] = {}
    for day in week:
        for slot in day.get("slots", []):
            code = slot.get("subject_code") or slot.get("subject", "?")
            name = slot.get("subject", code)
            if code not in breakdown:
                breakdown[code] = {"subject": name, "subject_code": code, "type": slot.get("type","safe"), "total_min": 0, "sessions": 0}
            breakdown[code]["total_min"] += slot.get("duration_min", 60)
            breakdown[code]["sessions"]  += 1
    # Add hours
    for v in breakdown.values():
        v["total_hours"] = round(v["total_min"] / 60, 1)
    return breakdown


# ── Backward-compat wrapper for /schedule endpoint ────────────────────────────

def generate_week_schedule(profile: dict, learning_dna: dict | None = None) -> list[dict]:
    """Sync deterministic wrapper (used as fallback by main.py)."""
    peak = (learning_dna or {}).get("peak_hour") or 8
    return _deterministic_fallback(profile, peak)


# ── LangGraph-compatible node ─────────────────────────────────────────────────
async def schedule_node(state: dict) -> dict:
    """
    LangGraph node wrapper for the schedule agent.
    Calls generate_ai_schedule and returns a chat-friendly summary.
    """
    profile = state.get("student_profile", {})
    student_id = state.get("student_id")

    # Try to load learning DNA
    learning_dna = state.get("learning_dna") or {}
    if student_id:
        try:
            from db import db
            if not learning_dna:
                dna = await db.get_learning_dna(student_id)
                learning_dna = dna or {}
        except Exception as e:
            logger.warning(f"Learning DNA load skipped in schedule_node: {e}")

    try:
        week, provider = await generate_ai_schedule(profile, learning_dna)
    except Exception as e:
        logger.error(f"schedule_node generate_ai_schedule failed ({e}), using fallback")
        peak = learning_dna.get("peak_hour") or 8
        week = _deterministic_fallback(profile, peak)
        provider = "deterministic"

    rationale = build_schedule_rationale(profile, learning_dna)
    breakdown = build_subject_breakdown(week)

    # Build a concise text summary for the chat response
    risk_subjects = [s.get("name", "?") for s in profile.get("subjects", []) if s.get("status") == "risk"]
    risk_line = f"\n\n**At-risk subjects** prioritized: {', '.join(risk_subjects)}" if risk_subjects else ""

    today_slots = week[0].get("slots", []) if week else []
    today_line = ""
    if today_slots:
        slot_strs = [f"**{s.get('time')}** — {s.get('subject')}: {s.get('topic')} ({s.get('duration_min')}min)" for s in today_slots[:3]]
        today_line = "\n\n**Today's sessions:**\n" + "\n".join(slot_strs)

    response_text = f"{rationale}{risk_line}{today_line}\n\nThe full 7-day plan is available in your **Schedule** tab."

    return {
        **state,
        "schedule_output": response_text,
        "primary_agent": "schedule",
        "model_used": provider,
        "citations": [
            {"label": "7-day personalized study plan", "source": "Schedule Agent"},
            {"label": f"Exam in {profile.get('examDays', '?')} days", "source": "ERP Calendar"},
        ],
    }

