"""
AI-Mentor — Teacher Agent
Dedicated agent for the Teaching Core (V1):
  - generate_lesson_plan(): structured step list before lesson starts
  - evaluate_checkpoint_answer(): judge student answers using LLM
  - detect_confusion(): track repeated concept asks in a session

All LLM calls use Groq (fast, low-latency for interactive teaching).
"""
import json
import logging

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from config import settings

logger = logging.getLogger(__name__)

BLOOM_NAMES = {
    1: "Remember", 2: "Understand", 3: "Apply",
    4: "Analyze",  5: "Evaluate",  6: "Create"
}


# ── Lesson Planner ───────────────────────────────────────────────────────────

async def generate_lesson_plan(
    subject: str,
    topic: str,
    bloom_level: int,
    style: str = "visual + example-based",
    syllabus_context: str = "",
) -> list[dict]:
    """
    Pre-generate a structured lesson plan for a topic.
    Returns a list of step dicts:
      [{ step_num, title, estimated_minutes, bloom_target, checkpoint_after }]
    Lightweight Groq call — no diagrams, just structure.
    """
    bloom_name = BLOOM_NAMES.get(bloom_level, "Understand")

    prompt = f"""You are designing a lesson plan for a student.
Subject: {subject}
Topic: {topic}
Student's Bloom Level: {bloom_level}/6 ({bloom_name})
Learning Style: {style}
{f"Syllabus Context: {syllabus_context}" if syllabus_context else ""}

Create a lesson plan with 4-6 steps. After every 2 steps, mark checkpoint_after=true.

Respond ONLY with a JSON array:
[
  {{
    "step_num": 1,
    "title": "Introduction to {topic}",
    "estimated_minutes": 3,
    "bloom_target": 1,
    "checkpoint_after": false
  }},
  {{
    "step_num": 2,
    "title": "Core Concept — How It Works",
    "estimated_minutes": 4,
    "bloom_target": 2,
    "checkpoint_after": true
  }}
]

Rules:
- step titles must be specific to "{topic}", not generic
- estimated_minutes: 2-6 minutes per step
- bloom_target: one level per step, starting at {max(1, bloom_level-1)}
- checkpoint_after: true after step 2, and again after step 4
- No markdown, no explanation, just the JSON array."""

    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.3,
        max_tokens=600,
    )

    try:
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = result.content.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        plan = json.loads(raw)
        # Validate and normalise
        validated = []
        for i, step in enumerate(plan):
            validated.append({
                "step_num":          int(step.get("step_num", i + 1)),
                "title":             str(step.get("title", f"Step {i+1}")),
                "estimated_minutes": int(step.get("estimated_minutes", 3)),
                "bloom_target":      int(step.get("bloom_target", bloom_level)),
                "checkpoint_after":  bool(step.get("checkpoint_after", False)),
            })
        return validated
    except Exception as e:
        logger.warning(f"generate_lesson_plan failed ({e}), returning fallback plan")
        # Sensible fallback — always return something the frontend can use
        return [
            {"step_num": 1, "title": f"Introduction to {topic}", "estimated_minutes": 3, "bloom_target": 1, "checkpoint_after": False},
            {"step_num": 2, "title": f"Core Concepts — {topic}", "estimated_minutes": 4, "bloom_target": 2, "checkpoint_after": True},
            {"step_num": 3, "title": f"Real-World Application", "estimated_minutes": 4, "bloom_target": 3, "checkpoint_after": False},
            {"step_num": 4, "title": f"Common Problems & Patterns", "estimated_minutes": 5, "bloom_target": 3, "checkpoint_after": True},
            {"step_num": 5, "title": f"Summary & Key Takeaways", "estimated_minutes": 2, "bloom_target": 2, "checkpoint_after": False},
        ]


# ── Checkpoint Evaluator ─────────────────────────────────────────────────────

async def evaluate_checkpoint_answer(
    question: str,
    student_answer: str,
    correct_context: str,
    bloom_level: int,
    topic: str,
) -> dict:
    """
    Evaluate a student's free-text checkpoint answer using Groq.
    Returns: { score: 0-10, correct: bool, feedback: str, misconceptions: [str] }
    """
    bloom_name = BLOOM_NAMES.get(bloom_level, "Understand")

    prompt = f"""You are a strict but encouraging teacher grading a student's answer.

Topic: {topic}
Bloom Level: {bloom_level}/6 ({bloom_name})
Question: {question}
Correct concept / expected answer: {correct_context}
Student's answer: {student_answer}

Grade the answer. Respond ONLY with valid JSON:
{{
  "score": 8,
  "correct": true,
  "feedback": "Good answer! You correctly identified X. One thing to add is Y.",
  "misconceptions": []
}}

Rules:
- score: 0-10 (7+ = correct=true, below 7 = correct=false)
- feedback: 1-2 sentences, specific to what the student wrote, encouraging
- misconceptions: list any wrong concepts the student showed (empty if correct)
- If student_answer is empty or "skip", score=0 and feedback="No answer provided. Let me explain the concept."
- Never say "the correct answer is X" directly in feedback — guide them instead."""

    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.2,
        max_tokens=250,
    )

    try:
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = result.content.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        graded = json.loads(raw)
        return {
            "score":         int(graded.get("score", 0)),
            "correct":       bool(graded.get("correct", False)),
            "feedback":      str(graded.get("feedback", "Let me explain this concept further.")),
            "misconceptions": list(graded.get("misconceptions", [])),
        }
    except Exception as e:
        logger.warning(f"evaluate_checkpoint_answer failed ({e})")
        return {
            "score": 0,
            "correct": False,
            "feedback": "I had trouble evaluating your answer. Let's review the concept together.",
            "misconceptions": [],
        }


# ── Confusion Detector ───────────────────────────────────────────────────────

def detect_confusion(session_turns: list[dict], current_topic: str, threshold: int = 3) -> bool:
    """
    Detect if student is confused about the same topic by tracking
    repeated questions in the session. Pure Python — no LLM needed.

    Returns True if the same concept appears >= threshold times in user turns.
    """
    if not session_turns or not current_topic:
        return False

    topic_lower = current_topic.lower().split()[:3]  # first 3 words of topic
    ask_count = 0

    for turn in session_turns:
        if turn.get("role") != "user":
            continue
        content_lower = (turn.get("content") or "").lower()
        # Check if any key topic word appears in the user message
        if any(word in content_lower for word in topic_lower if len(word) > 3):
            ask_count += 1

    return ask_count >= threshold


# ── Checkpoint Question Injector ─────────────────────────────────────────────

def parse_checkpoints_from_lesson(full_text: str) -> list[dict]:
    """
    Parse [CHECKPOINT] blocks from the LLM lesson output.
    Returns list of checkpoint dicts:
      [{ after_step: int, question: str, type: str, options: [], correct_index: int, explanation: str }]
    """
    import re
    checkpoints = []

    # Match [CHECKPOINT] blocks
    cp_pattern = re.compile(
        r'\[CHECKPOINT\]\s*\n'
        r'Question:\s*(.+?)\n'
        r'Type:\s*(mcq|short)\s*\n'
        r'(?:Options:\s*(.+?)\n)?'
        r'(?:Correct:\s*([A-Da-d]|\w+)\s*\n)?'
        r'Explanation:\s*(.+?)(?=\[STEP|\[CHECKPOINT\]|\Z)',
        re.DOTALL | re.IGNORECASE,
    )

    # Find which step each checkpoint follows
    step_pattern = re.compile(r'\[STEP\s+(\d+):', re.IGNORECASE)
    step_positions = [(m.start(), int(m.group(1))) for m in step_pattern.finditer(full_text)]
    cp_positions = [(m.start(), m) for m in cp_pattern.finditer(full_text)]

    for cp_pos, cp_match in cp_positions:
        # Find which step this checkpoint comes after
        after_step = 0
        for step_pos, step_num in step_positions:
            if step_pos < cp_pos:
                after_step = step_num

        question = cp_match.group(1).strip()
        cp_type = (cp_match.group(2) or "mcq").strip().lower()
        options_raw = (cp_match.group(3) or "").strip()
        correct_raw = (cp_match.group(4) or "A").strip()
        explanation = (cp_match.group(5) or "").strip()

        # Parse MCQ options: "A) opt1 B) opt2 C) opt3 D) opt4"
        options = []
        if options_raw:
            opt_parts = re.split(r'[A-D]\)', options_raw)
            options = [p.strip() for p in opt_parts if p.strip()]

        # Convert letter to 0-based index
        correct_index = ord(correct_raw[0].upper()) - ord('A') if correct_raw else 0

        checkpoints.append({
            "after_step":    after_step,
            "question":      question,
            "type":          cp_type,
            "options":       options,
            "correct_index": correct_index,
            "explanation":   explanation[:400],
        })

    return checkpoints
