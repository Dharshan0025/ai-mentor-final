"""
AI-Mentor — Learning Agent
Handles: concept explanations, quiz generation, Bloom's taxonomy gating,
         study material retrieval, prerequisite checking.
LLM: Groq (fast for explanations) + Gemini for quiz generation
"""
from datetime import datetime
import logging
import json

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from db import db

logger = logging.getLogger(__name__)


LEARNING_SYSTEM = """You are the Learning Agent for an AI academic mentor.

Your role:
- Explain concepts at the student's current Bloom's Taxonomy level
- Generate practice questions (MCQ, short answer) on demand
- Check prerequisite gaps before explaining advanced topics
- Use analogies and real-world examples from engineering context

Bloom's Taxonomy levels (apply appropriate depth):
1. Remember → define, list, recall
2. Understand → explain, describe, summarise
3. Apply → solve, use, implement
4. Analyze → compare, distinguish, examine
5. Evaluate → judge, critique, justify
6. Create → design, construct, propose

Student learning profile:
{learning_profile}

Rules:
- Match explanation depth to student's Bloom level for this subject.
- Adapt tone and structure to the student's preferred learning style.
- For conceptual \"what / why / how / explain\" questions:
  - On the FIRST turn about this topic in the recent chat, reply in Socratic mode:
    - Ask 1–2 short probing questions and get the student to think.
    - Do NOT give the full final explanation yet; keep it light and encouraging.
  - On FOLLOW-UP turns where the student has already tried to answer:
    - Give a clear explanation.
    - Briefly point out what they got right and where they need to correct their understanding.
- If asking for a quiz → generate exactly 3 MCQ questions with answer key.
- Highlight prerequisite topics if the current topic requires them.
- Use code snippets for CS topics when helpful (fenced code blocks).
- Maximum 400 words."""


async def learning_node(state: dict) -> dict:
    """Learning agent — adaptive explanations + quiz generation."""
    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.4,
        max_tokens=600,
    )

    profile = state.get("student_profile", {})
    student_id = state.get("student_id")

    learning_dna = None
    if student_id:
        try:
            # Fetch or auto-create the student's learning DNA
            learning_dna = await db.get_learning_dna(student_id)
            # Record an observation of the active hour (for peak_hour)
            hour = datetime.now().hour
            await db.update_learning_dna(
                student_college_id=student_id,
                peak_hour_observation=hour,
            )
        except Exception as e:
            logger.warning(f"Learning DNA load/update failed for {student_id}: {e}")

    system_prompt = LEARNING_SYSTEM.format(
        learning_profile=_format_learning_profile(profile, state["message"], learning_dna)
    )

    messages = [SystemMessage(content=system_prompt)]
    for msg in state.get("history", [])[-4:]:
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg["content"]))

    messages.append(HumanMessage(content=state["message"]))

    result = await llm.ainvoke(messages)

    return {
        **state,
        "learning_output": result.content,
        "model_used": settings.groq_model,
    }


def _format_learning_profile(profile: dict, message: str, learning_dna: dict | None = None) -> str:
    """Format the learning context — focus on relevant subject + learning DNA."""
    dna_lines = []
    if learning_dna:
        style = learning_dna.get("preferred_style") or "example-based"
        peak_hour = learning_dna.get("peak_hour")
        total_q = learning_dna.get("total_questions") or 0
        total_quiz = learning_dna.get("total_quizzes") or 0

        dna_lines.append(f"Preferred style: {style}")
        if peak_hour is not None:
            dna_lines.append(f"Peak study hour (approx.): {peak_hour}:00")
        dna_lines.append(f"Quiz history: {total_quiz} quiz attempts, {total_q} questions answered.")

        weak = learning_dna.get("weak_topics") or []
        strong = learning_dna.get("strong_topics") or []
        if weak:
            dna_lines.append(f"Weak topics (examples): {[w.get('topic') or w.get('subject_code') for w in weak[:3]]}")
        if strong:
            dna_lines.append(f"Strong topics (examples): {[s.get('topic') or s.get('subject_code') for s in strong[:3]]}")

    dna_block = "\n".join(dna_lines) if dna_lines else "No historical learning DNA available; assume average CS engineering student."

    if not profile:
        return (
            "Student is a 3rd year CS engineering student. Bloom level: 2-3 for most subjects.\n"
            f"Learning DNA:\n{dna_block}"
        )

    subjects = profile.get("subjects", [])
    message_lower = message.lower()

    # Try to find which subject is being discussed
    relevant_subject = None
    for s in subjects:
        name_parts = s.get("name", "").lower().split()
        if any(part in message_lower for part in name_parts if len(part) > 3):
            relevant_subject = s
            break

    if relevant_subject:
        return f"""
Focus subject: {relevant_subject.get('name')}
Student's Bloom level for this subject: {relevant_subject.get('bloomLevel', 2)}/6
Current grade: {relevant_subject.get('grade')} | Status: {relevant_subject.get('status', 'unknown')}
Department: {profile.get('department', 'CS')} | Semester: {profile.get('semester')}

Learning DNA:
{dna_block}
"""
    else:
        bloom_avg = sum(s.get("bloomLevel", 2) for s in subjects) // max(len(subjects), 1)
        return f"""
Department: {profile.get('department', 'CS')} | Semester: {profile.get('semester')}
Average Bloom level across subjects: {bloom_avg}/6
Subjects: {[s.get('name') for s in subjects]}

Learning DNA:
{dna_block}
"""


def generate_quiz(subject: str, topic: str, bloom_level: int) -> dict:
    """
    Generate targeted MCQ quiz questions for a specific topic and Bloom level.
    Returns structured JSON for the frontend to render interactively.
    """
    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.5,
        max_tokens=800,
    )

    bloom_names = {1: "Remember", 2: "Understand", 3: "Apply", 4: "Analyze", 5: "Evaluate", 6: "Create"}
    bloom_name = bloom_names.get(bloom_level, "Understand")

    prompt = f"""Generate exactly 3 MCQ questions for:
Subject: {subject}
Topic: {topic}
Bloom's Level: {bloom_level} — {bloom_name}

You MUST respond ONLY with a valid JSON array. No markdown, no explanation, just the JSON.
Format:
[
  {{
    "question": "What is...?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "answer_index": 1,
    "explanation": "Brief explanation of why B is correct"
  }},
  ...
]

Rules:
- answer_index is 0-based (0=A, 1=B, 2=C, 3=D)
- Make questions progressively harder for Bloom level {bloom_level} ({bloom_name})
- All 4 options must be plausible, not trivially wrong
- Keep each question concise and focused on {topic}"""

    result = llm.invoke([HumanMessage(content=prompt)])
    raw = result.content.strip()

    # Parse JSON — extract from markdown code block if LLM wraps it
    try:
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        questions = json.loads(raw)
    except Exception as e:
        logger.warning(f"Quiz JSON parse failed: {e}. Raw: {raw[:200]}")
        # Graceful fallback — return 1 placeholder question
        questions = [{
            "question": f"Explain the concept of {topic} in the context of {subject}.",
            "options": ["Level 1 understanding", "Level 2 understanding", "Level 3 understanding", "Level 4 understanding"],
            "answer_index": 1,
            "explanation": "This is a fallback question — the AI quiz generation encountered an issue."
        }]

    return {
        "subject": subject,
        "topic": topic,
        "bloom_level": bloom_level,
        "bloom_name": bloom_name,
        "questions": questions,
        "total": len(questions),
    }


