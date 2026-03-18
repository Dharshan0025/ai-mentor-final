"""
Planner Agent — decomposes a topic + student DNA into a structured lesson plan.

Given:
  - subject_code, topic
  - student's SM-2 history (weak areas, mastered concepts, bloom level)
  - teaching style preference

Produces:
  - Ordered list of micro-concept steps
  - Estimated minutes per step
  - Checkpoint positions (after every N steps)
  - Bloom's taxonomy level per step
  - RAG context hints (which chunks are most relevant per step)

Uses Groq (LLaMA 3.3 70B) for fast structured output.
"""
import json
import logging
from dataclasses import dataclass, field

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings

logger = logging.getLogger(__name__)

PLANNER_SYSTEM = """You are an expert AI lesson planner for university students.
Your job: given a topic and student profile, decompose the topic into a precise, pedagogically-ordered
list of micro-concept STEPS. Each step = one atomic concept that can be taught in 2-4 minutes.

Rules:
- Steps must build on each other (foundational → advanced)
- Identify EXACTLY which steps need a checkpoint quiz (every 2-3 steps)
- Assign a Bloom's taxonomy level (1=Remember, 2=Understand, 3=Apply, 4=Analyze, 5=Evaluate, 6=Create)
- If student has weak areas matching this topic, place those concepts EARLIER and flag them
- Keep diagrams_needed true ONLY for steps that genuinely benefit from a visual aid
- Return ONLY valid JSON, no markdown

Output JSON format:
{
  "topic": "<topic>",
  "estimated_total_minutes": <int>,
  "bloom_level": <1-6 overall>,
  "steps": [
    {
      "step_num": 1,
      "title": "<concise step title>",
      "micro_concept": "<what exactly is taught>",
      "estimated_minutes": <int>,
      "bloom_level": <1-6>,
      "checkpoint_after": <bool>,
      "diagrams_needed": <bool>,
      "revisit": <bool>,   // true if student has struggled with this before
      "key_terms": ["<term1>", "<term2>"]
    }
  ],
  "checkpoints": <total checkpoint count>,
  "teaching_strategy": "<brief teaching approach for this student>"
}"""


PLANNER_USER = """Subject: {subject_code}
Topic: {topic}
Teaching style: {style}
Student bloom level: {current_bloom}
Weak areas in this subject: {weak_areas}
Topics already mastered: {mastered}
RAG context available: {has_rag}

Syllabus reference:
{syllabus_context}

Create a step-by-step lesson plan for this topic. Generate between 4-8 steps."""


@dataclass
class PlannerAgent:
    model: str = field(default_factory=lambda: settings.groq_model)
    temperature: float = 0.2

    def _get_llm(self) -> ChatGroq:
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=self.model,
            temperature=self.temperature,
            max_tokens=1800,
        )

    async def plan(
        self,
        *,
        subject_code: str,
        topic: str,
        teaching_style: str = "visual + example-based",
        current_bloom: int = 2,
        weak_areas: list[str] | None = None,
        mastered_concepts: list[str] | None = None,
        syllabus_context: str = "",
        has_rag: bool = False,
    ) -> dict:
        """
        Generate a structured lesson plan dict.
        Falls back to a minimal plan on LLM error.
        """
        import asyncio
        llm = self._get_llm()
        user_msg = PLANNER_USER.format(
            subject_code=subject_code,
            topic=topic,
            style=teaching_style,
            current_bloom=current_bloom,
            weak_areas=", ".join(weak_areas or []) or "None identified",
            mastered=", ".join(mastered_concepts or []) or "None yet",
            has_rag="Yes" if has_rag else "No",
            syllabus_context=syllabus_context[:1200] if syllabus_context else "Not available",
        )
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content=PLANNER_SYSTEM),
                    HumanMessage(content=user_msg),
                ])
            )
            raw = result.content.strip()
            # Strip markdown code fences if LLM wraps output
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            plan = json.loads(raw)
            plan.setdefault("topic", topic)
            plan.setdefault("estimated_total_minutes", len(plan.get("steps", [])) * 3)
            return plan
        except Exception as e:
            logger.warning(f"PlannerAgent fallback: {e}")
            return self._fallback_plan(topic)

    @staticmethod
    def _fallback_plan(topic: str) -> dict:
        """Minimal 4-step plan when LLM fails."""
        steps = [
            {"step_num": i + 1, "title": f"Part {i + 1}: {topic}",
             "micro_concept": f"Core concept {i + 1}", "estimated_minutes": 3,
             "bloom_level": min(i + 1, 3), "checkpoint_after": (i % 2 == 1),
             "diagrams_needed": i == 1, "revisit": False, "key_terms": []}
            for i in range(4)
        ]
        return {
            "topic": topic, "estimated_total_minutes": 12,
            "bloom_level": 2, "steps": steps, "checkpoints": 2,
            "teaching_strategy": "visual + example-based",
        }


_planner: PlannerAgent | None = None

def get_planner() -> PlannerAgent:
    global _planner
    if _planner is None:
        _planner = PlannerAgent()
    return _planner
