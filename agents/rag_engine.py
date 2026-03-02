import asyncio
import os
import logging
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from db import db, get_pool, close_pool
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def ingest_pdf(filepath: str, subject_code: str, student_id: int = None):
    logger.info(f"Loading {filepath}...")
    try:
        loader = PyMuPDFLoader(filepath)
        docs = loader.load()
    except Exception as e:
        logger.error(f"Failed to load PDF: {e}")
        return

    logger.info(f"Splitting {len(docs)} pages...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_documents(docs)
    logger.info(f"Generated {len(chunks)} chunks.")

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001", 
        google_api_key=settings.google_api_key
    )

    filename = os.path.basename(filepath)
    success_count = 0

    # Ensure DB pool is initialized
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
                    filename=filename,
                    content=texts[j],
                    embedding=vector,
                    subject_code=subject_code,
                    student_db_id=student_id,
                    doc_type="study_material",
                )
                success_count += 1
        except Exception as e:
            logger.error(f"Error embedding batch {i // batch_size + 1}: {e}")

    await close_pool()
    logger.info(f"Successfully ingested {success_count} chunks into Supabase pgvector.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python rag_engine.py <path_to_pdf> <subject_code> [student_db_id]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    subject = sys.argv[2]
    student = int(sys.argv[3]) if len(sys.argv) > 3 else None

    asyncio.run(ingest_pdf(pdf_path, subject, student))
