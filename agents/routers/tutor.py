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

@router.get("/student/{student_id}/tutor/options")
async def get_tutor_options(student_id: str):
    """
    Tutor UI options from DB only: subjects and topics per subject.
    Subjects from student profile (subject_profiles); topics from subject_syllabus.
    No hardcoded data.
    """
    options = await db.get_tutor_options(student_id)
    return options


@router.post("/quiz/generate")
async def generate_quiz_endpoint(body: dict):
    """
    Generate AI-powered MCQ quiz questions for a given subject/topic/bloom level.
    Body: { subject, topic, bloom_level, student_id? }

    If student_id is provided, auto-resolves the real Bloom level for the subject
    from the student's ERP profile — prevents frontend from bypassing Bloom gating.
    Returns: { subject, topic, bloom_level, bloom_name, questions: [...], total }
    """
    from learning import generate_quiz
    subject = body.get("subject", "Computer Science")
    topic = body.get("topic", "Introduction")
    student_id = body.get("student_id")
    requested_bloom = int(body.get("bloom_level", 2))

    # Auto-resolve real Bloom level from student profile if student_id is provided
    bloom_level = requested_bloom
    if student_id:
        try:
            profile = await get_student_profile(student_id)
            subjects = profile.get("subjects", [])
            subject_lower = subject.lower()
            # Find the best-matching subject in the student's enrolled subjects
            matched = next(
                (s for s in subjects if subject_lower in s.get("name", "").lower()
                 or s.get("code", "").lower() == subject_lower),
                None
            )
            if matched:
                real_bloom = matched.get("bloomLevel", requested_bloom)
                # Allow frontend to request lower but never higher than student's level
                bloom_level = min(requested_bloom, real_bloom)
                logger.info(
                    f"Bloom gating: requested={requested_bloom}, "
                    f"profile={real_bloom}, resolved={bloom_level} for {subject}"
                )
        except Exception as e:
            logger.warning(f"Bloom auto-resolution failed for {student_id}: {e}. Using requested level.")

    # Clamp to valid range
    bloom_level = max(1, min(6, bloom_level))

    try:
        result = generate_quiz(subject, topic, bloom_level)
        result["bloom_was_capped"] = bloom_level < requested_bloom  # let frontend know if level was lowered
        return result
    except Exception as e:
        logger.error(f"Quiz generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Quiz generation failed. Please try again.")


@router.post("/student/{student_id}/tutor/teach")
async def tutor_teach(student_id: str, body: dict, request: Request):
    """
    AI Visual Tutor — streams a step-by-step lesson for a topic.

    Body: { subject_code, topic, mode: "visual"|"explain"|"quiz", session_id?: string }

    Returns SSE stream of events:
      - event: narration   → { text }       (voice-ready explanation chunk)
      - event: diagram     → { mermaid }    (Mermaid diagram code for whiteboard)
      - event: step        → { step, title } (new teaching step)
      - event: done        → {}
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    subject_code = body.get("subject_code", "")
    topic = body.get("topic", "")
    mode = body.get("mode", "visual")
    session_id = body.get("session_id") or str(uuid.uuid4())

    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    if session_id not in tutor_sessions:
        tutor_sessions[session_id] = {"turns": [], "lesson_summary": None}

    ctx = await build_tutor_context(student_id, subject_code, topic)
    if not ctx:
        raise HTTPException(status_code=404, detail="Student not found")

    profile = ctx["profile"]
    bloom_level = ctx["bloom_level"]
    style = ctx["style"]
    subject_name = ctx["subject_name"]
    syllabus_text = ctx["syllabus_text"]
    mastery_weak = ctx["mastery_weak"]
    mastery_strong = ctx["mastery_strong"]
    this_topic_row = ctx["this_topic_row"]
    att_overall = ctx["att_overall"]
    arrear_count = ctx["arrear_count"]
    subject_att = ctx["subject_att"]
    subject_status = ctx["subject_status"]
    total_questions = ctx["total_questions"]
    total_quizzes = ctx["total_quizzes"]
    accuracy = ctx["accuracy"]
    peak_hour = ctx["peak_hour"]

    mastery_block = ""
    if mastery_weak:
        mastery_block += f"Weak topics (this subject): {mastery_weak}\n"
    if mastery_strong:
        mastery_block += f"Strong topics: {mastery_strong}\n"
    if this_topic_row:
        bl = this_topic_row.get("bloom_level", bloom_level)
        ach = this_topic_row.get("achieved", False)
        avg = this_topic_row.get("avg_score")
        mastery_block += f"For THIS topic: Bloom {bl}, achieved={ach}" + (f", avg_score={avg}" if avg is not None else "") + ".\n"

    att_block = ""
    if att_overall is not None:
        att_block += f"Overall attendance: {att_overall}%. "
    if subject_att is not None:
        att_block += f"Subject attendance: {subject_att}%. "
    if arrear_count:
        att_block += f"Arrears: {arrear_count}. "
    if subject_status and subject_status != "safe":
        att_block += f"Subject status: {subject_status} (pace and encourage accordingly)."

    dna_block = f"Learning DNA: preferred_style={style}"
    if total_questions or total_quizzes:
        dna_block += f"; total_questions={total_questions}, total_quizzes={total_quizzes}"
    if accuracy is not None:
        dna_block += f"; accuracy={accuracy}%"
    if peak_hour is not None:
        dna_block += f"; peak_hour={peak_hour}"

    system_prompt = f"""You are an expert AI Tutor teaching an engineering student. You know this student's full context; never give a generic lesson. Adapt every step to their Bloom level and mastery. If they have weak topics in this subject, acknowledge and build from there. Vary your tone and examples; do not repeat the same phrasing. Be friendly but precise; use their name occasionally; ask one short check-in per lesson.

STUDENT CONTEXT:
- Name: {profile.get('name', 'Student')}
- Department: {profile.get('department', 'CSBS')} · Semester: {profile.get('semester', 7)}
- Subject: {subject_name}
- Topic to teach: {topic}
- Bloom's level: {bloom_level}/6
- Learning style: {style}
- CGPA: {profile.get('currentCGPA', '—')}
{f'- Mastery: {mastery_block}' if mastery_block else ''}
{f'- {att_block}' if att_block else ''}
- {dna_block}

SYLLABUS CONTEXT:
{syllabus_text}

TEACHING RULES:
1. Start with a personalized greeting: e.g. "Hi [Name], we're going to cover [topic]. You're at Bloom level {bloom_level} for this; I'll keep that in mind." Then teach.
2. Teach "{topic}" in 4-6 clear STEPS. Each step builds on the previous.
3. For EVERY step, produce TWO sections:
   a. [NARRATION] — A 2-4 sentence spoken explanation. Use analogies and real-world examples.
      Match Bloom level. Be conversational like a real teacher.
      For math/formula topics, include LaTeX wrapped in $$...$$ inline. Example: The loss function is $$J = -\\frac{{1}}{{m}} \\sum y \\log(\\hat{{y}})$$
   b. [DIAGRAM] — A valid Mermaid.js diagram for this step's concept.
      Prefer diagrams that look like real teaching aids: flowcharts for processes, sequence diagrams for protocols, state diagrams for state machines. Use clear, short labels (2-4 words per node). ONLY use: flowchart TD, sequenceDiagram, stateDiagram-v2, classDiagram.
      Keep diagrams SIMPLE — max 8 nodes. No inline styles or fill colors in node labels.
      Valid example: flowchart TD\\n    A[Start] --> B[Process] --> C[End]
   c. [CODE] (ONLY for CS/algorithm topics): A short code walkthrough block:
      [CODE]
      ```python
      # code here
      ```
      HIGHLIGHT: 2,4 (comma-separated 1-based line numbers to emphasize)
      EXPLAIN: Brief note on what the highlighted lines do
4. After STEP 2 and STEP 4, add a CHECKPOINT block to test understanding:
   [CHECKPOINT]
   Question: [Specific question about the concept just taught]
   Type: mcq
   Options: A) [option1] B) [option2] C) [option3] D) [option4]
   Correct: B
   Explanation: [Why B is correct, 1-2 sentences]
5. End with a brief summary and suggest a follow-up quiz.
6. Adapt depth to Bloom level {bloom_level}: {'basics and recall' if bloom_level <= 2 else 'application and analysis' if bloom_level <= 4 else 'evaluation and creation'}.

FORMAT YOUR RESPONSE EXACTLY LIKE THIS (repeat for each step):

[STEP 1: Title of Step]
[NARRATION]
Your spoken explanation here...

[DIAGRAM]
```mermaid
flowchart TD
    A["Concept"] --> B["Detail"]
    B --> C["Result"]
```

[STEP 2: Title of Next Step]
[NARRATION]
...
[DIAGRAM]
...

[CHECKPOINT]
Question: What is the key difference between X and Y?
Type: mcq
Options: A) First answer B) Second answer C) Third answer D) Fourth answer
Correct: A
Explanation: Because X does Z while Y does W.

[STEP 3: ...]
...and so on.

IMPORTANT: Every [DIAGRAM] MUST contain valid Mermaid syntax inside a ```mermaid code fence.
Do NOT add fill colors, style clauses, or any CSS inside the diagram."""

    async def stream_lesson():
        try:
            yield f"event: session_id\ndata: {json.dumps({'session_id': session_id})}\n\n"
            full_text = None

            # ── Try NVIDIA NIM first, fall back to Groq ───────────────────────
            full_text = None
            if settings.nvidia_api_key:
                try:
                    from langchain_openai import ChatOpenAI
                    llm_nvidia = ChatOpenAI(
                        api_key=settings.nvidia_api_key,
                        base_url=settings.nvidia_base_url,
                        model=settings.nvidia_model,
                        temperature=0.5,
                        max_tokens=4000,
                    )
                    result = await llm_nvidia.ainvoke([
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=f"Teach me: {topic}"),
                    ])
                    full_text = result.content or ""
                    logger.info(f"NVIDIA NIM lesson generated for topic: {topic}")
                except Exception as ne:
                    logger.warning(f"NVIDIA NIM call failed ({ne}), falling back to Groq")
                    full_text = None

            # ── Groq fallback ─────────────────────────────────────────────────
            if not full_text:
                from langchain_groq import ChatGroq
                llm = ChatGroq(
                    api_key=settings.groq_api_key,
                    model=settings.groq_model,
                    temperature=0.5,
                    max_tokens=4000,
                )
                result = await llm.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"Teach me: {topic}"),
                ])
                full_text = result.content or ""


            # ── Parse structured response into step events ──────────────
            import re
            from teacher import parse_checkpoints_from_lesson

            step_pattern      = re.compile(r'\[STEP\s+(\d+):\s*([^\]]+)\]', re.IGNORECASE)
            narration_pattern = re.compile(r'\[NARRATION\]\s*\n(.*?)(?=\[DIAGRAM\]|\[CODE\]|\[STEP|\[CHECKPOINT\]|\Z)', re.DOTALL | re.IGNORECASE)
            diagram_pattern   = re.compile(r'```mermaid\s*\n(.*?)```', re.DOTALL)
            code_block_pattern = re.compile(
                r'\[CODE\]\s*\n```(\w+)?\s*\n(.*?)```\s*\nHIGHLIGHT:\s*([^\n]*)\nEXPLAIN:\s*([^\n\[]*)',
                re.DOTALL | re.IGNORECASE,
            )
            latex_pattern = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)

            steps      = list(step_pattern.finditer(full_text))
            narrations = list(narration_pattern.finditer(full_text))
            diagrams   = list(diagram_pattern.finditer(full_text))
            code_blocks = list(code_block_pattern.finditer(full_text))
            checkpoints = parse_checkpoints_from_lesson(full_text)
            # Map checkpoints by after_step for O(1) lookup
            cp_by_step = {cp['after_step']: cp for cp in checkpoints}

            if not steps:
                yield f"event: step\ndata: {json.dumps({'step': 1, 'title': topic})}\n\n"
                yield f"event: narration\ndata: {json.dumps({'text': full_text[:2000]})}\n\n"
                yield f"event: done\ndata: {json.dumps({})}\n\n"
                return

            for i, step_match in enumerate(steps):
                step_num   = int(step_match.group(1))
                step_title = step_match.group(2).strip()

                yield f"event: step\ndata: {json.dumps({'step': step_num, 'title': step_title})}\n\n"

                # Narration — extract LaTeX equations and emit as separate events
                if i < len(narrations):
                    narr_text = narrations[i].group(1).strip()
                    # Detect and emit LaTeX equations embedded in narration
                    latex_matches = latex_pattern.findall(narr_text)
                    for latex in latex_matches:
                        yield f"event: equation\ndata: {json.dumps({'latex': latex.strip(), 'display': 'inline', 'step': step_num})}\n\n"

                    sentences = re.split(r'(?<=[.!?])\s+', narr_text)
                    for sent in sentences:
                        sent = sent.strip()
                        if sent:
                            yield f"event: narration\ndata: {json.dumps({'text': sent})}\n\n"
                            await asyncio.sleep(0.05)

                # Diagram for this step
                if i < len(diagrams):
                    mermaid_code = diagrams[i].group(1).strip()
                    yield f"event: diagram\ndata: {json.dumps({'mermaid': mermaid_code, 'title': step_title})}\n\n"

                # Code walkthrough block (if present for this step)
                if i < len(code_blocks):
                    cb = code_blocks[i]
                    lang        = (cb.group(1) or 'python').strip()
                    code        = cb.group(2).strip()
                    highlights  = [int(x.strip()) for x in cb.group(3).split(',') if x.strip().isdigit()]
                    explanation = cb.group(4).strip()
                    yield f"event: code_block\ndata: {json.dumps({'language': lang, 'code': code, 'highlight_lines': highlights, 'explanation': explanation, 'step': step_num})}\n\n"

                # ── Checkpoint after this step (if defined) ──────────────
                if step_num in cp_by_step:
                    cp = cp_by_step[step_num]
                    yield f"event: checkpoint\ndata: {json.dumps({**cp, 'step_before': step_num, 'step_after': step_num + 1})}\n\n"

                await asyncio.sleep(0.1)

            if session_id in tutor_sessions:
                tutor_sessions[session_id]["lesson_summary"] = f"Lesson: {topic}, steps 1–{len(steps)}"
                tutor_sessions[session_id]["last_step"] = len(steps)

            # ── Fire-and-forget: record lesson completion for spaced repetition
            asyncio.create_task(
                db.record_lesson_completion(
                    student_id=student_id,
                    subject_code=subject_code,
                    topic=topic,
                    steps_completed=len(steps),
                    bloom_level=bloom_level,
                )
            )

            yield f"event: done\ndata: {json.dumps({'total_steps': len(steps)})}\n\n"

        except Exception as e:
            logger.error(f"Tutor teach error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream_lesson(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/student/{student_id}/tutor/session/clear")
async def tutor_session_clear(student_id: str, body: dict):
    """Clear a tutor session (e.g. for 'New conversation'). Body: { session_id }"""
    sid = body.get("session_id")
    if sid and sid in tutor_sessions:
        del tutor_sessions[sid]
    return {"ok": True}


@router.post("/student/{student_id}/tutor/ask")
async def tutor_ask(student_id: str, body: dict):
    """
    AI Tutor follow-up Q&A. Student asks a question about the current topic;
    returns a concise, didactic answer (optionally with a Mermaid diagram).
    Body: { subject_code, topic, question, history?: [{role, content}], session_id?: string }
    """
    topic = (body.get("topic") or "").strip()
    question = (body.get("question") or "").strip()
    subject_code = body.get("subject_code", "")
    client_history = body.get("history") or []
    session_id = body.get("session_id")

    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    if session_id and session_id not in tutor_sessions:
        tutor_sessions[session_id] = {"turns": [], "lesson_summary": None}

    session_turns = []
    if session_id and session_id in tutor_sessions:
        session_turns = tutor_sessions[session_id].get("turns", [])[-10:]
    history = session_turns if session_turns else client_history[-6:]

    ctx = await build_tutor_context(student_id, subject_code, topic)
    if not ctx:
        raise HTTPException(status_code=404, detail="Student not found")

    profile = ctx["profile"]
    bloom = ctx["bloom_level"]
    style = ctx["style"]
    subject_name = ctx["subject_name"]
    syllabus_text = ctx["syllabus_text"]
    mastery_weak = ctx["mastery_weak"]
    mastery_strong = ctx["mastery_strong"]
    this_topic_row = ctx["this_topic_row"]

    mastery_block = ""
    if mastery_weak:
        mastery_block += f"Weak topics: {mastery_weak}. "
    if mastery_strong:
        mastery_block += f"Strong topics: {mastery_strong}. "
    if this_topic_row:
        bl = this_topic_row.get("bloom_level", bloom)
        ach = this_topic_row.get("achieved", False)
        mastery_block += f"For this topic: Bloom {bl}, achieved={ach}. "

    lesson_summary = ""
    if session_id and session_id in tutor_sessions:
        lesson_summary = (tutor_sessions[session_id].get("lesson_summary") or "").strip()
    session_context = f"\nRecent lesson: {lesson_summary}." if lesson_summary else ""

    # V5: Fetch RAG context for this question (non-blocking; enriches LLM answer)
    rag_context = ""
    try:
        from tutor_graph import get_tutor_graph
        graph = get_tutor_graph()
        db_id = (ctx["profile"] or {}).get("db_id") if ctx else None
        rag_context = await graph.enrich_qa(
            question=question,
            subject_code=subject_code or None,
            student_db_id=db_id,
        )
    except Exception as rag_err:
        logger.warning(f"RAG enrichment skipped: {rag_err}")

    rag_section = (
        f"\n\nRELEVANT STUDY MATERIAL (use to ground your answer):\n{rag_context[:1500]}"
        if rag_context else ""
    )

    system_prompt = f"""You are the AI Tutor for an engineering student. They are learning "{topic}" in {subject_name}. Continue the conversation naturally. Reference what you already taught or what the student asked. Vary your explanations; do not repeat the same sentences. If they ask to explain again, use different examples or a different angle. Sometimes offer a one-sentence recap question; when the student answers, briefly confirm or correct.{session_context}

STUDENT CONTEXT:
- Name: {profile.get('name', 'Student')}
- Bloom level: {bloom}/6. Learning style: {style}
{f'- Mastery: {mastery_block}' if mastery_block else ''}

SYLLABUS (current subject units):
{syllabus_text}
{rag_section}
Answer their follow-up question in 2–4 short paragraphs. Be conversational and didactic.
- Match Bloom level {bloom}/6 (depth of explanation).
- Prefer {style} style.
- If the question asks for an example or diagram, you MAY include a Mermaid diagram in a ```mermaid code block at the end.
- Keep the answer focused and under 250 words."""

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-6:]:
        messages.append({"role": h.get("role", "user"), "content": (h.get("content") or "")[:2000]})
    messages.append({"role": "user", "content": question})

    from langchain_core.messages import HumanMessage, SystemMessage
    lc_messages = [SystemMessage(content=system_prompt)]
    for h in history[-6:]:
        role, content = h.get("role", "user"), (h.get("content") or "")[:2000]
        lc_messages.append(HumanMessage(content=content) if role == "user" else SystemMessage(content=content))
    lc_messages.append(HumanMessage(content=question))

    try:
        llm = None
        # Try NVIDIA NIM first, fall back to Groq
        if settings.nvidia_api_key:
            try:
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(
                    api_key=settings.nvidia_api_key,
                    base_url=settings.nvidia_base_url,
                    model=settings.nvidia_model,
                    temperature=0.4,
                    max_tokens=800,
                )
            except Exception as ne:
                logger.warning(f"NVIDIA NIM init failed, using Groq: {ne}")
                llm = None
        if llm is None:
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                temperature=0.4,
                max_tokens=800,
            )

        result = await llm.ainvoke(lc_messages)
        text = (result.content or "").strip()
        mermaid_block = None
        if "```mermaid" in text:
            import re
            m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
            if m:
                mermaid_block = m.group(1).strip()
        if session_id and session_id in tutor_sessions:
            tutor_sessions[session_id]["turns"].append({"role": "user", "content": question})
            tutor_sessions[session_id]["turns"].append({"role": "assistant", "content": text})

        # ── Confusion detection (fire-and-forget) ────────────────────────
        if session_id and session_id in tutor_sessions:
            from teacher import detect_confusion
            session_turns = tutor_sessions[session_id].get("turns", [])
            if detect_confusion(session_turns, topic, threshold=3):
                asyncio.create_task(
                    db.flag_confusion_topic(student_id, topic, subject_code)
                )

        return {"answer": text, "mermaid": mermaid_block}
    except Exception as invoke_err:
        err_msg = (getattr(invoke_err, "message", None) or str(invoke_err)).lower()
        if "accessdenied" in err_msg or "authentication failed" in err_msg or "api key" in err_msg:
            logger.warning(f"LLM auth failed ({invoke_err}), falling back to Groq")
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                temperature=0.4,
                max_tokens=800,
            )
            result = await llm.ainvoke(lc_messages)
        else:
            raise

        text = (result.content or "").strip()
        mermaid_block = None
        if "```mermaid" in text:
            import re
            m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
            if m:
                mermaid_block = m.group(1).strip()
        if session_id and session_id in tutor_sessions:
            tutor_sessions[session_id]["turns"].append({"role": "user", "content": question})
            tutor_sessions[session_id]["turns"].append({"role": "assistant", "content": text})
        return {"answer": text, "mermaid": mermaid_block}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tutor ask error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/student/{student_id}/tutor/lesson-plan")
async def get_lesson_plan(student_id: str, subject_code: str = "", topic: str = ""):
    """
    V5: Pre-generate a structured lesson plan using TutorGraph multi-agent orchestration.
    - PlannerAgent: decomposes topic with Bloom + teaching style
    - KnowledgeRetrievalAgent: injects syllabus + RAG context
    - DifficultyController: adjusts Bloom from SM-2 history + weak areas
    Returns enriched plan with rag_available, bloom_action, and step-level metadata.
    """
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    from tutor_graph import get_tutor_graph
    from memory import MemoryAgent

    ctx = await build_tutor_context(student_id, subject_code, topic)
    bloom_level  = ctx["bloom_level"] if ctx else 2
    style        = ctx["style"] if ctx else "visual + example-based"
    db_id        = (ctx["profile"] or {}).get("db_id") if ctx else None
    dna_weak     = ctx.get("dna_weak") or []

    # Pull SM-2 weak areas for this subject (non-blocking)
    sm2_weak: list[str] = []
    try:
        mem = MemoryAgent()
        sm2_data = await mem.get_weak_areas(
            student["db_id"],
            subject_code=subject_code,
            top_n=8,
        )
        sm2_weak = [w.get("topic", w.get("concept", "")) for w in (sm2_data or [])]
    except Exception as e:
        logger.warning(f"SM-2 weak areas fetch failed: {e}")
        sm2_weak = dna_weak

    mastered_concepts = (ctx.get("dna_strong") or [])[:6]

    # Run multi-agent lesson planning (RAG + Planner + DifficultyController)
    graph = get_tutor_graph()
    plan = await graph.plan_lesson(
        subject_code=subject_code,
        topic=topic,
        student_db_id=db_id,
        teaching_style=style,
        current_bloom=bloom_level,
        weak_areas=sm2_weak,
        mastered_concepts=mastered_concepts,
    )

    subject_name = ctx["subject_name"] if ctx else subject_code
    total_mins = sum(s.get("estimated_minutes", 3) for s in plan.get("steps", []))

    return {
        "student_id":      student_id,
        "subject_code":    subject_code,
        "subject_name":    subject_name,
        "topic":           topic,
        "bloom_level":     plan.get("bloom_level", bloom_level),
        "bloom_action":    plan.get("bloom_action", "maintain"),
        "steps":           plan.get("steps", []),
        "total_steps":     len(plan.get("steps", [])),
        "estimated_total_minutes": total_mins,
        "checkpoints":     plan.get("checkpoints", sum(1 for s in plan.get("steps", []) if s.get("checkpoint_after"))),
        "teaching_strategy": plan.get("teaching_strategy", style),
        "rag_available":   plan.get("rag_available", False),
        "chunk_count":     plan.get("chunk_count", 0),
    }


@router.post("/student/{student_id}/tutor/checkpoint")
async def evaluate_checkpoint(student_id: str, body: dict):
    """
    Evaluate a student's checkpoint answer (free-text or MCQ).
    MCQ answers are evaluated client-side; this endpoint handles short-answer evaluation.
    Also persists the result to bloom_progress + Learning DNA.

    Body: { session_id, question, student_answer, correct_answer, subject_code, topic,
            question_type: 'mcq'|'short', correct_index?: int, selected_index?: int }
    Returns: { correct, score, feedback, misconceptions, unlock_next }
    """
    from teacher import evaluate_checkpoint_answer

    question      = (body.get("question") or "").strip()
    student_ans   = (body.get("student_answer") or "").strip()
    correct_ctx   = (body.get("correct_answer") or "").strip()
    subject_code  = body.get("subject_code", "")
    topic         = (body.get("topic") or "").strip()
    q_type        = body.get("question_type", "short")
    session_id    = body.get("session_id")

    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    ctx = await build_tutor_context(student_id, subject_code, topic)
    bloom_level = ctx["bloom_level"] if ctx else 2

    # MCQ: evaluate client-side index match
    if q_type == "mcq":
        correct_index  = int(body.get("correct_index", 0))
        selected_index = int(body.get("selected_index", -1))
        correct = selected_index == correct_index
        result = {
            "correct":        correct,
            "score":          10 if correct else 0,
            "feedback":       ("Correct! " + correct_ctx) if correct else ("Not quite. " + correct_ctx),
            "misconceptions": [],
            "unlock_next":    correct,
        }
    else:
        # Short answer: LLM-evaluated
        result = await evaluate_checkpoint_answer(
            question=question,
            student_answer=student_ans,
            correct_context=correct_ctx,
            bloom_level=bloom_level,
            topic=topic,
        )
        result["unlock_next"] = result["correct"]

    # Persist result to DB (fire-and-forget)
    asyncio.create_task(
        db.update_checkpoint_result(
            student_id=student_id,
            subject_code=subject_code,
            topic=topic,
            correct=result["correct"],
            bloom_level=bloom_level,
        )
    )

    return result


@router.post("/student/{student_id}/tutor/generate-quiz")
async def generate_exam_quiz(student_id: str, body: dict):
    """
    Generate MCQ questions for Exam Mode.
    Body: { subject, topic, bloom_level?, count? }
    Returns: { questions: [{ question, options: [str], correct_index: int }] }
    Uses existing lesson plan infrastructure + Groq to generate exam-style questions.
    """
    import json, re
    from groq import AsyncGroq

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    subject     = body.get("subject", "")
    topic       = (body.get("topic") or subject or "General").strip()
    bloom_level = int(body.get("bloom_level", 2))
    count       = min(int(body.get("count", 10)), 20)

    bloom_descriptors = {
        1: "recall and recognition (factual)",
        2: "understanding and explanation",
        3: "application of concepts",
        4: "analysis and comparison",
        5: "evaluation and synthesis",
        6: "creation and novel solutions",
    }
    bloom_desc = bloom_descriptors.get(bloom_level, "understanding")

    prompt = f"""Generate {count} multiple-choice exam questions on the topic "{topic}" (subject: {subject}).
Difficulty: Bloom's Level {bloom_level} ({bloom_desc}).
STRICT OUTPUT FORMAT (valid JSON array, no markdown, no extra text):
[
  {{
    "question": "...",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "correct_index": 0
  }}
]
Rules:
- Each question MUST have exactly 4 options.
- correct_index is 0-based (0=A, 1=B, 2=C, 3=D).
- Questions should test {bloom_desc}.
- No repeated questions.
- One clearly correct answer per question."""

    try:
        groq = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert exam question generator. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=3000,
        )
        raw = resp.choices[0].message.content.strip()
        # Extract JSON array from response
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            questions = json.loads(match.group())
        else:
            questions = json.loads(raw)

        # Validate and normalize
        validated = []
        for q in questions:
            if isinstance(q, dict) and q.get("question") and q.get("options") and "correct_index" in q:
                validated.append({
                    "question":      q["question"],
                    "options":       q["options"][:4],
                    "correct_index": int(q.get("correct_index", 0)),
                })
        return {"questions": validated[:count], "topic": topic, "subject": subject, "bloom_level": bloom_level}

    except Exception as e:
        logger.error(f"Quiz generation error: {e}", exc_info=True)
        # Fallback: return minimal placeholder questions
        return {
            "questions": [
                {
                    "question":      f"What is the key concept of {topic}?",
                    "options":       ["Option A", "Option B", "Option C", "Option D"],
                    "correct_index": 0,
                }
            ],
            "topic":       topic,
            "subject":     subject,
            "bloom_level": bloom_level,
            "error":       "Quiz generation failed, using fallback",
        }


@router.get("/student/{student_id}/tutor/due-topics")
async def get_due_topics(student_id: str):
    """
    Spaced Repetition — Returns topics due for review.
    Frontend shows these as a 'Review Due' banner on the Tutor page.
    Uses SM-2 inspired intervals based on bloom_level in bloom_progress.
    """
    due = await db.get_due_topics(student_id)
    return {
        "student_id": student_id,
        "due_count":  len(due),
        "topics":     due,
        "has_due":    len(due) > 0,
    }


@router.get("/student/{student_id}/tutor/session/{session_id}/state")
async def get_session_state(student_id: str, session_id: str):
    """
    Return the current tutor session state for resume functionality.
    Frontend can use this to restore lesson progress after page refresh.
    """
    if session_id not in tutor_sessions:
        return {
            "session_id":        session_id,
            "exists":            False,
            "last_step":         0,
            "checkpoints_passed": [],
            "lesson_summary":    None,
        }
    sess = tutor_sessions[session_id]
    return {
        "session_id":         session_id,
        "exists":             True,
        "last_step":          sess.get("last_step", 0),
        "checkpoints_passed": sess.get("checkpoints_passed", []),
        "lesson_summary":     sess.get("lesson_summary"),
        "turn_count":         len(sess.get("turns", [])),
    }


@router.get("/student/{student_id}/tutor/voice/settings")
async def get_voice_settings(student_id: str):
    """
    Return available voice personalities and TTS provider info.
    Frontend uses this to populate the voice selector UI.
    """
    from nova_sonic import VOICE_PERSONALITIES
    return {
        "student_id": student_id,
        "tts_provider": "browser-tts",
        "tts_model": None,
        "voices": [
            {
                "id": key,
                "label": cfg["description"],
            }
            for key, cfg in VOICE_PERSONALITIES.items()
        ],
        "default_voice": "professor",
        "sample_rate": 24000,
        "fallback_available": True,  # browser TTS is always available
    }


@router.post("/student/{student_id}/tutor/voice/speak")
async def tutor_voice_speak(student_id: str, body: dict):
    """
    Nova Sonic Text-to-Speech endpoint.
    Body: { text, voice?: "professor"|"coach"|"friend", max_chars?: int }
    Returns: streaming WAV audio (audio/wav) for browser Audio playback.
    Falls back to Amazon Polly if Nova Sonic is unavailable.
    Falls back to 204 No Content if neither is available (browser TTS used).
    """
    from nova_sonic import get_tts, VOICE_PERSONALITIES

    text = (body.get("text") or "").strip()
    voice = body.get("voice", "professor")
    max_chars = int(body.get("max_chars", 500))

    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    if voice not in VOICE_PERSONALITIES:
        voice = "professor"

    text = text[:max_chars]

    # Server-side TTS is stubbed (browser handles TTS via Web Speech API)
    from fastapi.responses import Response
    return Response(status_code=204)


@router.post("/student/{student_id}/tutor/voice/transcribe")
async def tutor_voice_transcribe(student_id: str, request: Request):
    """
    Speech-to-Text transcription endpoint.
    Accepts raw audio bytes (audio/webm or audio/wav) as request body.
    Returns: { transcript, confidence?, language }
    Falls back to empty transcript if AWS creds are not set (browser STT handles it).
    """
    from nova_sonic import get_stt
    # Server-side STT is stubbed (browser handles STT via Web Speech API)
    return {"transcript": "", "language": "en-US", "provider": "browser-stt"}


@router.post("/student/{student_id}/tutor/checkpoint/record")
async def record_tutor_checkpoint(student_id: str, body: dict):
    """
    Record a checkpoint attempt and update SM-2 memory.
    Body: {
      subject_code, topic, question, question_type, student_answer,
      correct_answer, is_correct, score, feedback?, response_time_ms?,
      bloom_level?, after_step?, session_id?
    }
    Returns: { checkpoint_id, sm2_update: { interval_days, next_review_at } }
    """
    from memory import get_memory_agent

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    memo = get_memory_agent()
    subject_code = body.get("subject_code", "")
    topic = body.get("topic", "")
    is_correct = bool(body.get("is_correct", False))
    score = float(body.get("score", 1.0 if is_correct else 0.0))

    checkpoint_id = await memo.record_checkpoint(
        student_db_id=student["db_id"],
        subject_code=subject_code,
        topic=topic,
        question=body.get("question", ""),
        question_type=body.get("question_type", "mcq"),
        student_answer=body.get("student_answer", ""),
        correct_answer=body.get("correct_answer", ""),
        is_correct=is_correct,
        score=score,
        feedback=body.get("feedback"),
        response_time_ms=body.get("response_time_ms"),
        bloom_level=int(body.get("bloom_level", 2)),
        after_step=body.get("after_step"),
        session_id=body.get("session_id"),
    )

    # Fetch updated SM-2 state to return to frontend
    memory_rows = await memo.get_memory(student["db_id"], subject_code, topic)
    updated = next((r for r in memory_rows if r["concept"] == topic), {})

    # Update Learning DNA if lesson is complete
    if is_correct:
        await memo.update_learning_dna_from_lesson(
            student_id,
            strong_topics_append=[{"topic": topic, "subject": subject_code}],
            questions_delta=1, correct_delta=1,
        )
    else:
        await memo.update_learning_dna_from_lesson(
            student_id,
            weak_topics_append=[{"topic": topic, "subject": subject_code}],
            questions_delta=1, correct_delta=0,
        )

    return {
        "checkpoint_id": checkpoint_id,
        "is_correct": is_correct,
        "score": score,
        "sm2_update": {
            "interval_days":  updated.get("interval_days", 1),
            "next_review_at": str(updated.get("next_review_at", "")),
            "ease_factor":    round(float(updated.get("ease_factor", 2.5)), 3),
            "repetitions":    updated.get("repetitions", 0),
        },
        "xp_update": None,  # populated below
    }


@router.get("/student/{student_id}/tutor/due-topics/smart")
async def get_smart_due_topics(student_id: str, horizon_hours: int = 24, limit: int = 10):
    """
    SM-2 aware due topics — returns concepts due for review.
    horizon_hours: how many hours ahead to look (default 24h)
    """
    from memory import get_memory_agent

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    memo = get_memory_agent()
    due = await memo.get_due_topics(student["db_id"], limit=limit, horizon_hours=horizon_hours)

    return {
        "student_id": student_id,
        "due_count": len(due),
        "horizon_hours": horizon_hours,
        "due_topics": [
            {
                "subject_code":   r["subject_code"],
                "topic":          r["topic"],
                "concept":        r["concept"],
                "next_review_at": str(r["next_review_at"]),
                "interval_days":  r["interval_days"],
                "ease_factor":    round(float(r["ease_factor"]), 3),
                "times_wrong":    r["times_wrong"],
                "avg_score":      round(float(r["avg_score"] or 0), 3),
                "urgency":        "overdue" if r["next_review_at"].replace(tzinfo=None) < datetime.utcnow() else "due_soon",
            }
            for r in due
        ],
    }


@router.get("/student/{student_id}/tutor/weak-areas")
async def get_weak_areas(student_id: str, subject_code: str = None, top_n: int = 10):
    """
    Return weak topic areas based on SM-2 difficulty_level, avg_score, confusion_count.
    """
    from memory import get_memory_agent

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    memo = get_memory_agent()
    weak = await memo.get_weak_areas(student["db_id"], subject_code=subject_code, top_n=top_n)

    return {
        "student_id": student_id,
        "weak_area_count": len(weak),
        "weak_areas": [
            {
                "subject_code":    r["subject_code"],
                "topic":           r["topic"],
                "concept":         r["concept"],
                "avg_score":       round(float(r["avg_score"] or 0), 3),
                "difficulty_level": round(float(r["difficulty_level"] or 0), 3),
                "times_wrong":     r["times_wrong"],
                "times_correct":   r["times_correct"],
                "confusion_count": r["confusion_count"],
                "last_studied":    str(r["last_studied"] or ""),
            }
            for r in weak
        ],
    }


@router.get("/student/{student_id}/tutor/progress")
async def get_tutor_progress(student_id: str, subject_code: str = None):
    """
    Progress dashboard summary: mastered/struggling concepts, checkpoint pass rate,
    accuracy by subject, SM-2 review queue size.
    Used by the /learn/progress frontend page.
    """
    from memory import get_memory_agent

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    memo = get_memory_agent()
    summary = await memo.get_progress_summary(student["db_id"], subject_code=subject_code)

    # Add learning DNA snapshot
    try:
        dna = await db.get_learning_dna(student_id)
        summary["learning_dna"] = {
            "preferred_style":  dna.get("preferred_style"),
            "total_quizzes":    dna.get("total_quizzes", 0),
            "total_questions":  dna.get("total_questions", 0),
            "correct_answers":  dna.get("correct_answers", 0),
            "overall_accuracy": round(
                (int(dna.get("correct_answers", 0)) /
                 max(int(dna.get("total_questions", 0) or 1), 1)) * 100, 1
            ),
            "peak_hour":        dna.get("peak_hour"),
            "weak_topic_count": len(dna.get("weak_topics") or []),
            "strong_topic_count": len(dna.get("strong_topics") or []),
        }
    except Exception:
        summary["learning_dna"] = None

    summary["student_id"] = student_id
    return summary


@router.post("/student/{student_id}/tutor/rag-query")
async def tutor_rag_query(student_id: str, body: dict):
    """
    Semantic RAG search over the student's study materials and syllabus.
    Body: { query, subject_code?, top_k? }
    Returns: { chunks: [{ content, filename, subject_code, similarity }] }
    Used internally by the AI tutor (and exposed for testing / frontend preview).
    """
    from rag_engine import query_rag, get_syllabus_context

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    query = (body.get("query") or "").strip()
    subject_code = body.get("subject_code")
    top_k = int(body.get("top_k", 5))

    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    chunks = await query_rag(
        query,
        subject_code=subject_code,
        student_db_id=student["db_id"],
        top_k=top_k,
    )

    syllabus_ctx = ""
    if subject_code:
        syllabus_ctx = await get_syllabus_context(subject_code, query)

    return {
        "query":        query,
        "subject_code": subject_code,
        "chunk_count":  len(chunks),
        "chunks":       [
            {
                "content":      r["content"][:500],
                "filename":     r["filename"],
                "subject_code": r["subject_code"],
                "similarity":   round(float(r["similarity"]), 4),
            }
            for r in chunks
        ],
        "syllabus_context": syllabus_ctx[:1000] if syllabus_ctx else None,
    }


@router.post("/student/{student_id}/tutor/deep-evaluate")
async def tutor_deep_evaluate(student_id: str, body: dict):
    """
    V5 Deep checkpoint evaluation via EvaluatorAgent.
    More thorough than /tutor/checkpoint — identifies misconceptions,
    recommends next action (continue | slow_down | doubt_resolve | revisit_step),
    and reports Bloom level actually demonstrated.

    Body: {
      subject_code, topic, question, student_answer, correct_answer,
      question_type?, response_time_ms?, prev_score?, wrong_count?
    }
    Returns: {
      is_correct, score, feedback, misconception, recommendation,
      bloom_achievement, correct_explanation, bloom_action, bloom_level
    }
    """
    from tutor_graph import get_tutor_graph

    subject_code    = body.get("subject_code", "")
    topic           = (body.get("topic") or "").strip()
    question        = (body.get("question") or "").strip()
    student_answer  = (body.get("student_answer") or "").strip()
    correct_answer  = (body.get("correct_answer") or "").strip()
    question_type   = body.get("question_type", "mcq")
    response_time   = int(body.get("response_time_ms", 0))
    prev_score      = body.get("prev_score")
    wrong_count     = int(body.get("wrong_count", 0))

    if not question or not student_answer:
        raise HTTPException(status_code=400, detail="question and student_answer are required")

    graph = get_tutor_graph()
    result = await graph.evaluate_checkpoint(
        subject_code=subject_code,
        topic=topic,
        question=question,
        student_answer=student_answer,
        correct_answer=correct_answer,
        question_type=question_type,
        response_time_ms=response_time,
        prev_score=float(prev_score) if prev_score is not None else None,
        wrong_count=wrong_count,
    )
    return result


@router.post("/student/{student_id}/tutor/doubt-resolve")
async def tutor_doubt_resolve(student_id: str, body: dict):
    """
    V5 Doubt resolution via DoubtResolverAgent.
    Triggered when a student fails the same concept ≥2 times.
    Generates a FRESH alternative explanation (analogy | example | breakdown | socratic),
    rotates approach to avoid repeating the same teaching method,
    and optionally generates a Mermaid diagram for visual learners.

    Body: {
      subject_code, topic, concept, wrong_count?,
      last_wrong_answer?, misconception?, confusion_context?
    }
    Returns: {
      mode, explanation, mini_question, key_insight,
      diagram?, rag_context?
    }
    """
    from tutor_graph import get_tutor_graph

    subject_code       = body.get("subject_code", "")
    topic              = (body.get("topic") or "").strip()
    concept            = (body.get("concept") or topic).strip()
    wrong_count        = int(body.get("wrong_count", 2))
    last_wrong_answer  = body.get("last_wrong_answer")
    misconception      = body.get("misconception")
    confusion_context  = body.get("confusion_context", "")

    if not concept:
        raise HTTPException(status_code=400, detail="concept or topic is required")

    student = await db.get_student_by_college_id(student_id)
    db_id = student["db_id"] if student else None

    graph = get_tutor_graph()
    result = await graph.resolve_doubt(
        subject_code=subject_code,
        topic=topic,
        concept=concept,
        wrong_count=wrong_count,
        last_wrong_answer=last_wrong_answer,
        misconception=misconception,
        student_db_id=db_id,
    )
    return result


@router.get("/student/{student_id}/tutor/timeline")
async def get_lesson_timeline(student_id: str, limit: int = 20, offset: int = 0):
    """
    Progress Timeline — paginated lesson_completion history.
    Returns chronological list of lessons the student has studied.
    Combines lesson_completion records + SM-2 concept events for a full picture.
    """
    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    db_id = student["db_id"]

    try:
        pool = await db.get_pool() if hasattr(db, "get_pool") else None

        # Try lesson_completion table first
        try:
            from db import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT topic, subject_code, steps_completed, bloom_level,
                           steps_total, teaching_style, completed_at
                    FROM lesson_completion
                    WHERE student_db_id = $1
                    ORDER BY completed_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    db_id, limit, offset,
                )
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM lesson_completion WHERE student_db_id = $1", db_id
                )
        except Exception:
            rows, total = [], 0

        # Fallback: read from student_learning_memory as proxy
        if not rows:
            try:
                from memory import get_memory_agent
                memo = get_memory_agent()
                mem_rows = await memo.get_memory(db_id)
                rows = []
                for r in mem_rows[:limit]:
                    rows.append({
                        "topic":           r.get("concept", ""),
                        "subject_code":    r.get("subject_code", ""),
                        "steps_completed": r.get("repetitions", 1),
                        "bloom_level":     r.get("bloom_level", 2),
                        "completed_at":    r.get("last_reviewed_at", ""),
                        "steps_total":     None,
                    })
                total = len(rows)
            except Exception:
                rows, total = [], 0

        return {
            "student_id": student_id,
            "total":      int(total or len(rows)),
            "limit":      limit,
            "offset":     offset,
            "events": [
                {
                    "topic":           dict(r).get("topic", ""),
                    "subject_code":    dict(r).get("subject_code", ""),
                    "steps_completed": dict(r).get("steps_completed", 0),
                    "steps_total":     dict(r).get("steps_total"),
                    "bloom_level":     dict(r).get("bloom_level", 2),
                    "completed_at":    str(dict(r).get("completed_at", "")),
                }
                for r in rows
            ],
        }
    except Exception as e:
        logger.error(f"Timeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/student/{student_id}/concept-graph")
async def build_concept_graph_endpoint(student_id: str, body: dict):
    """
    Build or regenerate a concept dependency graph for a subject.
    Body: { subject_code, topics?: [str], refresh?: bool }
    Returns: { nodes, edges, mermaid_code, study_order }
    """
    from concept_graph import build_concept_graph, save_concept_graph, get_cached_graph
    from db import get_pool
    from memory import get_memory_agent

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    subject_code = (body.get("subject_code") or "").strip()
    topics       = body.get("topics") or []
    refresh      = bool(body.get("refresh", False))

    if not subject_code:
        raise HTTPException(status_code=400, detail="'subject_code' is required")

    pool = await get_pool()

    # Return cached unless refresh=True
    if not refresh:
        cached = await get_cached_graph(pool, student["db_id"], subject_code)
        if cached:
            return {**cached, "from_cache": True}

    # If no topics provided, pull from syllabus
    if not topics:
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT topics FROM subject_syllabus WHERE subject_code=$1 ORDER BY unit_number",
                    subject_code,
                )
            for r in rows:
                topics.extend(r["topics"] or [])
        except Exception:
            pass

    if not topics:
        raise HTTPException(
            status_code=400,
            detail="No topics available. Provide topics in body or ensure syllabus is loaded."
        )

    # Build SM-2 mastery map for color overlay
    mastery_map = {}
    try:
        memo = get_memory_agent()
        mem_rows = await memo.get_memory(student["db_id"], subject_code)
        for r in mem_rows:
            concept = r.get("concept", "")
            reps    = r.get("repetitions", 0)
            ease    = r.get("ease_factor", 2.5)
            if reps >= 3 and ease >= 2.5:
                mastery_map[concept] = "mastered"
            elif reps >= 1:
                mastery_map[concept] = "learning"
    except Exception:
        pass

    graph = await build_concept_graph(subject_code, topics, mastery_map)

    # Cache to DB
    try:
        await save_concept_graph(pool, student["db_id"], subject_code, graph)
    except Exception as e:
        logger.warning(f"Graph save failed: {e}")

    return {**graph, "from_cache": False}


@router.get("/student/{student_id}/concept-graph/{subject_code}")
async def get_concept_graph(student_id: str, subject_code: str):
    """Fetch cached concept graph for a subject."""
    from concept_graph import get_cached_graph
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    pool = await get_pool()
    graph = await get_cached_graph(pool, student["db_id"], subject_code)

    if not graph:
        raise HTTPException(
            status_code=404,
            detail="No concept graph found. Build one via POST /concept-graph first."
        )

    return {**graph, "from_cache": True}


@router.post("/student/{student_id}/tutor/evaluate-adaptive")
async def evaluate_adaptive_checkpoint(student_id: str, body: dict):
    """
    Evaluate a checkpoint with behavioral hesitation data.
    Body: { session_id, question, answer, subject_code, topic,
            bloom_level?, hesitation_data?, current_bloom? }
    Returns: { score, emotion_state, directive, feedback, ... standard eval }
    """
    from adaptive_engine import classify_emotion_state, get_adaptive_directive, log_adaptive_directive
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    session_id      = body.get("session_id", "")
    question        = body.get("question", "")
    answer          = body.get("answer", "")
    subject_code    = body.get("subject_code", "")
    topic           = body.get("topic", "")
    bloom_level     = int(body.get("bloom_level", 2))
    current_bloom   = int(body.get("current_bloom", bloom_level))
    hesitation_data = body.get("hesitation_data") or {}

    if not question or not answer:
        raise HTTPException(status_code=400, detail="'question' and 'answer' are required")

    # Standard checkpoint evaluation via TutorGraph
    try:
        from tutor_graph import get_tutor_graph
        tg = get_tutor_graph()
        eval_result = await tg.evaluate_checkpoint(
            student_db_id=student["db_id"],
            session_id=session_id,
            question=question,
            answer=answer,
            subject_code=subject_code,
            topic=topic,
            bloom_level=bloom_level,
        )
        score = float(eval_result.get("score", 0.7))
    except Exception as e:
        logger.warning(f"TutorGraph eval error: {e}")
        # Simple keyword-based fallback
        score = 0.6 if len(answer.strip()) > 20 else 0.3
        eval_result = {"score": score, "feedback": "Evaluation partial"}

    # Classify emotion state from hesitation + score
    emotion_state = classify_emotion_state(score, hesitation_data)
    directive     = get_adaptive_directive(emotion_state, current_bloom)

    # Update checkpoint record with hesitation + emotion
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tutor_checkpoints
                SET hesitation_json = $1, emotion_state = $2
                WHERE session_id = $3
                  AND student_db_id = $4
                  AND question = $5
                """,
                json.dumps(hesitation_data),
                emotion_state,
                session_id,
                student["db_id"],
                question[:500],
            )
        # Log adaptive directive
        hs = int(hesitation_data.get("hesitation_score", 0))
        await log_adaptive_directive(pool, student["db_id"], session_id, emotion_state, directive, hs, score, current_bloom)
    except Exception as e:
        logger.warning(f"Hesitation save error: {e}")

    return {
        **eval_result,
        "emotion_state": emotion_state,
        "directive":     directive,
        "hesitation":    hesitation_data,
    }


@router.post("/student/{student_id}/tutor/session/diagrams")
async def save_session_diagram(student_id: str, body: dict):
    """Save a diagram event for visual memory (V2)."""
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    session_id   = (body.get("session_id") or "").strip()
    mermaid_code = (body.get("mermaid_code") or "").strip()
    if not mermaid_code:
        raise HTTPException(status_code=400, detail="'mermaid_code' is required")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tutor_session_diagrams
                    (student_db_id, session_id, subject_code, topic, step_num, diagram_title, mermaid_code)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, created_at
                """,
                student["db_id"],
                session_id,
                body.get("subject_code", ""),
                body.get("topic", ""),
                int(body.get("step_num", 0)),
                body.get("diagram_title", "Diagram"),
                mermaid_code,
            )
        return {"diagram_id": row["id"], "saved_at": str(row["created_at"])}
    except Exception as e:
        logger.error(f"Diagram save error: {e}")
        return {"diagram_id": None, "saved_at": None}


@router.get("/student/{student_id}/tutor/session/diagrams")
async def get_session_diagrams(student_id: str, session_id: str = None, limit: int = 20):
    """Get all saved diagrams for a session (or recent ones across sessions)."""
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if session_id:
                rows = await conn.fetch(
                    """
                    SELECT id, session_id, subject_code, topic, step_num,
                           diagram_title, mermaid_code, created_at
                    FROM tutor_session_diagrams
                    WHERE student_db_id = $1 AND session_id = $2
                    ORDER BY created_at ASC LIMIT $3
                    """,
                    student["db_id"], session_id, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, session_id, subject_code, topic, step_num,
                           diagram_title, mermaid_code, created_at
                    FROM tutor_session_diagrams
                    WHERE student_db_id = $1
                    ORDER BY created_at DESC LIMIT $2
                    """,
                    student["db_id"], limit,
                )
        return {"diagrams": [dict(r) for r in rows]}
    except Exception as e:
        logger.error(f"Diagram fetch error: {e}")
        return {"diagrams": []}


@router.post("/student/{student_id}/tutor/session/event")
async def save_session_event(student_id: str, body: dict):
    """
    Save a single lesson SSE event for replay.
    Body: { session_id, event_type, event_data, step_num }
    """
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    session_id = (body.get("session_id") or "").strip()
    event_type = (body.get("event_type") or "").strip()
    if not session_id or not event_type:
        raise HTTPException(status_code=400, detail="'session_id' and 'event_type' are required")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO session_events
                    (student_db_id, session_id, event_type, event_data, step_num)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                student["db_id"],
                session_id,
                event_type,
                json.dumps(body.get("event_data") or {}),
                int(body.get("step_num", 0)),
            )
        return {"event_id": row["id"]}
    except Exception as e:
        logger.warning(f"Session event save error: {e}")
        return {"event_id": None}


@router.get("/student/{student_id}/tutor/session/{session_id}/events")
async def get_session_events(student_id: str, session_id: str):
    """Fetch all stored events for a session (for replay)."""
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, event_type, event_data, step_num, created_at
                FROM session_events
                WHERE student_db_id = $1 AND session_id = $2
                ORDER BY created_at ASC
                """,
                student["db_id"], session_id,
            )
        events = []
        for r in rows:
            d = dict(r)
            # parse JSONB from string if needed
            if isinstance(d.get("event_data"), str):
                try:
                    d["event_data"] = json.loads(d["event_data"])
                except Exception:
                    pass
            events.append(d)
        return {"session_id": session_id, "events": events, "count": len(events)}
    except Exception as e:
        logger.error(f"Session events fetch error: {e}")
        return {"session_id": session_id, "events": [], "count": 0}


@router.get("/tutor/study-modes")
async def get_study_modes():
    """List all available study mode profiles."""
    return {"modes": list(STUDY_MODE_PROFILES.values())}


@router.get("/tutor/study-modes/{mode}")
async def get_study_mode(mode: str):
    """Get a specific study mode profile."""
    profile = STUDY_MODE_PROFILES.get(mode)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Unknown mode '{mode}'. Valid: {list(STUDY_MODE_PROFILES)}")
    return profile


@router.get("/tutor/supported-languages")
async def get_supported_languages():
    """List languages the AI tutor can teach in."""
    return {
        "languages": [
            {"code": "en", "label": "English", "native": "English", "flag": "🇬🇧"},
            {"code": "ta", "label": "Tamil", "native": "தமிழ்", "flag": "🇮🇳"},
            {"code": "hi", "label": "Hindi", "native": "हिंदी", "flag": "🇮🇳"},
        ],
        "default": "en",
        "note": "Language affects narration and explanation text. Diagrams and code remain in English.",
    }


# In-memory tutor session store: session_id -> { "turns": [{role, content}], "lesson_summary": str }
tutor_sessions: dict[str, dict] = {}


async def build_tutor_context(student_id: str, subject_code: str, topic: str) -> dict:
    """
    Unified tutor context: profile, full learning DNA, syllabus, mastery (including
    this-topic level). Used by both teach and ask for consistent personalization.
    """
    profile = await get_student_profile(student_id)
    if not profile:
        return None

    syllabus = []
    if subject_code:
        syllabus = await db.get_subject_syllabus(subject_code=subject_code)

    mastery_data = {}
    db_id = profile.get("db_id")
    if db_id:
        try:
            mastery_data = await db.get_topic_mastery(db_id)
        except Exception:
            pass

    learning_dna = {}
    try:
        learning_dna = await db.get_learning_dna(student_id)
    except Exception:
        pass

    relevant_subject = None
    for s in profile.get("subjects", []):
        if s.get("code") == subject_code or (topic and topic.lower() in (s.get("name") or "").lower()):
            relevant_subject = s
            break

    bloom_level = relevant_subject.get("bloomLevel", 2) if relevant_subject else 2
    subject_name = relevant_subject.get("name", subject_code) if relevant_subject else subject_code
    att_overall = profile.get("attendanceOverall") or profile.get("attendance_overall")
    arrear_count = profile.get("arrear_count") or profile.get("activeArrears", 0)
    subject_att = relevant_subject.get("live_attendance") or relevant_subject.get("attendance") if relevant_subject else None
    subject_status = relevant_subject.get("status", "safe") if relevant_subject else "safe"

    syllabus_text = ""
    if syllabus:
        units = [f"Unit {s['unit_number']}: {s['unit_title']} — Topics: {s.get('topics', '')}" for s in syllabus[:5]]
        syllabus_text = "\n".join(units)

    topics_list = mastery_data.get("topics", [])
    weak = [t for t in topics_list if not t.get("achieved", False)]
    strong = [t for t in topics_list if t.get("achieved", False)]
    mastery_weak = ", ".join(t.get("topic", t.get("subject_code", "")) for t in weak[:5]) if weak else ""
    mastery_strong = ", ".join(t.get("topic", t.get("subject_code", "")) for t in strong[:5]) if strong else ""

    this_topic_row = None
    topic_lower = (topic or "").lower()
    for t in topics_list:
        tcode = (t.get("subject_code") or "").lower()
        ttop = (t.get("topic") or "").lower()
        if subject_code and tcode == subject_code.lower() and (topic_lower in ttop or ttop in topic_lower or not topic):
            this_topic_row = t
            break
    if not this_topic_row and topics_list:
        this_topic_row = next((t for t in topics_list if (t.get("subject_code") or "").lower() == (subject_code or "").lower()), None)

    style = learning_dna.get("preferred_style", "visual + example-based")
    dna_weak = learning_dna.get("weak_topics") or []
    dna_strong = learning_dna.get("strong_topics") or []
    total_q = learning_dna.get("total_questions") or 0
    total_quiz = learning_dna.get("total_quizzes") or 0
    correct = learning_dna.get("correct_answers") or 0
    accuracy = round(100 * correct / total_q, 1) if total_q else None
    peak_hour = learning_dna.get("peak_hour")

    return {
        "profile": profile,
        "learning_dna": learning_dna,
        "syllabus": syllabus,
        "mastery_data": mastery_data,
        "relevant_subject": relevant_subject,
        "bloom_level": bloom_level,
        "subject_name": subject_name,
        "subject_code": subject_code,
        "topic": topic,
        "style": style,
        "syllabus_text": syllabus_text or "General CS engineering syllabus.",
        "mastery_weak": mastery_weak,
        "mastery_strong": mastery_strong,
        "this_topic_row": this_topic_row,
        "att_overall": att_overall,
        "arrear_count": arrear_count,
        "subject_att": subject_att,
        "subject_status": subject_status,
        "dna_weak": dna_weak,
        "dna_strong": dna_strong,
        "total_questions": total_q,
        "total_quizzes": total_quiz,
        "accuracy": accuracy,
        "peak_hour": peak_hour,
    }

@router.post("/student/{student_id}/tutor/vision")
async def tutor_vision(student_id: str, request: Request):
    """
    Multimodal Vision OCR endpoint using NVIDIA NIM APIs.
    Expects JSON: { image: "base64_string_with_data_url", topic: "string" }
    """
    body = await request.json()
    base64_image = body.get("image")
    topic = body.get("topic", "General")
    
    if not base64_image:
        raise HTTPException(status_code=400, detail="image is required")
        
    if "," in base64_image:
        base64_image = base64_image.split(",")[1]

    if not settings.nvidia_api_key:
        raise HTTPException(status_code=500, detail="NVIDIA NIM API key not configured")

    try:
        from openai import AsyncOpenAI
        import re
        import json
        
        client = AsyncOpenAI(
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key
        )
        
        system_prompt = f"""You are an expert AI Tutor analyzing a scanned image (textbook diagram or notes) for the topic "{topic}".
Analyze the concepts presented.
STRICTLY output a valid JSON containing exactly two fields:
1. "explanation": A concise 2-sentence explanation of the image.
2. "mermaid": A valid Mermaid.js diagram (e.g., flowchart TD) representing the parsed concepts. Use clear, short labels.

Output ONLY the JSON object. Do not wrap in markdown tags if possible."""
        
        vision_model = "meta/llama-3.2-90b-vision-instruct" 
        
        response = await client.chat.completions.create(
            model=vision_model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this image and return the JSON."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2048,
            temperature=0.3
        )
        
        content = response.choices[0].message.content.strip()
        
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()
            
        try:
            parsed = json.loads(content)
            return parsed
        except json.JSONDecodeError:
            mermaid_match = re.search(r"```mermaid\s*\n(.*?)```", content, re.DOTALL)
            mermaid_code = mermaid_match.group(1).strip() if mermaid_match else ""
            return {
                "explanation": content.split("```")[0][:500].strip(),
                "mermaid": mermaid_code
            }

    except Exception as e:
        logger.error(f"Vision API error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vision API failed: {str(e)}")
