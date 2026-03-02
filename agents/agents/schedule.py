"""
AI-Mentor — Schedule Agent
Handles: personalized study plan generation, time management advice,
         risk-priority scheduling, exam countdown planning.
LLM: Groq (deterministic, structured output)
"""
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


SCHEDULE_SYSTEM = """You are the Schedule Agent for an AI academic mentor.

Your role:
- Build a personalized weekly study plan based on subject risk priority
- Balance study load (no more than 8 hours/day)
- Prioritize high-risk subjects (grade < 6.0 OR attendance < 75%)
- Follow Pomodoro technique: 25-min focus + 5-min break blocks

Study priority rules:
1. At-risk subjects → 40% of study time
2. Watch subjects → 30% of study time
3. Safe subjects → 20% of study time
4. Rest/wellness → 10%

Student profile:
{student_profile}

When generating a schedule:
- Use structured markdown tables
- Show time blocks (09:00, 09:30, etc.)
- Label each block with subject, topic, and type (risk/watch/safe)
- Suggest specific topics to study (from their Bloom level gaps)
- Keep exam countdown front and centre

Rules:
- Maximum 350 words
- Be specific: "2 hours of OS Process Scheduling" not "study CS"
- If Pomodoro → 4 blocks per 2-hour session"""


def schedule_node(state: dict) -> dict:
    """Schedule agent — risk-priority study plan generation."""
    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.3,
        max_tokens=600,
    )

    profile = state.get("student_profile", {})
    system_prompt = SCHEDULE_SYSTEM.format(
        student_profile=_format_schedule_context(profile)
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["message"]),
    ]

    result = llm.invoke(messages)

    return {
        **state,
        "schedule_output": result.content,
        "model_used": settings.groq_model,
    }


def _format_schedule_context(profile: dict) -> str:
    """Format student schedule context for LLM."""
    if not profile:
        return "Semester 7, exam in 18 days, 3 at-risk subjects."

    subjects = profile.get("subjects", [])
    risk    = [s for s in subjects if s.get("status") == "risk"]
    watch   = [s for s in subjects if s.get("status") == "watch"]
    safe    = [s for s in subjects if s.get("status") == "safe"]

    def fmt_subj(subj_list):
        return [f"{s.get('name')} (Bloom {s.get('bloomLevel')}/6)" for s in subj_list]

    return f"""
Semester: {profile.get('semester')}
Exam in: {profile.get('examDays', 18)} days
CGPA: {profile.get('currentCGPA')} → Target: {profile.get('predictedCGPA')}

At-risk subjects: {fmt_subj(risk)}
Watch subjects: {fmt_subj(watch)}
Safe subjects: {fmt_subj(safe)}

Study streak: {profile.get('studyStreak', 0)} days
"""


def generate_week_schedule(profile: dict) -> list[dict]:
    """
    Deterministic schedule generator.
    Returns a structured 7-day plan matching the Schedule page format.
    """
    subjects = profile.get("subjects", [])
    risk    = [s for s in subjects if s.get("status") == "risk"]
    watch   = [s for s in subjects if s.get("status") == "watch"]
    safe    = [s for s in subjects if s.get("status") == "safe"]

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today = datetime.now()

    week_plan = []
    for i, day_name in enumerate(days):
        day_date = (today + timedelta(days=i)).strftime("%d %b")
        slots = []

        # Morning: risk subjects
        if risk:
            for j, subj in enumerate(risk[:2]):
                slots.append({
                    "time": f"0{8+j}:00",
                    "subject": subj.get("name", "Subject"),
                    "topic": _suggest_topic(subj),
                    "type": "risk",
                    "duration_min": 90,
                })

        # Midday: watch subjects
        if watch:
            subj = watch[i % max(len(watch), 1)]
            slots.append({
                "time": "11:00",
                "subject": subj.get("name", "Subject"),
                "topic": _suggest_topic(subj),
                "type": "watch",
                "duration_min": 60,
            })

        # Afternoon: safe / revision
        if safe:
            subj = safe[i % max(len(safe), 1)]
            slots.append({
                "time": "14:00",
                "subject": subj.get("name", "Subject"),
                "topic": "Revision & past papers",
                "type": "safe",
                "duration_min": 60,
            })

        week_plan.append({
            "day": day_name,
            "date": day_date,
            "slots": slots,
        })

    return week_plan


def _suggest_topic(subject: dict) -> str:
    """Suggest a focused topic based on Bloom level."""
    bloom = subject.get("bloomLevel", 2)
    name = subject.get("name", "Subject")
    bloom_topics = {
        1: "Key definitions & terminology",
        2: "Core concept understanding",
        3: "Practice problems & applications",
        4: "Analysis of exam patterns",
        5: "Critical evaluation of approaches",
        6: "Case study design",
    }
    return bloom_topics.get(bloom, "Core concepts")
