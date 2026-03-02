"""
Syllabus RAG Ingest — AI Mentor Sprint 1
Uses sentence-transformers (local, no API key, no rate limits).
Model: all-mpnet-base-v2 — 768-dim, matches documents table exactly.

Run: python ingest_syllabus.py
"""
import asyncio
import sys
import re
import json
sys.path.insert(0, r"D:\Ai-mentor\agents")

from db import get_pool
from config import settings

SYLLABUS_PATH = r"D:\Ai-mentor\all_sem_syllabus_unit_wise.md"
MODEL_NAME = "all-mpnet-base-v2"  # 768-dim, same as documents table


def parse_syllabus_into_chunks(filepath: str) -> list[dict]:
    """Parse markdown syllabus tables into one chunk per subject."""
    chunks = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    sections = re.split(r'\n##\s+', content)

    for section in sections:
        if not section.strip():
            continue

        lines = section.strip().split('\n')
        section_title = lines[0].strip().rstrip('#').strip()

        # Table data rows only (skip header and separator rows)
        data_rows = [
            l for l in lines
            if l.startswith('|')
            and not l.startswith('| :')
            and 'Subject Code' not in l
        ]

        for row in data_rows:
            cols = [c.strip() for c in row.split('|')[1:-1]]
            if len(cols) < 2:
                continue

            code = cols[0].strip()
            title = cols[1].strip()
            if not code or not title:
                continue

            units = cols[2:] if len(cols) > 2 else []
            units_text = ""
            for i, u in enumerate(units):
                clean = u.strip().replace('*(Same as Vertical I)*', '').strip()
                if clean and clean != '\u2014' and clean != '-':
                    units_text += f"\n  Unit {i+1}: {clean}"

            chunk_text = (
                f"Subject: {title} ({code})\n"
                f"Curriculum Section: {section_title}\n"
                f"Topics covered:{units_text if units_text else ' Practical/Lab exercises.'}"
            )

            chunks.append({
                "code": code,
                "title": title,
                "section": section_title,
                "text": chunk_text,
            })

    return chunks


async def embed_and_store(chunks: list[dict]):
    """Embed with local sentence-transformers and store in pgvector."""
    print(f"Loading model: {MODEL_NAME} (downloads ~420MB first time)...")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: Run: venv\\Scripts\\pip install sentence-transformers")
        return

    model = SentenceTransformer(MODEL_NAME)
    print(f"Model loaded. Embedding {len(chunks)} subjects...\n")

    pool = await get_pool()
    inserted = 0
    skipped = 0
    errors = 0

    for i, chunk in enumerate(chunks):
        filename = f"syllabus:{chunk['code']}"
        try:
            # Check if already indexed (idempotent)
            async with pool.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT id FROM documents WHERE filename = $1 LIMIT 1",
                    filename,
                )
            if exists:
                skipped += 1
                print(f"  [{i+1:3d}/{len(chunks)}] SKIP  {chunk['code']}")
                continue

            # Embed locally — no API, no rate limits
            vector = model.encode(chunk["text"]).tolist()
            vector_str = json.dumps(vector)

            # Insert into pgvector documents table
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO documents (filename, content, embedding) "
                    "VALUES ($1, $2, $3::extensions.vector)",
                    filename,
                    chunk["text"],
                    vector_str,
                )

            inserted += 1
            print(f"  [{i+1:3d}/{len(chunks)}] OK    {chunk['code']:12s} {chunk['title'][:48]}")

        except Exception as e:
            errors += 1
            print(f"  [{i+1:3d}/{len(chunks)}] ERROR {chunk['code']}: {e}")

    await pool.close()
    print()
    print("=" * 55)
    print(f"Syllabus Ingest Complete!")
    print(f"  Inserted : {inserted}")
    print(f"  Skipped  : {skipped} (already indexed)")
    print(f"  Errors   : {errors}")
    if inserted > 0:
        print("\nAcademic Agent now has full 8-semester syllabus in RAG!")


async def main():
    print()
    print("AI Mentor — Syllabus RAG Ingest (local embeddings)")
    print("=" * 55)

    chunks = parse_syllabus_into_chunks(SYLLABUS_PATH)
    print(f"Parsed {len(chunks)} subjects from syllabus\n")

    if not chunks:
        print("ERROR: No chunks parsed. Check SYLLABUS_PATH.")
        return

    print("Preview (first 5):")
    for c in chunks[:5]:
        print(f"  {c['code']:12s} | {c['title'][:48]:48s} | {c['section'][:25]}")
    print(f"  ... and {max(0, len(chunks)-5)} more\n")

    await embed_and_store(chunks)


if __name__ == "__main__":
    asyncio.run(main())
