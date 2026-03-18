"""
Tutor Graph — V5 Multi-Agent LangGraph Orchestration
=====================================================

This is the BRAIN of the AI Teacher. It coordinates all 6 specialist agents
into a coherent teaching loop that adapts to the student in real-time.

Graph Flow:
  ┌─────────────────────────────────────────────────────────┐
  │  START                                                  │
  │     ↓                                                   │
  │  [knowledge_retrieval] ← RAG + Syllabus fetch           │
  │     ↓                                                   │
  │  [planner]             ← Lesson plan with Bloom levels  │
  │     ↓                                                   │
  │  [difficulty_check]    ← Set Bloom from SM-2 history    │
  │     ↓                                                   │
  │  FOR EACH STEP:                                         │
  │    [visual?] ← Generate Mermaid if step.diagrams_needed │
  │    [narrate] ← Generate step narration (streaming-ready)│
  │    [checkpoint?] ← Generate Q per step.checkpoint_after │
  │       ↓ (after checkpoint answer)                       │
  │    [evaluate] ← Score answer + recommend action         │
  │       ↓                                                 │
  │    [doubt_resolve?] ← If recommendation=doubt_resolve   │
  │       ↓                                                 │
  │    [difficulty_adjust] ← Adjust Bloom mid-lesson        │
  │  END STEP LOOP                                          │
  │     ↓                                                   │
  │  [lesson_complete]     ← Summary + DNA update           │
  └─────────────────────────────────────────────────────────┘

NOTE: For SSE streaming compatibility this graph is used in TWO ways:
  1. Preflight: plan() → get lesson plan synchronously before streaming
  2. Per-step: step_run() → run visual + narration per step during streaming
  3. Post-checkpoint: evaluate() → called after student answers quiz
  4. Doubt: resolve_doubt() → called when student is confused

The lesson streaming endpoint in main.py calls these methods individually
rather than running the full graph at once (for SSE compatibility).
"""
import asyncio
import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)


class TutorGraph:
    """
    Multi-agent lesson orchestrator.
    Coordinates: KnowledgeRetrieval → Planner → DifficultyController
                 → Visual → Narration → Evaluator → DoubtResolver
    """

    def __init__(self):
        # Lazy-load agents to avoid circular imports at module level
        self._kr = None
        self._planner = None
        self._evaluator = None
        self._visual = None
        self._dc = None
        self._doubt = None

    # ── Agent Lazy Loaders ─────────────────────────────────────────────────

    def _get_kr(self):
        if self._kr is None:
            from tutor_agents.knowledge_retrieval import get_knowledge_retrieval
            self._kr = get_knowledge_retrieval()
        return self._kr

    def _get_planner(self):
        if self._planner is None:
            from tutor_agents.planner import get_planner
            self._planner = get_planner()
        return self._planner

    def _get_evaluator(self):
        if self._evaluator is None:
            from tutor_agents.evaluator import get_evaluator
            self._evaluator = get_evaluator()
        return self._evaluator

    def _get_visual(self):
        if self._visual is None:
            from tutor_agents.visual import get_visual_agent
            self._visual = get_visual_agent()
        return self._visual

    def _get_dc(self):
        if self._dc is None:
            from tutor_agents.difficulty_controller import get_difficulty_controller
            self._dc = get_difficulty_controller()
        return self._dc

    def _get_doubt(self):
        if self._doubt is None:
            from tutor_agents.doubt_resolver import get_doubt_resolver
            self._doubt = get_doubt_resolver()
        return self._doubt

    # ── Phase 1: Pre-Lesson Planning ───────────────────────────────────────

    async def plan_lesson(
        self,
        *,
        subject_code: str,
        topic: str,
        student_db_id: int | None = None,
        teaching_style: str = "visual + example-based",
        current_bloom: int = 2,
        weak_areas: list[str] | None = None,
        mastered_concepts: list[str] | None = None,
    ) -> dict:
        """
        Full pre-lesson planning:
        1. Fetch RAG context + syllabus
        2. Run PlannerAgent with full context
        3. Run DifficultyController to set initial Bloom level
        4. Return enriched lesson plan

        This is called BEFORE streaming starts, replacing the old /lesson-plan endpoint.
        """
        kr = self._get_kr()
        planner = self._get_planner()
        dc = self._get_dc()

        # Step 1: Knowledge retrieval (parallel)
        rag_data, ingest_info = await asyncio.gather(
            kr.topic_context(
                subject_code=subject_code,
                topic=topic,
                student_db_id=student_db_id,
            ),
            kr.ingest_check(subject_code),
        )

        # Step 2: Plan lesson with full context
        plan = await planner.plan(
            subject_code=subject_code,
            topic=topic,
            teaching_style=teaching_style,
            current_bloom=current_bloom,
            weak_areas=weak_areas or [],
            mastered_concepts=mastered_concepts or [],
            syllabus_context=rag_data.get("syllabus_context", ""),
            has_rag=rag_data.get("rag_available", False),
        )

        # Step 3: Difficulty adjustment based on SM-2 history
        if weak_areas:
            # Student has known struggles — check if we should retreat
            avg_score = 0.5   # Default when we don't have per-topic score
            action, adjusted_bloom, reason = dc.decide(
                current_bloom=current_bloom,
                avg_score=avg_score,
                times_wrong=len(weak_areas),
                ease_factor=2.0,  # Lower EF if weak areas exist
            )
            logger.info(f"DifficultyController: {action} → Bloom {adjusted_bloom} ({reason})")
        else:
            action, adjusted_bloom = "maintain", current_bloom

        # Enrich plan with orchestration metadata
        plan["bloom_level"] = adjusted_bloom
        plan["bloom_action"] = action
        plan["rag_available"] = rag_data.get("rag_available", False)
        plan["chunk_count"] = rag_data.get("chunk_count", 0)
        plan["has_documents"] = ingest_info.get("has_documents", False)
        plan["rag_context"] = rag_data.get("context_string", "")
        plan["syllabus_context"] = rag_data.get("syllabus_context", "")

        return plan

    # ── Phase 2: Per-Step Execution ────────────────────────────────────────

    async def prepare_step(
        self,
        *,
        subject_code: str,
        step: dict,
        student_db_id: int | None = None,
    ) -> dict:
        """
        Prepare a single lesson step:
        1. Fetch step-level RAG context
        2. Generate Mermaid diagram (if step.diagrams_needed)

        Returns step enriched with { rag_context, diagram }.
        This is called DURING streaming, before the step narration is generated.
        """
        kr = self._get_kr()
        visual = self._get_visual()

        step_rag = ""
        diagram = None

        # Run RAG + visual in parallel when both needed
        if step.get("diagrams_needed", False):
            step_rag_task = kr.step_context(
                subject_code=subject_code,
                step_title=step.get("title", ""),
                micro_concept=step.get("micro_concept", ""),
                student_db_id=student_db_id,
            )
            visual_task = visual.generate_diagram(
                title=step.get("title", ""),
                micro_concept=step.get("micro_concept", ""),
                subject_code=subject_code,
                key_terms=step.get("key_terms", []),
            )
            step_rag, diagram = await asyncio.gather(step_rag_task, visual_task)
        else:
            step_rag = await kr.step_context(
                subject_code=subject_code,
                step_title=step.get("title", ""),
                micro_concept=step.get("micro_concept", ""),
                student_db_id=student_db_id,
            )

        return {
            **step,
            "rag_context": step_rag,
            "diagram":     diagram,
        }

    # ── Phase 3: Post-Checkpoint Evaluation ───────────────────────────────

    async def evaluate_checkpoint(
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
        Deep evaluation of a checkpoint answer by EvaluatorAgent.
        Also determines if DifficultyController should adjust Bloom level.
        Returns full evaluation dict + optional Bloom adjustment.
        """
        evaluator = self._get_evaluator()
        dc = self._get_dc()

        # Evaluate answer
        evaluation = await evaluator.evaluate(
            subject_code=subject_code,
            topic=topic,
            question=question,
            student_answer=student_answer,
            correct_answer=correct_answer,
            question_type=question_type,
            response_time_ms=response_time_ms,
            prev_score=prev_score,
            wrong_count=wrong_count,
        )

        # Check if Bloom needs adjustment
        bloom_action = "maintain"
        bloom_level = 2
        if prev_score is not None:
            new_score = evaluation.get("score", 0.0)
            updated_avg = (prev_score + new_score) / 2
            bloom_action, bloom_level, _ = dc.decide(
                current_bloom=2,
                avg_score=updated_avg,
                times_wrong=wrong_count,
            )

        evaluation["bloom_action"] = bloom_action
        evaluation["bloom_level"] = bloom_level
        return evaluation

    # ── Phase 4: Doubt Resolution ─────────────────────────────────────────

    async def resolve_doubt(
        self,
        *,
        subject_code: str,
        topic: str,
        concept: str,
        wrong_count: int = 2,
        last_wrong_answer: str | None = None,
        misconception: str | None = None,
        student_db_id: int | None = None,
    ) -> dict:
        """
        Full doubt resolution:
        1. Fetch relevant RAG context for the confused concept
        2. Generate alternative explanation via DoubtResolverAgent
        3. Generate a new Mermaid diagram for the concept (if visual helps)

        Returns { explanation, mini_question, key_insight, mode, diagram?, rag_context }
        """
        kr = self._get_kr()
        doubt = self._get_doubt()
        visual = self._get_visual()

        # Fetch context + generate fresh explanation + diagram in parallel
        context_task = kr.question_context(
            question=f"explain {concept} in {topic}",
            subject_code=subject_code,
            student_db_id=student_db_id,
            top_k=3,
        )
        resolve_task = doubt.resolve(
            subject_code=subject_code,
            topic=topic,
            concept=concept,
            wrong_count=wrong_count,
            last_wrong_answer=last_wrong_answer,
            misconception=misconception,
            prev_modes=doubt.get_mode_history(subject_code, concept),
        )
        diagram_task = visual.generate_diagram(
            title=concept,
            micro_concept=f"Alternative visual explanation of {concept}",
            subject_code=subject_code,
        )

        rag_context, resolution, diagram = await asyncio.gather(
            context_task, resolve_task, diagram_task
        )

        resolution["rag_context"] = rag_context
        resolution["diagram"] = diagram
        return resolution

    # ── Q&A Context Enrichment ─────────────────────────────────────────────

    async def enrich_qa(
        self,
        *,
        question: str,
        subject_code: str | None,
        student_db_id: int | None = None,
    ) -> str:
        """
        Retrieve RAG context for a student Q&A question.
        Returns formatted context string to inject into the Q&A LLM prompt.
        """
        kr = self._get_kr()
        return await kr.question_context(
            question=question,
            subject_code=subject_code,
            student_db_id=student_db_id,
        )

    # ── Narration Prompt Builder ───────────────────────────────────────────

    @staticmethod
    def build_step_prompt(
        *,
        subject_code: str,
        topic: str,
        step: dict,
        teaching_style: str,
        bloom_level: int,
        rag_context: str = "",
        previous_concepts: list[str] | None = None,
    ) -> str:
        """
        Build the narration prompt for a lesson step.
        Injects RAG context, Bloom level, teaching style, and step metadata.
        This prompt is passed to the Groq streaming LLM in the lesson endpoint.
        """
        bloom_labels = {
            1: "Remember (recall facts)",
            2: "Understand (explain in own words)",
            3: "Apply (solve problems)",
            4: "Analyze (break down and compare)",
            5: "Evaluate (critique and justify)",
            6: "Create (design and construct)",
        }
        bloom_desc = bloom_labels.get(bloom_level, "Understand")

        rag_section = (
            f"\n\n--- RELEVANT STUDY MATERIAL (use to enrich your explanation) ---\n{rag_context}\n---"
            if rag_context
            else ""
        )

        prev_section = (
            f"\nPreviously taught: {', '.join(previous_concepts[-3:])}"
            if previous_concepts
            else ""
        )

        return (
            f"You are teaching step {step.get('step_num', '?')}: **{step.get('title', '')}**\n"
            f"Micro-concept: {step.get('micro_concept', '')}\n"
            f"Subject: {subject_code} | Topic: {topic}\n"
            f"Teaching style: {teaching_style}\n"
            f"Bloom's level: {bloom_desc}\n"
            f"Key terms to cover: {', '.join(step.get('key_terms', []))}\n"
            f"{prev_section}"
            f"{rag_section}\n\n"
            f"Teach this concept STEP BY STEP. Be concrete, use examples. "
            f"If {step.get('diagrams_needed', False)}, mention that a diagram will appear. "
            f"End with: 'Let me show you a diagram' ONLY if diagrams_needed is true. "
            f"Target Bloom level {bloom_level} — students should be able to {bloom_desc.lower()} after this step."
        )


# ── Module-level singleton ──────────────────────────────────────────────────────

_tutor_graph: TutorGraph | None = None


def get_tutor_graph() -> TutorGraph:
    global _tutor_graph
    if _tutor_graph is None:
        _tutor_graph = TutorGraph()
    return _tutor_graph
