"""
Auto Notes Generator — Phase 5 V7 Knowledge Engine
Converts lesson session logs into structured, well-formatted Markdown + HTML notes.
Uses Groq LLM to synthesize the lesson into export-ready academic notes.
"""
import json
import re
import logging
import markdown   # pip install markdown
from groq import AsyncGroq
from config import settings

logger = logging.getLogger(__name__)


async def generate_notes(
    subject_code: str,
    topic: str,
    lesson_steps: list[dict],
    qa_thread: list[dict] = None,
    student_name: str = "Student",
) -> dict:
    """
    Generate structured Markdown notes from a lesson session.

    Args:
        lesson_steps: list of { step_num, content, title? } (tutor's explanation steps)
        qa_thread:    list of { role: 'user'|'assistant', content } (Q&A conversation)
        student_name: for personalizing the header

    Returns:
        { title, markdown, html, word_count, created_at }
    """
    if not lesson_steps and not qa_thread:
        return {
            "title": f"{topic} — Notes",
            "markdown": f"# {topic}\n\nNo lesson content available to generate notes from.",
            "html": f"<h1>{topic}</h1><p>No lesson content available.</p>",
            "word_count": 0,
        }

    # Prepare lesson context for the LLM
    steps_text = ""
    for i, step in enumerate(lesson_steps[:15], 1):  # cap at 15 steps
        content = step.get("content") or step.get("explanation") or ""
        title = step.get("title") or f"Step {i}"
        if content:
            steps_text += f"\n### Step {i}: {title}\n{content[:1200]}\n"

    qa_text = ""
    if qa_thread:
        for msg in qa_thread[-20:]:  # last 20 messages
            role = "Student" if msg.get("role") == "user" else "Tutor"
            content = msg.get("content", "")[:400]
            if content:
                qa_text += f"\n**{role}:** {content}\n"

    prompt = f"""You are an expert academic note-taker. Convert this lesson into clean, structured study notes.

Subject: {subject_code}
Topic: {topic}

LESSON CONTENT:
{steps_text or "(No steps recorded)"}

Q&A DISCUSSION:
{qa_text or "(No Q&A recorded)"}

Generate comprehensive study notes in STRICT MARKDOWN format:

# {topic}
**Subject:** {subject_code} | **Note Type:** Lesson Notes

## 📌 Key Concepts
(3-6 most important concepts as bullet points)

## 🧠 Detailed Explanation
(The core concepts explained clearly with structure)

## 💡 Examples & Applications
(Concrete examples, analogies, or code snippets if applicable. Use code blocks for code.)

## 📐 Formulas / Key Points
(If applicable: equations, rules, algorithms, or definitions in bullet form)

## ❓ Common Exam Questions
(3-5 likely exam questions based on this topic)

## 🔁 Quick Revision Summary
(5-7 bullet points for last-minute revision)

Rules:
- Use proper markdown: ##, ###, **, `, \`\`\`code\`\`\`
- Be concise but complete — notes should be valuable for exam prep
- Do NOT use placeholder text like "(to be filled)"
- Include actual content from the lesson
"""

    try:
        groq = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert academic note-taker. Generate clean, well-structured markdown notes."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
        )
        notes_md = resp.choices[0].message.content.strip()

        # Convert to HTML
        try:
            notes_html = _markdown_to_html(notes_md, topic)
        except Exception:
            notes_html = f"<pre>{notes_md}</pre>"

        word_count = len(notes_md.split())
        title = f"{topic} — {subject_code} Notes"

        return {
            "title":      title,
            "markdown":   notes_md,
            "html":       notes_html,
            "word_count": word_count,
        }

    except Exception as e:
        logger.error(f"Notes generation error: {e}", exc_info=True)
        fallback_md = f"# {topic}\n**Subject:** {subject_code}\n\n*Notes generation failed: {e}*\n\n## Lesson Steps\n{steps_text or 'No content'}"
        return {
            "title":      f"{topic} — Notes",
            "markdown":   fallback_md,
            "html":       f"<h1>{topic}</h1><p>Generation failed.</p>",
            "word_count": len(fallback_md.split()),
        }


def _markdown_to_html(md_text: str, title: str) -> str:
    """Convert markdown to a styled HTML document."""
    try:
        import markdown as md_lib
        body = md_lib.markdown(
            md_text,
            extensions=["fenced_code", "tables", "nl2br"],
        )
    except Exception:
        # Minimal fallback: wrap in pre
        body = f"<pre>{md_text}</pre>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 24px; color: #1C1410; background: #FFFDF7; line-height: 1.7; }}
  h1 {{ color: #FF7A00; border-bottom: 2px solid #FF7A00; padding-bottom: 8px; }}
  h2 {{ color: #2F4858; margin-top: 28px; }}
  h3 {{ color: #374151; }}
  code {{ background: #F3F4F6; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
  pre {{ background: #1F2937; color: #F9FAFB; padding: 16px; border-radius: 8px; overflow-x: auto; }}
  pre code {{ background: none; color: inherit; }}
  blockquote {{ border-left: 3px solid #FF7A00; margin: 0; padding: 8px 16px; background: rgba(255,122,0,0.05); }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #E8E0D5; padding: 8px 12px; }}
  th {{ background: #F4F1EC; }}
  ul, ol {{ padding-left: 24px; }}
  li {{ margin: 4px 0; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


async def save_notes(
    pool, student_db_id: int, subject_code: str, topic: str,
    notes: dict, session_id: str = None,
) -> int:
    """Save generated notes to the database. Returns inserted row ID."""
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            """
            INSERT INTO student_notes
                (student_db_id, subject_code, topic, title, markdown_content,
                 html_content, session_id, word_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            student_db_id,
            subject_code,
            topic,
            notes.get("title", f"{topic} Notes"),
            notes.get("markdown", ""),
            notes.get("html", ""),
            session_id,
            notes.get("word_count", 0),
        )
    return row_id


async def list_notes(pool, student_db_id: int, limit: int = 20) -> list[dict]:
    """List saved notes for a student (summary only, no full content)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, subject_code, topic, title, word_count, session_id, created_at
            FROM student_notes
            WHERE student_db_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            student_db_id, limit,
        )
    return [dict(r) for r in rows]


async def get_note(pool, note_id: int, student_db_id: int) -> dict | None:
    """Fetch a single note with full markdown + html content."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, subject_code, topic, title, markdown_content, html_content,
                   word_count, session_id, created_at
            FROM student_notes
            WHERE id = $1 AND student_db_id = $2
            """,
            note_id, student_db_id,
        )
    return dict(row) if row else None
