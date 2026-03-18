"""
Problems Generator — Phase 7 V10
Generates MCQ / short-answer / coding problems for student practice bank.
"""
import json
import re
import logging
from groq import AsyncGroq
from config import settings

logger = logging.getLogger(__name__)

_re = re


async def generate_problems(
    subject_name: str,
    topic: str,
    count: int = 5,
    mode: str = "mixed",          # "mcq" | "short" | "coding" | "mixed"
    difficulty: str = "medium",   # "easy" | "medium" | "hard" | "olympiad"
    student_context: dict = None,
) -> list[dict]:
    """
    Generate problems for a topic in a subject.
    Returns list of problem dicts with type, question, answer, hints, difficulty.
    """
    mode_desc = {
        "mcq": "multiple-choice questions with 4 options and 1 correct answer",
        "short": "short-answer questions (2-3 sentence answers)",
        "coding": "coding problems with problem statement, examples, and constraints",
        "mixed": "a mix of MCQ (40%), short-answer (30%), and coding problems (30%)",
        "olympiad": "olympiad-level proof, derivation, and advanced reasoning questions (Bloom L5-L6)",
        "hackathon": "system design, API design, scalability, and MVP planning problems",
    }.get(mode, "mixed problems")

    difficulty_desc = {
        "easy": "beginner level — recall and basic understanding (Bloom L1-L2)",
        "medium": "intermediate — application and analysis (Bloom L3-L4)",
        "hard": "advanced — evaluation and synthesis (Bloom L5-L6)",
        "olympiad": "competition-grade — prove, derive, construct, disprove",
    }.get(difficulty, "medium")

    prompt = f"""Generate {count} practice problems for Indian engineering students studying {subject_name}.

Topic: {topic}
Problem types: {mode_desc}
Difficulty: {difficulty_desc}

Return ONLY a valid JSON array. Each problem must follow this exact schema:
{{
  "id": "unique short slug like 'q1'",
  "type": "mcq" | "short" | "coding",
  "question": "the full question text",
  "options": ["A", "B", "C", "D"],  // only for MCQ, omit for others
  "correct_index": 0,  // only for MCQ (0-3)
  "correct_answer": "the correct answer or explanation",
  "hint": "a one-line hint without giving away the answer",
  "bloom_level": 3,  // 1-6
  "difficulty": "{difficulty}",
  "tags": ["relevant", "keywords"],
  "explanation": "why this answer is correct — 2-3 sentences"
}}

IMPORTANT:
- For coding problems: question should include Input/Output format and constraints
- For MCQ: all 4 options must be plausible, only one correct
- For short: expected answer 2-3 sentences
- Return ONLY the JSON array, no markdown, no explanation
"""

    try:
        client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert problem setter for engineering exams. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=3000,
        )
        raw = resp.choices[0].message.content.strip()
        # Extract JSON array
        match = _re.search(r'\[.*\]', raw, re.DOTALL)
        problems = json.loads(match.group() if match else raw)
        # Validate and clean
        result = []
        for i, p in enumerate(problems[:count]):
            result.append({
                "id": p.get("id", f"q{i+1}"),
                "type": p.get("type", "mcq"),
                "question": p.get("question", ""),
                "options": p.get("options", []),
                "correct_index": p.get("correct_index", 0),
                "correct_answer": p.get("correct_answer", ""),
                "hint": p.get("hint", ""),
                "bloom_level": p.get("bloom_level", 3),
                "difficulty": p.get("difficulty", difficulty),
                "tags": p.get("tags", [topic]),
                "explanation": p.get("explanation", ""),
            })
        return result
    except Exception as e:
        logger.warning(f"[problems_generator] LLM failed: {e}, using fallback")
        return _fallback_problems(topic, count, difficulty)


async def debug_code(code: str, stderr: str, language: str = "python") -> dict:
    """
    Analyze a code error using Groq LLM and return structured debug report.
    """
    prompt = f"""A student's {language} code has an error. Help debug it.

CODE:
```{language}
{code[:2000]}
```

ERROR OUTPUT:
```
{stderr[:1000]}
```

Provide a structured debug analysis. Return ONLY valid JSON:
{{
  "error_type": "short error category (e.g. SyntaxError, LogicError, IndexError)",
  "root_cause": "1-2 sentence explanation of WHY this error occurred",
  "line_hint": "which line number(s) is likely the problem (or null if unknown)",
  "fix_suggestion": "concrete, specific fix the student should make",
  "fixed_code": "the corrected version of the code (full code)",
  "learning_tip": "one teaching tip to avoid this type of error in future",
  "similar_errors": ["2-3 related error patterns the student should know about"]
}}

IMPORTANT: Return ONLY the JSON object, no markdown.
"""
    try:
        client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",  # fast model for instant debugging
            messages=[
                {"role": "system", "content": "You are an expert debugger and coding teacher. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()
        match = _re.search(r'\{.*\}', raw, re.DOTALL)
        return json.loads(match.group() if match else raw)
    except Exception as e:
        return {
            "error_type": "ParseError",
            "root_cause": "Could not analyze the error automatically.",
            "line_hint": None,
            "fix_suggestion": f"Check the error: {stderr[:200]}",
            "fixed_code": code,
            "learning_tip": "Read the error message carefully — it usually tells you the line and type of error.",
            "similar_errors": [],
        }


def _fallback_problems(topic: str, count: int, difficulty: str) -> list[dict]:
    return [
        {
            "id": f"q{i+1}",
            "type": "short",
            "question": f"Explain the concept of '{topic}' in your own words.",
            "options": [],
            "correct_index": 0,
            "correct_answer": f"A clear explanation of {topic} with an example.",
            "hint": f"Think about what {topic} does and how it works.",
            "bloom_level": 2,
            "difficulty": difficulty,
            "tags": [topic],
            "explanation": f"Understanding {topic} is fundamental to this subject.",
        }
        for i in range(count)
    ]
