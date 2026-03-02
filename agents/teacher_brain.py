"""
AI-Mentor — Teacher Brain (Phase 6 + 6B)
Core teaching intelligence: lesson planning, understanding checks,
answer evaluation, adaptive explanation, and teacher-like prompts.

LLM priority: Bedrock (Claude Haiku 4.5) → Groq (Llama 3.3 70B)
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LessonConcept:
    index: int                       # 0-based
    title: str                       # short concept name (3-5 words)
    explanation: str                 # 4-6 sentence teacher-style explanation
    example: str                     # single concrete real-world example
    checkpoint_question: str         # one comprehension-check question
    needs_diagram: bool = True       # whether a Mermaid visual should be generated


@dataclass
class LessonPlan:
    topic: str
    subject_code: str
    difficulty_level: str            # "beginner" | "intermediate" | "advanced"
    teaching_style: str              # "visual" | "example-based" | "analogy-driven"
    concepts: list[LessonConcept] = field(default_factory=list)

    @property
    def total_concepts(self) -> int:
        return len(self.concepts)

    def to_summary_dict(self) -> dict:
        """Lightweight dict for the lesson_plan SSE event."""
        return {
            "topic": self.topic,
            "subject_code": self.subject_code,
            "difficulty_level": self.difficulty_level,
            "teaching_style": self.teaching_style,
            "total_concepts": self.total_concepts,
            "concept_titles": [c.title for c in self.concepts],
        }


@dataclass
class EvaluationResult:
    """Result of evaluating a student's answer to a checkpoint question."""
    score: float            # 0.0 – 1.0
    understood: bool        # True if student grasped the concept
    feedback: str           # teacher-style feedback sentence
    needs_reexplain: bool   # True if concept should be re-taught


# ═══════════════════════════════════════════════════════════════════════════════
# LLM FACTORY — Bedrock (Claude Haiku 4.5) → Groq fallback
# ═══════════════════════════════════════════════════════════════════════════════

def get_teacher_llm(temperature: float = 0.4, max_tokens: int = 2000):
    """
    Returns the best available async LLM for teaching tasks.
    Priority: Bedrock (Claude Haiku 4.5) → Groq (Llama 3.3 70B).
    """
    # Try Bedrock first (Claude Haiku 4.5)
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        try:
            from langchain_aws import ChatBedrock
            return ChatBedrock(
                region_name=settings.aws_region,
                model_id=settings.bedrock_model_id,
                model_kwargs={"temperature": temperature, "max_tokens": max_tokens},
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
        except Exception as e:
            logger.warning(f"Bedrock init failed, falling back to Groq: {e}")

    # Fallback: Groq
    from langchain_groq import ChatGroq
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LESSON PLANNER
# ═══════════════════════════════════════════════════════════════════════════════

PLANNER_SYSTEM = """You are an expert lesson planner for an AI university tutor.
Your job: decompose a topic into 3–5 clear, sequential concepts a student must learn.
Each concept builds on the previous. Tailor to the given Bloom level and learning style.

OUTPUT: Return ONLY a valid JSON object — no markdown, no explanation, no preamble.
Schema:
{
  "difficulty_level": "beginner|intermediate|advanced",
  "teaching_style": "visual|example-based|analogy-driven",
  "concepts": [
    {
      "title": "<3–5 word concept name>",
      "explanation": "<4–6 sentences. Conversational teacher voice. No jargon dumps. Build intuition first.>",
      "example": "<One concrete real-world or code example. Keep it to 2–3 sentences.>",
      "checkpoint_question": "<One short question to check understanding. End with '?'>",
      "needs_diagram": true
    }
  ]
}

Rules:
- 3 concepts minimum, 5 maximum.
- explanation must be speakable (will be read aloud by TTS) — avoid tables, bullet lists, raw code.
- checkpoint_question must be answerable in 1–2 sentences by a student who understood the explanation.
- needs_diagram: true only when a flowchart, tree, or sequence diagram genuinely helps (not for pure math).
"""


def _build_planner_prompt(topic: str, subject_code: str, ctx: dict) -> str:
    bloom = ctx.get("bloom_level", 2)
    style = ctx.get("style", "example-based")
    syllabus_text = ctx.get("syllabus_text", "")
    mastery_weak = ctx.get("mastery_weak", "")
    student_name = ctx.get("profile", {}).get("name", "Student")

    bloom_desc = {
        1: "basics and simple recall",
        2: "understanding and simple explanation",
        3: "application and worked examples",
        4: "analysis and comparing approaches",
        5: "evaluation and trade-off discussion",
        6: "synthesis and design",
    }.get(bloom, "understanding and examples")

    prompt = f"""Topic to teach: "{topic}"
Subject code: {subject_code}
Student: {student_name} | Bloom level: {bloom}/6 ({bloom_desc}) | Learning style: {style}
"""
    if mastery_weak:
        prompt += f"Known weak areas for this student: {mastery_weak}\n"
    if syllabus_text:
        prompt += f"\nSyllabus context (use to keep concepts relevant):\n{syllabus_text[:800]}\n"

    prompt += "\nGenerate the structured lesson plan JSON now."
    return prompt


def _parse_plan_json(raw: str, topic: str, subject_code: str) -> LessonPlan:
    """Extract JSON from LLM output and build a LessonPlan. Robust to markdown fences."""
    clean = raw.strip()
    if "```json" in clean:
        clean = clean.split("```json", 1)[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```", 1)[1].split("```")[0].strip()

    if not clean.startswith("{"):
        m = re.search(r"\{.*\}", clean, re.DOTALL)
        if m:
            clean = m.group(0)

    data = json.loads(clean)
    concepts_raw = data.get("concepts", [])

    concepts = []
    for i, c in enumerate(concepts_raw[:5]):
        concepts.append(LessonConcept(
            index=i,
            title=c.get("title", f"Concept {i + 1}"),
            explanation=c.get("explanation", ""),
            example=c.get("example", ""),
            checkpoint_question=c.get("checkpoint_question", "Did that make sense?"),
            needs_diagram=bool(c.get("needs_diagram", True)),
        ))

    if not concepts:
        raise ValueError("JSON parsed but contains no concepts")

    return LessonPlan(
        topic=topic,
        subject_code=subject_code,
        difficulty_level=data.get("difficulty_level", "intermediate"),
        teaching_style=data.get("teaching_style", "example-based"),
        concepts=concepts,
    )


def _make_fallback_plan(topic: str, subject_code: str, ctx: dict) -> LessonPlan:
    """Emergency fallback: a minimal 3-concept plan when the LLM fails."""
    bloom = ctx.get("bloom_level", 2)
    return LessonPlan(
        topic=topic,
        subject_code=subject_code,
        difficulty_level="intermediate",
        teaching_style="example-based",
        concepts=[
            LessonConcept(
                index=0,
                title=f"Introduction to {topic}",
                explanation=(
                    f"Let's start with the basics of {topic}. "
                    f"This is a fundamental concept in {subject_code or 'computer science'}. "
                    "I'll walk you through the core idea step by step."
                ),
                example=f"Think of {topic} like a well-organized filing system — everything has a place and a purpose.",
                checkpoint_question=f"In your own words, what do you think {topic} is trying to solve?",
                needs_diagram=True,
            ),
            LessonConcept(
                index=1,
                title=f"How {topic} Works",
                explanation=(
                    f"Now that we know what {topic} is, let's look at the mechanism. "
                    "The key steps happen in a specific sequence that we'll trace through together. "
                    "Pay attention to the order — it matters."
                ),
                example=f"Here's a step-by-step trace of {topic} on a small input to make it concrete.",
                checkpoint_question="Can you describe one step in the process we just covered?",
                needs_diagram=True,
            ),
            LessonConcept(
                index=2,
                title=f"Why {topic} Matters",
                explanation=(
                    f"Understanding {topic} is important because it appears in real systems you use every day. "
                    f"At Bloom level {bloom}, we'll also look at where it's applied and why it's preferred over alternatives."
                ),
                example=f"Real systems that use {topic}: modern databases and search engines rely on this concept.",
                checkpoint_question="Can you name one scenario where this concept would be useful?",
                needs_diagram=False,
            ),
        ],
    )


async def plan_lesson(
    student_id: str,
    subject_code: str,
    topic: str,
    ctx: dict,
) -> LessonPlan:
    """
    Plan a lesson for a topic using the student's context.
    Returns a LessonPlan with 3–5 concepts.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    prompt = _build_planner_prompt(topic, subject_code, ctx)
    llm = get_teacher_llm(temperature=0.3, max_tokens=2000)

    try:
        result = await llm.ainvoke([
            SystemMessage(content=PLANNER_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw = (result.content or "").strip()
        plan = _parse_plan_json(raw, topic, subject_code)
        logger.info(
            f"Lesson planned for [{student_id}] topic='{topic}' → "
            f"{plan.total_concepts} concepts, difficulty={plan.difficulty_level}"
        )
        return plan

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed for lesson plan (topic='{topic}'): {e}. Using fallback.")
        return _make_fallback_plan(topic, subject_code, ctx)
    except Exception as e:
        logger.error(f"plan_lesson failed for topic='{topic}': {e}", exc_info=True)
        return _make_fallback_plan(topic, subject_code, ctx)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6B — ANSWER EVALUATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

EVAL_SYSTEM = """You are a university professor evaluating a student's answer to a comprehension question.
You must return ONLY a valid JSON object — no preamble, no markdown fences.

Schema:
{
  "score": <float 0.0 to 1.0>,
  "understood": <true if score >= 0.6>,
  "feedback": "<1-2 sentence teacher feedback, spoken aloud>"
}

Scoring guide:
- 1.0: Fully correct, demonstrates understanding
- 0.7–0.9: Mostly correct, minor gap
- 0.4–0.6: Partially correct, key ideas missing
- 0.1–0.3: Attempted but fundamentally wrong
- 0.0: No relevant content

Feedback rules:
- If correct: "Good thinking, {name}. That's exactly right." or similar warm praise.
- If partially correct: "You're on the right track, {name}. [explain what's missing in one sentence]."
- If incorrect: "That's a common confusion, {name}. [brief correction in one sentence]."
- Keep feedback to 1-2 sentences. Be encouraging. Never be harsh."""


async def evaluate_student_answer(
    student_answer: str,
    concept: LessonConcept,
    ctx: dict,
) -> EvaluationResult:
    """
    Evaluate a student's answer to a checkpoint question.
    Uses LLM to compare the answer against the concept's content.
    Returns an EvaluationResult with score, understood flag, and teacher feedback.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    profile = ctx.get("profile", {})
    student_name = profile.get("name", "Student").split()[0]
    bloom = ctx.get("bloom_level", 2)

    eval_prompt = f"""Student: {student_name} | Bloom level: {bloom}/6

Concept being taught: "{concept.title}"
Key explanation: {concept.explanation[:300]}
Example given: {concept.example[:200]}

Checkpoint question: "{concept.checkpoint_question}"
Student's answer: "{student_answer}"

Evaluate. Return JSON only."""

    llm = get_teacher_llm(temperature=0.2, max_tokens=300)

    try:
        result = await llm.ainvoke([
            SystemMessage(content=EVAL_SYSTEM.replace("{name}", student_name)),
            HumanMessage(content=eval_prompt),
        ])
        raw = (result.content or "").strip()

        # Parse JSON robustly
        clean = raw
        if "```json" in clean:
            clean = clean.split("```json", 1)[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```", 1)[1].split("```")[0].strip()
        if not clean.startswith("{"):
            m = re.search(r"\{.*\}", clean, re.DOTALL)
            if m:
                clean = m.group(0)

        data = json.loads(clean)
        score = max(0.0, min(1.0, float(data.get("score", 0.5))))
        understood = bool(data.get("understood", score >= 0.6))
        feedback = data.get("feedback", "").strip()

        if not feedback:
            if understood:
                feedback = f"Good work, {student_name}. You've got it."
            else:
                feedback = f"Not quite, {student_name}. Let me explain this differently."

        return EvaluationResult(
            score=score,
            understood=understood,
            feedback=feedback,
            needs_reexplain=not understood,
        )

    except Exception as e:
        logger.warning(f"Answer evaluation failed: {e}. Using heuristic fallback.")
        # Simple heuristic: if answer has >5 words, give partial credit
        word_count = len(student_answer.strip().split())
        if word_count >= 8:
            return EvaluationResult(
                score=0.5,
                understood=False,
                feedback=f"Thanks for your attempt, {student_name}. Let me clarify a few things.",
                needs_reexplain=True,
            )
        elif word_count >= 3:
            return EvaluationResult(
                score=0.3,
                understood=False,
                feedback=f"I see what you mean, {student_name}, but let me re-explain this a bit differently.",
                needs_reexplain=True,
            )
        else:
            return EvaluationResult(
                score=0.1,
                understood=False,
                feedback=f"No worries, {student_name}. This is a tricky concept. Let me walk through it again.",
                needs_reexplain=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6B — ADAPTIVE EXPLANATION LEVEL
# ═══════════════════════════════════════════════════════════════════════════════

def adjust_explanation_level(session: dict) -> str:
    """
    Determine the right explanation level based on session performance.
    Examines past correct/incorrect answers in the session.

    Returns: "simple" | "moderate" | "advanced"
    """
    turns = session.get("turns", [])
    mastered = session.get("concepts_mastered", [])
    failed = session.get("concepts_failed", [])
    attempt_count = session.get("attempt_count", 0)

    # Count recent evaluations in turns
    correct = 0
    incorrect = 0
    for t in turns[-12:]:
        content = (t.get("content") or "").lower()
        if t.get("role") == "assistant":
            if any(w in content for w in ["exactly right", "that's correct", "good thinking", "well done", "you've got it"]):
                correct += 1
            elif any(w in content for w in ["not quite", "let me explain", "re-explain", "common confusion", "let me clarify"]):
                incorrect += 1

    # If currently struggling (attempt_count > 0), go simpler
    if attempt_count >= 2:
        return "simple"
    if attempt_count == 1:
        return "simple"

    # Overall session performance
    total_concepts = len(mastered) + len(failed)
    if total_concepts == 0:
        return "moderate"

    mastery_rate = len(mastered) / total_concepts if total_concepts else 0.5

    if mastery_rate >= 0.8 and correct >= 3:
        return "advanced"
    elif mastery_rate <= 0.4 or incorrect >= 3:
        return "simple"
    else:
        return "moderate"


# ═══════════════════════════════════════════════════════════════════════════════
# CONCEPT NARRATION + RE-EXPLANATION PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

TEACHER_PERSONALITY = """You are a personal academic mentor and a patient, calm, encouraging university professor.
You remember past lessons. You track student progress. You encourage improvement.
You adjust your teaching style to the student. You behave like a long-term professor guiding a student.

Teaching rules:
- Explain clearly in short sentences.
- Use real-world examples and analogies.
- Ask questions to check understanding.
- Wait for the student's answer before moving on.
- Encourage the student: "Good thinking", "Nice attempt", "You're improving".
- NEVER produce long lectures or paragraphs.
- Teach step by step. One idea at a time.
- Address the student by their first name.
- When diagrams are provided, explain them step-by-step like drawing on a whiteboard.
- Refer to specific parts of diagrams: "Notice how X connects to Y."
"""


def build_concept_system_prompt(
    concept: LessonConcept,
    ctx: dict,
    is_last: bool,
    explanation_level: str = "moderate",
    prev_concept_title: str = "",
) -> str:
    """
    Build the system prompt for streaming one concept's narration + diagram.
    Now includes teacher personality, adaptive level, and lesson continuity.
    """
    profile = ctx.get("profile", {})
    bloom = ctx.get("bloom_level", 2)
    style = ctx.get("style", "example-based")
    student_name = profile.get("name", "Student").split()[0]

    # Lesson continuity
    continuity = ""
    if prev_concept_title:
        continuity = f'\nStart by saying: "Last time we covered {prev_concept_title}. Now let\'s move to {concept.title}."\n'

    # Explanation depth by level
    level_instruction = {
        "simple": (
            "Use simple analogies and everyday language. "
            "Break each idea into the smallest possible pieces. "
            "Avoid any technical jargon. Use metaphors the student can relate to."
        ),
        "moderate": (
            "Balance intuition with technical accuracy. "
            "Use one analogy and one technical term per explanation."
        ),
        "advanced": (
            "Be concise and use proper technical terminology. "
            "The student is performing well — move faster and mention edge cases."
        ),
    }.get(explanation_level, "Balance intuition with technical accuracy.")

    prompt = f"""{TEACHER_PERSONALITY}
You are teaching ONE concept right now: "{concept.title}"
Student: {student_name} | Bloom level: {bloom}/6 | Preferred style: {style}
Explanation level: {explanation_level.upper()} — {level_instruction}
{continuity}
Your job for this concept:
1. Deliver a spoken narration (conversational, no bullet points, no headers).
   Core idea: {concept.explanation}
   Example to use: {concept.example}
   Address {student_name} by name once or twice. Keep the total to 5–8 sentences.

2. {"Generate a Mermaid diagram that visually represents this concept. When you generate a diagram, ALSO explain it step-by-step in the narration — refer to specific nodes and arrows as if drawing on a whiteboard." if concept.needs_diagram else "No diagram needed for this concept — focus on a clear spoken explanation."}
   {"Use ONLY: flowchart TD/LR, sequenceDiagram, stateDiagram-v2, classDiagram, erDiagram, mindmap, timeline, pie. Max 10 nodes. No inline styles. No classDef." if concept.needs_diagram else ""}

3. End with the checkpoint question (word-for-word): "{concept.checkpoint_question}"

FORMAT (follow exactly):
[NARRATION]
<your 5–8 sentence spoken explanation here>

{"[DIAGRAM]" if concept.needs_diagram else ""}
{"```mermaid" if concept.needs_diagram else ""}
{"<mermaid code>" if concept.needs_diagram else ""}
{"```" if concept.needs_diagram else ""}

[CHECKPOINT]
{concept.checkpoint_question}

{"[LESSON_END]" if is_last else ""}
"""
    return prompt


def build_reexplain_prompt(
    concept: LessonConcept,
    ctx: dict,
    attempt_count: int,
) -> str:
    """
    Build a re-explanation prompt when the student didn't understand.
    attempt_count 1: use a different analogy.
    attempt_count 2+: use the simplest possible explanation with a concrete example.
    """
    profile = ctx.get("profile", {})
    bloom = ctx.get("bloom_level", 2)
    student_name = profile.get("name", "Student").split()[0]

    if attempt_count == 1:
        strategy = (
            f"Use a COMPLETELY DIFFERENT analogy than last time. "
            f"Think of a real-world scenario {student_name} can relate to — "
            f"like cooking, sports, or using a phone. "
            f"Keep it to 4–5 sentences. End with a new checkpoint question."
        )
    else:
        strategy = (
            f"Use the SIMPLEST possible explanation for {student_name}. "
            f"Pretend they are a complete beginner. "
            f"Walk through a concrete step-by-step example with real numbers or objects. "
            f"Keep it to 5–6 sentences. End with a very simple checkpoint question."
        )

    return f"""{TEACHER_PERSONALITY}
The student did NOT understand "{concept.title}" after {attempt_count} attempt(s).
This is attempt {attempt_count + 1}. DO NOT repeat the same explanation.

Student: {student_name} | Bloom level: {bloom}/6

Strategy: {strategy}

Start with encouragement: "No problem, {student_name}. Let me explain this differently."

FORMAT:
[NARRATION]
<your re-explanation here, 4–6 sentences>

[CHECKPOINT]
<a new, simpler question about {concept.title}>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 10 — VISUAL PLANNER
# ═══════════════════════════════════════════════════════════════════════════════

VISUAL_PLAN_SYSTEM = """You are a teaching assistant deciding whether a concept needs a visual diagram.
Return ONLY a valid JSON object — no preamble, no markdown.

Schema:
{
  "visual_required": true or false,
  "visual_type": "flowchart" | "sequence" | "state" | "class" | "er" | "mindmap" | "timeline" | "pie" | "gantt" | "graph" | "tree" | "array" | "process",
  "description": "<one-sentence description of what the diagram should show>"
}

Decision rules:
- visual_required=true ONLY when a visual genuinely aids understanding (processes, structures, relationships, comparisons)
- visual_required=false for: definitions, formulas, simple facts, historical dates, pure theory
- Choose visual_type that BEST matches the concept:
  - flowchart/process: step-by-step procedures, algorithms
  - sequence: interactions between components, request-response, protocols
  - state: state machines, lifecycle, transitions
  - class: OOP hierarchies, type relationships
  - er: database schemas, entity relationships
  - mindmap: topic overview, concept connections
  - timeline: chronological events, phases
  - pie: distributions, proportions
  - gantt: schedules, parallel tasks
  - graph: networks, connections
  - tree: hierarchies, recursive structures, binary trees
  - array: data structures, lists, indexing
"""


async def generate_visual_plan(
    concept: LessonConcept,
    ctx: dict,
) -> dict:
    """
    Decide if a concept needs a visual diagram and what type.

    Returns:
        {
            "visual_required": bool,
            "visual_type": str,
            "description": str
        }
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    # If the concept already says needs_diagram=False, respect it but double-check
    profile = ctx.get("profile", {})
    bloom = ctx.get("bloom_level", 2)
    style = ctx.get("style", "example-based")

    user_prompt = f"""Concept: "{concept.title}"
Explanation: {concept.explanation[:200]}
Example: {concept.example[:150]}
Bloom level: {bloom}/6 | Student's preferred style: {style}

Should this concept have a visual diagram? What type? Describe it."""

    llm = get_teacher_llm(temperature=0.2, max_tokens=200)

    try:
        result = await llm.ainvoke([
            SystemMessage(content=VISUAL_PLAN_SYSTEM),
            HumanMessage(content=user_prompt),
        ])
        raw = (result.content or "").strip()

        clean = raw
        if "```json" in clean:
            clean = clean.split("```json", 1)[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```", 1)[1].split("```")[0].strip()
        if not clean.startswith("{"):
            m = re.search(r"\{.*\}", clean, re.DOTALL)
            if m:
                clean = m.group(0)

        data = json.loads(clean)
        return {
            "visual_required": bool(data.get("visual_required", concept.needs_diagram)),
            "visual_type": data.get("visual_type", "flowchart"),
            "description": data.get("description", f"Diagram for {concept.title}"),
        }

    except Exception as e:
        logger.warning(f"Visual plan failed for '{concept.title}': {e}. Using concept default.")
        return {
            "visual_required": concept.needs_diagram,
            "visual_type": "flowchart",
            "description": f"Visual representation of {concept.title}",
        }




# ═══════════════════════════════════════════════════════════════════════════════
# INTERRUPT PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

def build_interrupt_system_prompt(
    current_concept: LessonConcept,
    lesson_plan: LessonPlan,
    ctx: dict,
) -> str:
    """
    Prompt for the interrupt handler. The student interrupted mid-lesson.
    Answer the doubt quickly, then signal to resume.
    """
    profile = ctx.get("profile", {})
    bloom = ctx.get("bloom_level", 2)
    student_name = profile.get("name", "Student").split()[0]

    return f"""{TEACHER_PERSONALITY}
You were explaining "{current_concept.title}"
(concept {current_concept.index + 1} of {lesson_plan.total_concepts} in the lesson on "{lesson_plan.topic}")
when {student_name} raised their hand with a question.

Rules:
- Answer ONLY the specific doubt asked. Do not re-explain the full concept.
- Keep your answer to 2–4 sentences. Be direct and clear.
- After answering, end with exactly: "Let's continue from where we left."
- Do NOT use bullet points or headers — this will be spoken aloud.
- Match Bloom level {bloom}/6: {'stick to basics and simple analogies' if bloom <= 2 else 'use application-level examples' if bloom <= 4 else 'discuss trade-offs and design choices'}.
"""
