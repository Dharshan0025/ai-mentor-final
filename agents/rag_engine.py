"""
RAG Engine — LangChain + Supabase pgvector
Upgraded V2: adds query/retrieval functions on top of the existing
PDF ingestion pipeline. Uses AWS Bedrock Titan Embeddings.

Functions:
  - ingest_pdf()            — existing PDF ingestion (unchanged)
  - ingest_syllabus_text()  — ingest raw text from subject_syllabus rows
  - query_rag()             — semantic search → top-k chunks for a query
  - build_context()         — assemble RAG context string for LLM prompts
  - get_syllabus_context()  — retrieve relevant syllabus segments for a topic
"""
import asyncio
import os
import json
import logging
from typing import Optional
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_aws import BedrockEmbeddings
from db import db, get_pool, close_pool
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Embedding singleton ────────────────────────────────────────────────────
_embeddings: Optional[BedrockEmbeddings] = None


def _get_embeddings() -> BedrockEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = BedrockEmbeddings(
            model_id="amazon.titan-embed-text-v2:0",
            region_name=settings.aws_region,
        )
    return _embeddings


# ── Existing: PDF ingest ───────────────────────────────────────────────────

async def ingest_pdf(filepath: str, subject_code: str, student_id: int = None):
    """Ingest a PDF file into the pgvector documents table."""
    logger.info(f"Loading {filepath}...")
    try:
        loader = PyMuPDFLoader(filepath)
        docs = loader.load()
    except Exception as e:
        logger.error(f"Failed to load PDF: {e}")
        return

    logger.info(f"Splitting {len(docs)} pages...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = text_splitter.split_documents(docs)
    logger.info(f"Generated {len(chunks)} chunks.")

    embeddings = _get_embeddings()
    filename = os.path.basename(filepath)
    success_count = 0
    await get_pool()

    batch_size = 10
    total_batches = (len(chunks) - 1) // batch_size + 1

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [chunk.page_content for chunk in batch]
        logger.info(f"Embedding batch {i // batch_size + 1}/{total_batches}...")
        try:
            vectors = embeddings.embed_documents(texts)
            for j, vector in enumerate(vectors):
                await db.insert_document_chunk(
                    filename=filename, content=texts[j], embedding=vector,
                    subject_code=subject_code, student_db_id=student_id,
                    doc_type="study_material",
                )
                success_count += 1
        except Exception as e:
            logger.error(f"Error embedding batch {i // batch_size + 1}: {e}")

    logger.info(f"Successfully ingested {success_count} chunks into Supabase pgvector.")


# ── NEW: Syllabus text ingest ─────────────────────────────────────────────

async def ingest_syllabus_text(subject_code: str, texts: list[str], source: str = "syllabus") -> int:
    """
    Ingest raw text chunks (e.g., from subject_syllabus rows) into documents.
    Returns number of chunks successfully ingested.
    """
    if not texts:
        return 0
    embeddings = _get_embeddings()
    await get_pool()
    success = 0
    batch_size = 10
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            vectors = embeddings.embed_documents(batch)
            for j, vector in enumerate(vectors):
                await db.insert_document_chunk(
                    filename=f"syllabus_{subject_code}",
                    content=batch[j],
                    embedding=vector,
                    subject_code=subject_code,
                    doc_type=source,
                )
                success += 1
        except Exception as e:
            logger.error(f"Syllabus ingest error (batch {i}): {e}")
    return success


# ── NEW: Semantic search / RAG query ──────────────────────────────────────

async def query_rag(
    query: str,
    subject_code: str | None = None,
    student_db_id: int | None = None,
    top_k: int = 5,
    min_similarity: float = 0.4,
) -> list[dict]:
    """
    Embed the query and perform cosine similarity search in pgvector.
    Returns top-k chunks as list of { content, subject_code, filename, similarity }.

    Uses the existing `documents` table with vector(<dim>) column.
    """
    if not query or not query.strip():
        return []

    embeddings = _get_embeddings()
    loop = asyncio.get_event_loop()

    try:
        vector = await loop.run_in_executor(
            None, lambda: embeddings.embed_query(query)
        )
    except Exception as e:
        logger.error(f"RAG embed_query failed: {e}")
        return []

    pool = await get_pool()
    vector_str = json.dumps(vector)

    try:
        async with pool.acquire() as conn:
            if subject_code and student_db_id:
                rows = await conn.fetch(
                    """
                    SELECT content, subject_code, filename,
                           1 - (embedding <=> $1::extensions.vector) AS similarity
                    FROM documents
                    WHERE subject_code = $2
                      AND (student_id = $3 OR student_id IS NULL)
                      AND 1 - (embedding <=> $1::extensions.vector) >= $4
                    ORDER BY embedding <=> $1::extensions.vector
                    LIMIT $5
                    """,
                    vector_str, subject_code, student_db_id, min_similarity, top_k,
                )
            elif subject_code:
                rows = await conn.fetch(
                    """
                    SELECT content, subject_code, filename,
                           1 - (embedding <=> $1::extensions.vector) AS similarity
                    FROM documents
                    WHERE subject_code = $2
                      AND 1 - (embedding <=> $1::extensions.vector) >= $3
                    ORDER BY embedding <=> $1::extensions.vector
                    LIMIT $4
                    """,
                    vector_str, subject_code, min_similarity, top_k,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT content, subject_code, filename,
                           1 - (embedding <=> $1::extensions.vector) AS similarity
                    FROM documents
                    WHERE 1 - (embedding <=> $1::extensions.vector) >= $2
                    ORDER BY embedding <=> $1::extensions.vector
                    LIMIT $3
                    """,
                    vector_str, min_similarity, top_k,
                )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"RAG pgvector search failed: {e}")
        return []


async def build_context(
    query: str,
    subject_code: str | None = None,
    student_db_id: int | None = None,
    top_k: int = 4,
    max_chars: int = 3000,
) -> str:
    """
    Build a RAG context string to inject into LLM prompts.
    Returns formatted text block with retrieved chunks.
    Returns empty string if no relevant context found.
    """
    chunks = await query_rag(
        query, subject_code=subject_code,
        student_db_id=student_db_id, top_k=top_k,
    )
    if not chunks:
        return ""

    parts = []
    total = 0
    for i, chunk in enumerate(chunks, 1):
        text = chunk.get("content", "").strip()
        if not text:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        snippet = text[:remaining]
        parts.append(f"[Source {i}: {chunk.get('filename', 'unknown')}]\n{snippet}")
        total += len(snippet)

    if not parts:
        return ""

    return "--- Relevant Study Material ---\n" + "\n\n".join(parts) + "\n---"


async def get_syllabus_context(subject_code: str, topic: str) -> str:
    """
    Retrieve relevant syllabus segments from Supabase subject_syllabus table
    and format them as a context string for teaching prompts.
    """
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT unit_number, unit_title, topics
                FROM subject_syllabus
                WHERE subject_code = $1
                ORDER BY unit_number
                """,
                subject_code,
            )
        if not rows:
            return ""

        # Find units whose topics mention the query topic
        topic_lower = topic.lower()
        relevant = []
        for r in rows:
            all_topics = r["topics"] or []
            matching = [t for t in all_topics if topic_lower in t.lower() or t.lower() in topic_lower]
            if matching:
                relevant.append({
                    "unit": r["unit_number"],
                    "title": r["unit_title"],
                    "topics": matching,
                })

        if not relevant:
            # Return first unit as fallback context
            first = dict(rows[0])
            return f"Unit {first['unit_number']}: {first['unit_title']}\nTopics: {', '.join(first['topics'] or [])}"

        lines = []
        for r in relevant:
            lines.append(f"Unit {r['unit']}: {r['title']}\nTopics: {', '.join(r['topics'])}")

        return "\n\n".join(lines)
    except Exception as e:
        logger.warning(f"get_syllabus_context failed: {e}")
        return ""


# ── Entry point (unchanged) ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python rag_engine.py <path_to_pdf> <subject_code> [student_db_id]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    subject = sys.argv[2]
    student = int(sys.argv[3]) if len(sys.argv) > 3 else None

    asyncio.run(ingest_pdf(pdf_path, subject, student))
