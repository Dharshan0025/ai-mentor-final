"""
Knowledge Retrieval Agent — LangChain RAG over syllabus + PDF content.

Wraps rag_engine.query_rag and get_syllabus_context into a clean agent interface.

Provides:
  1. topic_context()  — RAG chunks + syllabus for a given topic (used by Planner + Tutor)
  2. step_context()   — RAG chunks for a specific concept/step (injected into narration prompts)
  3. question_context() — RAG context relevant to a student question (used by doubt resolver + Q&A)
  4. ingest_check()   — Check if documents exist for a subject (to decide if RAG is usable)

Falls back gracefully if no documents are ingested.
"""
import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeRetrievalAgent:
    top_k: int = 4
    max_chars: int = 2500

    async def topic_context(
        self,
        *,
        subject_code: str,
        topic: str,
        student_db_id: int | None = None,
    ) -> dict:
        """
        Retrieve RAG chunks + syllabus context for a topic.
        Returns { rag_chunks, syllabus_context, rag_available }.
        Used by Planner to enrich the lesson plan.
        """
        from rag_engine import query_rag, get_syllabus_context, build_context

        try:
            chunks, syllabus = await asyncio.gather(
                query_rag(
                    topic,
                    subject_code=subject_code,
                    student_db_id=student_db_id,
                    top_k=self.top_k,
                ),
                get_syllabus_context(subject_code, topic),
            )
            context_str = await build_context(
                topic,
                subject_code=subject_code,
                student_db_id=student_db_id,
                top_k=self.top_k,
                max_chars=self.max_chars,
            )
            return {
                "rag_chunks":       chunks,
                "syllabus_context": syllabus,
                "context_string":   context_str,
                "rag_available":    bool(chunks),
                "chunk_count":      len(chunks),
            }
        except Exception as e:
            logger.warning(f"KnowledgeRetrievalAgent.topic_context failed: {e}")
            return {
                "rag_chunks":       [],
                "syllabus_context": "",
                "context_string":   "",
                "rag_available":    False,
                "chunk_count":      0,
            }

    async def step_context(
        self,
        *,
        subject_code: str,
        step_title: str,
        micro_concept: str,
        student_db_id: int | None = None,
    ) -> str:
        """
        RAG context for a specific teaching step.
        Returns formatted context string for injection into narration prompts.
        """
        from rag_engine import build_context
        query = f"{step_title}: {micro_concept}"
        try:
            ctx = await build_context(
                query,
                subject_code=subject_code,
                student_db_id=student_db_id,
                top_k=3,
                max_chars=1200,
            )
            return ctx
        except Exception as e:
            logger.warning(f"KnowledgeRetrievalAgent.step_context failed: {e}")
            return ""

    async def question_context(
        self,
        *,
        question: str,
        subject_code: str | None = None,
        student_db_id: int | None = None,
        top_k: int = 4,
    ) -> str:
        """
        RAG context for a student Q&A question.
        Used by the Q&A endpoint and doubt_resolver to ground answers in study material.
        Returns formatted context string.
        """
        from rag_engine import build_context
        try:
            return await build_context(
                question,
                subject_code=subject_code,
                student_db_id=student_db_id,
                top_k=top_k,
                max_chars=1800,
            )
        except Exception as e:
            logger.warning(f"KnowledgeRetrievalAgent.question_context failed: {e}")
            return ""

    async def ingest_check(self, subject_code: str) -> dict:
        """
        Check if any documents are ingested for a subject.
        Returns { has_documents, chunk_count }.
        """
        from db import get_pool
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM documents WHERE subject_code = $1",
                    subject_code,
                )
            count = int(row["cnt"]) if row else 0
            return {"has_documents": count > 0, "chunk_count": count}
        except Exception as e:
            logger.warning(f"KnowledgeRetrievalAgent.ingest_check failed: {e}")
            return {"has_documents": False, "chunk_count": 0}

    async def get_relevant_questions(
        self,
        *,
        subject_code: str,
        topic: str,
        student_db_id: int | None = None,
        n: int = 3,
    ) -> list[str]:
        """
        Retrieve likely exam question stems from RAG documents for a topic.
        Used by PlannerAgent to generate smarter checkpoints.
        """
        from rag_engine import query_rag
        try:
            chunks = await query_rag(
                f"exam questions {topic} {subject_code}",
                subject_code=subject_code,
                student_db_id=student_db_id,
                top_k=n,
                min_similarity=0.35,
            )
            return [c["content"][:300] for c in chunks]
        except Exception:
            return []


_kr: KnowledgeRetrievalAgent | None = None

def get_knowledge_retrieval() -> KnowledgeRetrievalAgent:
    global _kr
    if _kr is None:
        _kr = KnowledgeRetrievalAgent()
    return _kr
