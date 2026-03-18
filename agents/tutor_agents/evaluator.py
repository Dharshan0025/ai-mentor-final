"""
Evaluator Agent — scores checkpoint sessions and recommends next teaching action.

Given:
  - A checkpoint question + student answer + correct answer
  - Previous SM-2 score for this concept
  - Time taken to answer (response_time_ms)

Produces:
  - is_correct: bool
  - score: float (0–1)
  - feedback: str (targeted, not generic)
  - misconception: str | None (what the student got wrong conceptually)
  - recommendation: 'continue' | 'slow_down' | 'doubt_resolve' | 'revisit_step'
  - bloom_achievement: int (Bloom level actually demonstrated by the answer)

This evaluator is SEPARATE from the existing /tutor/checkpoint endpoint (which is a fast
client-side evaluator). The EvaluatorAgent is used by tutor_graph for deeper analysis.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings

logger = logging.getLogger(__name__)

EVALUATOR_SYSTEM = """You are an expert educational evaluator AI.
Your task: deeply analyse a student's checkpoint answer and provide actionable pedagogical feedback.

Evaluation criteria:
1. Conceptual accuracy (not just matching keywords)
2. Depth of understanding (which Bloom level does the answer demonstrate?)
3. Common misconceptions in this subject area
4. Urgency: should the teacher slow down, revisit, or continue?

Output ONLY valid JSON:
{
  "is_correct": <bool>,
  "score": <float 0.0-1.0>,
  "feedback": "<specific, encouraging 1-2 sentence feedback addressing the student directly>",
  "misconception": "<what they misunderstood, or null if correct>",
  "recommendation": "<one of: continue | slow_down | doubt_resolve | revisit_step>",
  "bloom_achievement": <1-6>,
  "correct_explanation": "<brief 1-sentence correct explanation>"
}

Be encouraging even for wrong answers. Name the specific concept they got wrong."""


EVALUATOR_USER = """Subject: {subject_code}
Topic: {topic}
Question: {question}
Student's answer: {student_answer}
Correct answer / explanation: {correct_answer}
Question type: {question_type}
Time taken: {response_time_ms}ms
Previous score on this concept: {prev_score}
Wrong attempts this session: {wrong_count}"""


@dataclass
class EvaluatorAgent:
    model: str = field(default_factory=lambda: settings.groq_model)

    def _get_llm(self) -> ChatGroq:
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=self.model,
            temperature=0.1,
            max_tokens=600,
        )

    async def evaluate(
        self,
        *,
        subject_code: str,
        topic: str,
        question: str,
        student_answer: str,
        correct_answer: str,
        question_type: str = "mcq",
        response_time_ms: int = 0,
        prev_score: float | None = None,
        wrong_count: int = 0,
    ) -> dict:
        """
        Deep evaluation of a checkpoint answer.
        Returns evaluation dict with recommendation.
        """
        llm = self._get_llm()
        user_msg = EVALUATOR_USER.format(
            subject_code=subject_code,
            topic=topic,
            question=question,
            student_answer=student_answer or "(no answer)",
            correct_answer=correct_answer,
            question_type=question_type,
            response_time_ms=response_time_ms,
            prev_score=f"{prev_score:.2f}" if prev_score is not None else "first attempt",
            wrong_count=wrong_count,
        )
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content=EVALUATOR_SYSTEM),
                    HumanMessage(content=user_msg),
                ])
            )
            raw = result.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            ev = json.loads(raw)
            # Normalise fields
            ev.setdefault("is_correct", False)
            ev.setdefault("score", 1.0 if ev["is_correct"] else 0.0)
            ev.setdefault("feedback", "Good effort! Keep going.")
            ev.setdefault("misconception", None)
            ev.setdefault("recommendation", "continue" if ev["is_correct"] else "slow_down")
            ev.setdefault("bloom_achievement", 2)
            ev.setdefault("correct_explanation", correct_answer[:200])
            return ev
        except Exception as e:
            logger.warning(f"EvaluatorAgent fallback: {e}")
            is_correct = student_answer.strip().lower() == correct_answer.strip().lower()
            return {
                "is_correct": is_correct,
                "score": 1.0 if is_correct else 0.0,
                "feedback": "Correct! Well done." if is_correct else "Not quite — check the concept and try again.",
                "misconception": None,
                "recommendation": "continue" if is_correct else "slow_down",
                "bloom_achievement": 2,
                "correct_explanation": correct_answer[:200],
            }

    async def recommend_action(self, *, wrong_count: int, avg_score: float, response_time_ms: int) -> str:
        """
        Fast heuristic action recommender (no LLM call).
        Returns recommendation string.
        """
        if wrong_count >= 2 or avg_score < 0.35:
            return "doubt_resolve"
        if wrong_count >= 1 or avg_score < 0.55:
            return "slow_down"
        if response_time_ms > 60_000:  # >60s — struggled but got it
            return "slow_down"
        return "continue"


_evaluator: EvaluatorAgent | None = None

def get_evaluator() -> EvaluatorAgent:
    global _evaluator
    if _evaluator is None:
        _evaluator = EvaluatorAgent()
    return _evaluator
