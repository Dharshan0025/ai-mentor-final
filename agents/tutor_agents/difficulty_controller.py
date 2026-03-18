"""
Difficulty Controller Agent — dynamically adjusts Bloom's taxonomy level mid-lesson.

Uses student's SM-2 history (avg_score, times_correct, times_wrong, ease_factor)
to decide whether to:
  - ADVANCE: increase Bloom level (student is mastering concepts faster than expected)
  - MAINTAIN: keep current Bloom level
  - RETREAT: lower Bloom level (student is struggling)
  - REMEDIATE: insert a remedial step before continuing

Decision is made PURELY with heuristics (no LLM call) for speed.
Can optionally call LLM to generate a custom remedial explanation.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings

logger = logging.getLogger(__name__)

BloomAction = Literal["advance", "maintain", "retreat", "remediate"]

BLOOM_LABELS = {
    1: "Remember",
    2: "Understand",
    3: "Apply",
    4: "Analyze",
    5: "Evaluate",
    6: "Create",
}

REMEDIAL_SYSTEM = """You are an expert AI tutor. A student is struggling with a concept.
Write a SHORT remedial re-explanation (3-5 sentences) using a COMPLETELY DIFFERENT approach
or analogy than a standard textbook. Be concrete, relatable, and encouraging.
Do NOT use bullet points — write as natural spoken English."""


@dataclass
class DifficultyController:
    """
    Adjusts Bloom's level mid-lesson based on student performance.
    Pure heuristics for speed — no LLM needed for the decision itself.
    """

    # Thresholds
    advance_threshold: float = 0.82    # avg_score above this → advance
    retreat_threshold: float = 0.45    # avg_score below this → retreat
    remediate_threshold: float = 0.30  # avg_score below this → remediate

    def decide(
        self,
        *,
        current_bloom: int,
        avg_score: float,
        times_wrong: int,
        ease_factor: float = 2.5,
        session_pass_rate: float | None = None,
    ) -> tuple[BloomAction, int, str]:
        """
        Returns (action, new_bloom_level, reason_string).
        """
        score = avg_score or 0.0
        ef = ease_factor or 2.5

        # Use session pass rate if available, fallback to avg_score
        effective_score = session_pass_rate if session_pass_rate is not None else score

        if times_wrong >= 3 or effective_score < self.remediate_threshold:
            new_bloom = max(1, current_bloom - 1)
            return "remediate", new_bloom, (
                f"Student scored {effective_score:.0%} — inserting remedial step before continuing"
            )
        elif effective_score < self.retreat_threshold or (ef < 1.6 and times_wrong >= 2):
            new_bloom = max(1, current_bloom - 1)
            return "retreat", new_bloom, (
                f"Ease factor {ef:.2f} + score {effective_score:.0%} — reducing Bloom level to {BLOOM_LABELS[new_bloom]}"
            )
        elif effective_score >= self.advance_threshold and ef >= 2.8 and times_wrong == 0:
            new_bloom = min(6, current_bloom + 1)
            return "advance", new_bloom, (
                f"Excellent performance ({effective_score:.0%}) — advancing to Bloom {BLOOM_LABELS[new_bloom]}"
            )
        else:
            return "maintain", current_bloom, (
                f"Maintaining Bloom {BLOOM_LABELS[current_bloom]} ({effective_score:.0%})"
            )

    async def generate_remedial_explanation(
        self,
        *,
        topic: str,
        concept: str,
        subject_code: str,
        misconception: str | None = None,
    ) -> str:
        """
        Generate a short alternative explanation for a concept a student is struggling with.
        Uses a different approach/analogy than the original narration.
        """
        llm = ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0.6,
            max_tokens=300,
        )
        misconception_hint = (
            f"\nThe student's specific misconception was: {misconception}" if misconception else ""
        )
        user_msg = (
            f"Subject: {subject_code}\n"
            f"Topic: {topic}\n"
            f"Concept the student is struggling with: {concept}"
            f"{misconception_hint}\n\n"
            "Write a SHORT alternative explanation using a completely different analogy or approach."
        )
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content=REMEDIAL_SYSTEM),
                    HumanMessage(content=user_msg),
                ])
            )
            return result.content.strip()
        except Exception as e:
            logger.warning(f"DifficultyController.remedial failed: {e}")
            return (
                f"Let me try explaining {concept} differently. Think of it as a practical process: "
                f"we break the problem into smaller pieces, solve each one, and combine the results. "
                f"The key insight is understanding WHY each step exists, not just HOW to do it."
            )

    def get_bloom_label(self, level: int) -> str:
        return BLOOM_LABELS.get(level, "Understand")


_controller: DifficultyController | None = None

def get_difficulty_controller() -> DifficultyController:
    global _controller
    if _controller is None:
        _controller = DifficultyController()
    return _controller
