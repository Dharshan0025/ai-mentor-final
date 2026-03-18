"""
Doubt Resolver Agent — handles repeated confusion questions differently.

When a student asks the SAME concept multiple times (detected via confusionMapRef in frontend
or via tutor_checkpoints records), this agent takes over and re-explains using:
  1. A completely different analogy
  2. A concrete real-world example
  3. A step-by-step breakdown (not summary)
  4. A Socratic question to test if they now understand

Key features:
  - Tracks explanation history per topic to AVOID repeating the same approach
  - Generates 3 types of explanations: analogy, example, breakdown
  - Can generate a custom mini-checkpoint question at the end
  - Used by tutor_graph when EvaluatorAgent returns recommendation='doubt_resolve'
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings

logger = logging.getLogger(__name__)

ExplanationMode = Literal["analogy", "example", "breakdown", "socratic"]

DOUBT_SYSTEM = """You are a patient, creative AI tutor. A student is confused about a concept
and has already received the standard explanation. You MUST use a DIFFERENT approach.

Approach selection:
- "analogy": Use a creative real-world analogy (NOT from textbooks)
- "example":  Walk through a concrete, specific example with exact values/names
- "breakdown": Decompose into 3-4 atomic sub-steps, explain each separately
- "socratic": Ask 2-3 guiding questions that lead the student to the answer themselves

Output ONLY valid JSON:
{
  "mode": "<analogy|example|breakdown|socratic>",
  "explanation": "<your alternative explanation — 3-6 sentences, natural spoken English>",
  "mini_question": "<A single short question to check if student now understands>",
  "key_insight": "<The ONE thing they must remember, in 10 words or less>"
}"""


DOUBT_USER = """Subject: {subject_code}
Topic: {topic}
Concept the student is confused about: {concept}
Number of wrong attempts: {wrong_count}
Previous explanation modes used: {prev_modes}
Student's last wrong answer (if any): {last_wrong_answer}
Misconception identified: {misconception}

Confusion context: {confusion_context}

Use mode: {preferred_mode}
Generate a fresh, creative re-explanation that's NOTHING like the standard explanation."""


@dataclass
class DoubtResolverAgent:
    model: str = field(default_factory=lambda: settings.groq_model)
    # Track which modes were used per topic to avoid repetition
    _mode_history: dict = field(default_factory=dict)

    def _get_llm(self) -> ChatGroq:
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=self.model,
            temperature=0.7,   # Higher temp for creative explanations
            max_tokens=700,
        )

    def _select_mode(self, topic_key: str, wrong_count: int) -> ExplanationMode:
        """Pick the next explanation mode, rotating through modes to avoid repetition."""
        used = self._mode_history.get(topic_key, [])
        all_modes: list[ExplanationMode] = ["analogy", "example", "breakdown", "socratic"]
        # Prefer modes not yet used
        available = [m for m in all_modes if m not in used]
        if not available:
            available = all_modes  # Reset cycle
        # For high wrong_count, prefer breakdown (most explicit)
        if wrong_count >= 3 and "breakdown" in available:
            chosen = "breakdown"
        elif wrong_count >= 2 and "example" in available:
            chosen = "example"
        else:
            chosen = available[0]
        return chosen

    def _record_mode(self, topic_key: str, mode: ExplanationMode) -> None:
        if topic_key not in self._mode_history:
            self._mode_history[topic_key] = []
        self._mode_history[topic_key].append(mode)
        # Keep only last 3
        self._mode_history[topic_key] = self._mode_history[topic_key][-3:]

    async def resolve(
        self,
        *,
        subject_code: str,
        topic: str,
        concept: str,
        wrong_count: int = 2,
        last_wrong_answer: str | None = None,
        misconception: str | None = None,
        confusion_context: str = "",
        prev_modes: list[str] | None = None,
    ) -> dict:
        """
        Generate a fresh alternative explanation for a confused concept.
        Returns {mode, explanation, mini_question, key_insight}.
        """
        topic_key = f"{subject_code}::{concept}"
        preferred = self._select_mode(topic_key, wrong_count)
        self._record_mode(topic_key, preferred)

        llm = self._get_llm()
        user_msg = DOUBT_USER.format(
            subject_code=subject_code,
            topic=topic,
            concept=concept,
            wrong_count=wrong_count,
            prev_modes=", ".join(prev_modes or []) or "standard",
            last_wrong_answer=last_wrong_answer or "unknown",
            misconception=misconception or "not identified",
            confusion_context=confusion_context[:500] if confusion_context else "None provided",
            preferred_mode=preferred,
        )

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content=DOUBT_SYSTEM),
                    HumanMessage(content=user_msg),
                ])
            )
            raw = result.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            res = json.loads(raw)
            res.setdefault("mode", preferred)
            res.setdefault("mini_question", f"Can you now explain {concept} in your own words?")
            res.setdefault("key_insight", f"The core of {concept} is...")
            return res
        except Exception as e:
            logger.warning(f"DoubtResolverAgent fallback: {e}")
            return {
                "mode": preferred,
                "explanation": (
                    f"Let's approach {concept} completely differently. "
                    f"Imagine you're explaining it to a friend who has never heard of it. "
                    f"The key idea is: what problem does {concept} solve, and why was it invented? "
                    f"Once you understand the 'why', the 'how' becomes obvious."
                ),
                "mini_question": f"In your own words, what problem does {concept} solve?",
                "key_insight": f"{concept} exists to solve a specific, real problem.",
            }

    def get_mode_history(self, subject_code: str, concept: str) -> list[str]:
        """Get explanation modes already used for a concept this session."""
        return self._mode_history.get(f"{subject_code}::{concept}", [])


_doubt_resolver: DoubtResolverAgent | None = None

def get_doubt_resolver() -> DoubtResolverAgent:
    global _doubt_resolver
    if _doubt_resolver is None:
        _doubt_resolver = DoubtResolverAgent()
    return _doubt_resolver
