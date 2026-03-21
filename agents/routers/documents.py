import os, json, uuid, asyncio, logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, UploadFile, File, Response, Form
from fastapi.responses import StreamingResponse
from schemas import *
from config import settings
from db import db
from services import get_student_profile

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/rag/search")
async def rag_search(q: str, subject: str = None, top_k: int = 5):
    """
    Semantic search across the embedded syllabus + uploaded documents.
    Returns top-k relevant text chunks.
    Query params: q (required), subject (optional), top_k (default 5)
    """
    from rag_engine import query_rag

    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query 'q' is required")

    chunks = await query_rag(
        query=q.strip(),
        subject_code=subject or None,
        top_k=min(top_k, 10),
        min_similarity=0.3,
    )
    return {
        "query":   q,
        "subject": subject,
        "results": [
            {
                "content":      c.get("content", "")[:800],
                "subject_code": c.get("subject_code", ""),
                "filename":     c.get("filename", ""),
                "similarity":   round(float(c.get("similarity", 0)), 3),
            }
            for c in chunks
        ],
        "total": len(chunks),
    }


@router.post("/admin/rag/ingest-syllabus")
async def admin_ingest_syllabus(background_tasks: BackgroundTasks):
    """
    Admin: re-trigger full syllabus ingestion (fire-and-forget, non-blocking).
    Reads from subject_syllabus DB table → embeds per-unit chunks into documents.
    Returns immediately; ingestion runs in background.
    """
    async def _ingest():
        try:
            from rag_engine import ingest_syllabus_text
            pool = await db.get_pool() if hasattr(db, "get_pool") else None

            pool_local = None
            try:
                from db import get_pool as _get_pool
                pool_local = await _get_pool()
            except Exception:
                pass

            if not pool_local:
                logger.warning("ingest-syllabus: Could not get pool")
                return

            async with pool_local.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT subject_code, unit_number, unit_title, topics FROM subject_syllabus ORDER BY subject_code, unit_number"
                )

            total = 0
            subject_chunks = {}
            for r in rows:
                code  = r["subject_code"]
                unit  = r["unit_number"]
                title = r["unit_title"] or ""
                topics = r["topics"] or []
                text = f"Subject: {code}\nUnit {unit}: {title}\nTopics: {', '.join(topics)}"
                subject_chunks.setdefault(code, []).append(text)

            for code, chunks in subject_chunks.items():
                count = await ingest_syllabus_text(code, chunks, source="syllabus_unit")
                total += count
                logger.info(f"Syllabus ingest: {code} — {count} chunks")

            logger.info(f"Syllabus re-ingest complete: {total} total chunks")
        except Exception as e:
            logger.error(f"Syllabus ingest background error: {e}", exc_info=True)

    background_tasks.add_task(_ingest)
    return {"status": "ingestion_started", "message": "Syllabus embedding running in background"}


@router.post("/student/{student_id}/documents/upload")
async def upload_document(
    student_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject_code: str = Form(default=""),
):
    """
    Upload a PDF study material. Chunks and embeds it into the pgvector documents table.
    Returns immediately; embedding runs in background.
    """
    import aiofiles, os, tempfile

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    MAX_SIZE = 20 * 1024 * 1024  # 20 MB
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    # Save to temp file
    suffix = ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.flush()
    tmp.close()
    tmp_path = tmp.name

    # Save record to student_documents table
    pool = None
    try:
        from db import get_pool
        pool = await get_pool()
    except Exception:
        pass

    doc_id = None
    if pool:
        async with pool.acquire() as conn:
            doc_id = await conn.fetchval(
                """
                INSERT INTO student_documents
                    (student_db_id, filename, original_name, subject_code, file_size_bytes, status)
                VALUES ($1, $2, $3, $4, $5, 'processing')
                RETURNING id
                """,
                student["db_id"],
                os.path.basename(tmp_path),
                file.filename,
                subject_code or None,
                len(content),
            )

    # Embed in background
    db_id  = student["db_id"]
    s_code = subject_code or ""

    async def _embed(path: str, fid: int, did):
        try:
            from rag_engine import ingest_pdf
            chunks_count = await ingest_pdf(path, s_code, fid)
            os.unlink(path)
            if pool and did:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE student_documents SET status='ready', chunks_count=$1 WHERE id=$2",
                        chunks_count or 0, did,
                    )
        except Exception as e:
            logger.error(f"PDF embed error: {e}")
            if pool and did:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE student_documents SET status='error' WHERE id=$1", did
                    )

    background_tasks.add_task(_embed, tmp_path, db_id, doc_id)

    return {
        "doc_id":        doc_id,
        "filename":      file.filename,
        "file_size":     len(content),
        "subject_code":  subject_code,
        "status":        "processing",
        "message":       "PDF uploaded. Embedding in background (ready in ~30s).",
    }


@router.get("/student/{student_id}/documents")
async def list_documents(student_id: str):
    """List all uploaded documents for a student."""
    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, original_name, subject_code, chunks_count, file_size_bytes, status, created_at
                FROM student_documents
                WHERE student_db_id = $1
                ORDER BY created_at DESC
                """,
                student["db_id"],
            )
        return {"documents": [dict(r) for r in rows]}
    except Exception as e:
        logger.error(f"List documents error: {e}")
        return {"documents": []}


@router.delete("/student/{student_id}/documents/{doc_id}")
async def delete_document(student_id: str, doc_id: int):
    """Delete a document and all its embedded chunks."""
    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            doc = await conn.fetchrow(
                "SELECT id, filename FROM student_documents WHERE id=$1 AND student_db_id=$2",
                doc_id, student["db_id"],
            )
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Delete from pgvector documents table
            await conn.execute(
                "DELETE FROM documents WHERE filename=$1", doc["filename"]
            )
            # Delete record
            await conn.execute(
                "DELETE FROM student_documents WHERE id=$1", doc_id
            )
        return {"deleted": True, "doc_id": doc_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/student/{student_id}/pyq/analyze")
async def analyze_pyq_paper(student_id: str, body: dict):
    """
    Analyze a Past Year Question paper.
    Body: { text, subject_code, title? }
    Returns: { topics: [{ name, bloom_level, frequency, weight_pct, likely_exam }], ... }
    """
    from pyq_analyzer import analyze_pyq, save_pyq_analysis
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    text         = (body.get("text") or "").strip()
    subject_code = (body.get("subject_code") or "").strip()
    title        = body.get("title")

    if not text:
        raise HTTPException(status_code=400, detail="'text' is required (paste the question paper)")
    if not subject_code:
        raise HTTPException(status_code=400, detail="'subject_code' is required")

    analysis = await analyze_pyq(text, subject_code)

    # Save to DB (non-blocking on failure)
    try:
        pool = await get_pool()
        analysis_id = await save_pyq_analysis(
            pool, student["db_id"], subject_code, text, analysis, title
        )
        analysis["pyq_id"] = analysis_id
    except Exception as e:
        logger.warning(f"PYQ save failed: {e}")

    return analysis


@router.get("/student/{student_id}/pyq/history")
async def get_pyq_history(student_id: str, limit: int = 10):
    """List past PYQ analyses for a student."""
    from pyq_analyzer import get_pyq_history as _get_history
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    pool = await get_pool()
    return {"analyses": await _get_history(pool, student["db_id"], limit)}


@router.post("/student/{student_id}/notes/generate")
async def generate_student_notes(student_id: str, body: dict):
    """
    Generate structured Markdown notes from a lesson or topic.
    Body: { subject_code, topic, session_id?, lesson_steps?: [...], qa_thread?: [...] }
    Returns: { note_id, title, markdown, html, word_count }
    """
    from notes_generator import generate_notes, save_notes
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    subject_code  = (body.get("subject_code") or "").strip()
    topic         = (body.get("topic") or "").strip()
    session_id    = body.get("session_id")
    lesson_steps  = body.get("lesson_steps") or []
    qa_thread     = body.get("qa_thread") or []

    if not subject_code or not topic:
        raise HTTPException(status_code=400, detail="'subject_code' and 'topic' are required")

    # If no steps provided but session_id is given, try to pull from DB
    if not lesson_steps and session_id:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT step_text AS content, step_num
                    FROM lesson_steps
                    WHERE session_id=$1
                    ORDER BY step_num
                    """,
                    session_id,
                )
            lesson_steps = [dict(r) for r in rows]
        except Exception:
            pass

    notes = await generate_notes(
        subject_code=subject_code,
        topic=topic,
        lesson_steps=lesson_steps,
        qa_thread=qa_thread,
        student_name=student.get("name", "Student"),
    )

    # Save to DB
    note_id = None
    try:
        pool = await get_pool()
        note_id = await save_notes(
            pool, student["db_id"], subject_code, topic, notes, session_id
        )
    except Exception as e:
        logger.warning(f"Notes save failed: {e}")

    return {
        "note_id":    note_id,
        "title":      notes["title"],
        "markdown":   notes["markdown"],
        "html":       notes["html"],
        "word_count": notes["word_count"],
        "subject_code": subject_code,
        "topic":      topic,
    }


@router.get("/student/{student_id}/notes")
async def list_student_notes(student_id: str, limit: int = 20):
    """List all saved notes for a student (summary only)."""
    from notes_generator import list_notes
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    pool = await get_pool()
    return {"notes": await list_notes(pool, student["db_id"], limit)}


@router.get("/student/{student_id}/notes/{note_id}")
async def get_student_note(student_id: str, note_id: int):
    """Fetch a single note with full markdown + html content."""
    from notes_generator import get_note
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    pool = await get_pool()
    note = await get_note(pool, note_id, student["db_id"])
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.delete("/student/{student_id}/notes/{note_id}")
async def delete_student_note(student_id: str, note_id: int):
    """Delete a saved note."""
    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM student_notes WHERE id=$1 AND student_db_id=$2",
                note_id, student["db_id"],
            )
        deleted = result != "DELETE 0"
        return {"deleted": deleted, "note_id": note_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


