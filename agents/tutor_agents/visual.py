"""
Visual Agent — dedicated Mermaid diagram generator.

Given a concept title + micro-concept description + teaching step context,
generates a clean Mermaid diagram that visually explains the concept.

Diagram types by context:
  - flowchart LR  → algorithms, processes, decision trees
  - sequenceDiagram → protocols, message passing, API calls
  - classDiagram   → OOP, data structures, schema relationships
  - graph TD       → trees, hierarchies, dependency graphs
  - xychart-beta   → data comparisons, complexity graphs

Rules:
  - Never use colors/styles (removed by frontend sanitizer anyway)
  - Keep labels short (< 40 chars)
  - Max 12 nodes
  - Prefer direction: LR for processes, TD for hierarchies
  - Always return valid Mermaid syntax
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings

logger = logging.getLogger(__name__)

VISUAL_SYSTEM = """You are an expert at creating Mermaid diagrams to visually explain computer science and engineering concepts.

Rules (STRICT):
1. Output ONLY the raw Mermaid code — no explanation, no markdown fences, no ```
2. Keep all node labels under 35 characters
3. Max 12 nodes
4. No fill/stroke/color/style directives
5. No special characters in labels that break Mermaid (use quotes around labels with parentheses)
6. Choose the most appropriate diagram type for the concept

Diagram type selection guide:
- Algorithm / process → flowchart LR
- Class hierarchy / OOP → classDiagram
- Message passing / protocol → sequenceDiagram
- Tree / hierarchy → graph TD
- State machine → stateDiagram-v2
- Timeline of steps → flowchart TD"""


VISUAL_USER = """Generate a Mermaid diagram to visually explain this concept for a university student.

Step title: {title}
Concept: {micro_concept}
Subject: {subject_code}
Key terms to include: {key_terms}

Return ONLY the raw Mermaid code."""


@dataclass
class VisualAgent:
    model: str = field(default_factory=lambda: settings.groq_model)

    def _get_llm(self) -> ChatGroq:
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=self.model,
            temperature=0.15,
            max_tokens=600,
        )

    async def generate_diagram(
        self,
        *,
        title: str,
        micro_concept: str,
        subject_code: str,
        key_terms: list[str] | None = None,
    ) -> str | None:
        """
        Generate a Mermaid diagram string for a concept.
        Returns raw Mermaid code or None if generation fails.
        """
        llm = self._get_llm()
        user_msg = VISUAL_USER.format(
            title=title,
            micro_concept=micro_concept,
            subject_code=subject_code,
            key_terms=", ".join(key_terms or []) or "none specified",
        )
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content=VISUAL_SYSTEM),
                    HumanMessage(content=user_msg),
                ])
            )
            raw = result.content.strip()
            # Strip any accidental markdown fences
            raw = self._clean_mermaid(raw)
            if not raw or len(raw) < 10:
                return None
            return raw
        except Exception as e:
            logger.warning(f"VisualAgent.generate_diagram failed: {e}")
            return None

    @staticmethod
    def _clean_mermaid(raw: str) -> str:
        """Remove markdown fences and style lines that break the frontend sanitizer."""
        # Strip ```mermaid ... ``` or ``` ... ```
        raw = re.sub(r"^```(?:mermaid)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE)
        # Strip style/classDef lines
        lines = [
            l for l in raw.split("\n")
            if not re.match(r"^\s*(style\s+|classDef\s+|linkStyle\s+)", l, re.IGNORECASE)
        ]
        return "\n".join(lines).strip()

    async def generate_step_animation(
        self,
        *,
        algorithm: str,
        subject_code: str,
        num_steps: int = 5,
    ) -> list[str]:
        """
        Generate a sequence of Mermaid frames that animate an algorithm step-by-step.
        Returns list of Mermaid strings (one per animation frame).
        """
        # For now: generate a single comprehensive diagram
        # Full step-animation requires multiple LLM calls — can be Phase 4 feature
        diagram = await self.generate_diagram(
            title=algorithm,
            micro_concept=f"Step-by-step {algorithm} animation ({num_steps} steps)",
            subject_code=subject_code,
        )
        return [diagram] if diagram else []


_visual: VisualAgent | None = None

def get_visual_agent() -> VisualAgent:
    global _visual
    if _visual is None:
        _visual = VisualAgent()
    return _visual
