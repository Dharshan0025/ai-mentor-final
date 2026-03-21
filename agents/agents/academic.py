"""
AI-Mentor — Academic Agent
Handles: subject Q&A, grade lookups, past paper analysis,
         DAG prerequisite enforcement, Bloom's gating.
LLM: Groq llama-3.3-70b (fast, free tier)
"""
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings
import logging

from db import db
from mentor_strategy import build_mentor_brief

logger = logging.getLogger(__name__)


ACADEMIC_SYSTEM = """You are the Academic Agent for an AI-powered student mentor system.

Your role:
- Answer subject-specific questions grounded in the student's actual ERP data
- Reference their exact grades, attendance, and Bloom's level when relevant
- Flag when a topic requires prerequisite knowledge they may lack
- Suggest relevant past exam question patterns
- Keep responses focused, structured, and actionable

Student Profile:
{student_profile}

Rules:
- ALWAYS cite specific data (e.g., "Your OS grade is 5.4 with 65% attendance")
- Use markdown: **bold** key terms, numbered lists for steps
- Be encouraging — students are stressed; frame issues as solvable
- Maximum 300 words
- If Tamil is requested, respond in Tamil"""


import json

BLOOM_CLASSIFIER_PROMPT = """Analyze this student question and determine two things:
1. The subject code it relates to (from their enrolled subjects list).
2. The Bloom's Taxonomy level of the question (1 to 6).
Bloom levels: 1=Remember, 2=Understand, 3=Apply, 4=Analyze, 5=Evaluate, 6=Create.

Enrolled Subjects: {subject_list}
Student Question: "{question}"

Respond ONLY with a valid JSON object matching this schema: {{"subject_code": "CS702", "bloom_level": 3}}
"""

def _classify_bloom_level(message: str, profile: dict, llm) -> dict:
    subjects = profile.get("subjects", [])
    if not subjects:
        return {"subject_code": None, "bloom_level": 1}
        
    subject_list = ", ".join([f"{s.get('name')} ({s.get('code')})" for s in subjects])
    prompt = BLOOM_CLASSIFIER_PROMPT.format(subject_list=subject_list, question=message)
    
    try:
        res = llm.invoke([HumanMessage(content=prompt)]).content
        # Find json block
        if "```json" in res:
            res = res.split("```json")[1].split("```")[0].strip()
        elif "```" in res:
            res = res.split("```")[1].strip()
        return json.loads(res)
    except Exception as e:
        logger.warning(f"Bloom classification failed: {e}")
        return {"subject_code": None, "bloom_level": 1}

from db import db

async def _get_rag_context(message: str, *, exam_focus: bool = False, student_id: str | None = None) -> str:
    """Embed message and fetch top matching document chunks.

    Also pulls episodic memory facts for the student to enrich the context.
    If exam_focus=True, prefer past exam papers (doc_type='exam_paper').
    """
    context_parts = []

    # ── Episodic Memory ──────────────────────────────────────────────────────
    if student_id:
        try:
            from memory_worker import get_recent_memories
            memories = await get_recent_memories(db, student_id, limit=6)
            if memories:
                mem_lines = "\n".join(
                    f"- [{m['category']}] {m['fact']}" + (f" ({m['subject_code']})" if m.get("subject_code") else "")
                    for m in memories
                )
                context_parts.append(f"\n--- STUDENT EPISODIC MEMORY (from past sessions) ---\n{mem_lines}\n")
        except Exception as exc:
            logger.debug("Episodic memory fetch skipped: %s", exc)

    # ── Vector Search ────────────────────────────────────────────────────────
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        embeddings = HuggingFaceEmbeddings(model_name="all-mpnet-base-v2")
        # Run sync embed in a thread
        import asyncio
        vector = await asyncio.to_thread(embeddings.embed_query, message)

        if exam_focus:
            docs = await db.search_documents(vector, limit=5, doc_type="exam_paper")
            label = "EXCERPTS FROM PAST EXAM PAPERS"
        else:
            docs = await db.search_documents(vector, limit=3)
            label = "EXCERPTS FROM COURSE MATERAL"
        
        if docs:
            doc_context = f"\n--- {label} ---\n"
            for i, d in enumerate(docs):
                if d.get("similarity", 0) > 0.6:  # Threshold
                    doc_context += f"[Source {i+1}: {d.get('filename')}] {d.get('content')}\n\n"
            context_parts.append(doc_context + "------------------------------------\n")

    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")

    return "".join(context_parts)

async def academic_node(state: dict) -> dict:
    """Academic agent — subject Q&A grounded in ERP profile with Bloom's gating and RAG."""
    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.3,
        max_tokens=600,
    )

    profile = state.get("student_profile", {})
    message = state["message"]
    student_id = state.get("student_id")

    learning_dna = state.get("learning_dna")
    if student_id:
        try:
            if learning_dna is None:
                learning_dna = await db.get_learning_dna(student_id)
        except Exception as e:
            logger.warning(f"Learning DNA load failed for {student_id}: {e}")
    
    # 1. Pedagogical Enforcement (Bloom's Gating)
    classifier_result = _classify_bloom_level(message, profile, llm)
    req_subject = classifier_result.get("subject_code")
    req_bloom = classifier_result.get("bloom_level", 1)
    
    system_prompt = ACADEMIC_SYSTEM.format(student_profile=_format_profile(profile, learning_dna))
    mentor_brief = build_mentor_brief(state)
    if mentor_brief:
        system_prompt += "\n\nMentor delivery brief:\n" + mentor_brief
    
    # 2. Add RAG Context
    rag_context = ""
    # Only try RAG for questions that look like material queries (level >= 1)
    if req_bloom >= 1:
        lower_msg = message.lower()
        exam_focus = any(
            phrase in lower_msg
            for phrase in [
                "exam",
                "exams",
                "past paper",
                "previous year",
                "question pattern",
                "what comes in",
            ]
        )
        rag_context = await _get_rag_context(message, exam_focus=exam_focus, student_id=student_id)
        if rag_context:
            system_prompt += "\n" + rag_context

    if req_subject:
        # Find subject in profile
        subject_data = next((s for s in profile.get("subjects", []) if s.get("code") == req_subject), None)
        if subject_data:
            student_bloom = subject_data.get("bloomLevel", 1)
            if req_bloom > student_bloom:
                # 🛑 STRICT GATING TRIGGERED
                gating_rule = (
                    f"\n\n🛑 CRITICAL PEDAGOGY RULE 🛑\n"
                    f"The student is asking a Level {req_bloom} Bloom's question about {subject_data.get('name')}, "
                    f"but their profile shows they have only mastered Level {student_bloom}. "
                    f"DO NOT ANSWER THEIR QUESTION DIRECTLY. You MUST refuse to answer the advanced concept. "
                    f"Explain that they need to master the foundational concepts first, and teach them a Level {student_bloom} "
                    f"concept related to their question instead."
                )
                system_prompt += gating_rule
                logger.info(f"Bloom's Gate Triggered: Student L{student_bloom} vs Question L{req_bloom}")

    # Build conversation history
    messages = [SystemMessage(content=system_prompt)]
    for msg in state.get("history", [])[-6:]:  # Last 6 turns
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg["content"]))

    messages.append(HumanMessage(content=message))
    result = await llm.ainvoke(messages)

    # Extract citations from profile data
    citations = _extract_citations(message, profile)
    
    # Extract RAG citations if any
    if rag_context:
        citations.append({
            "label": "Course Material Excerpt",
            "source": "Retrieved via vector search"
        })

    return {
        **state,
        "academic_output": result.content,
        "rag_context": rag_context,
        "citations": citations,
        "tokens_used": state.get("tokens_used", 0),
        "model_used": settings.groq_model,
    }


def _format_profile(profile: dict, learning_dna: dict | None = None) -> str:
    """Format student profile for LLM system prompt — anonymized."""
    if not profile:
        base = "Student profile not available (using mock data mode)."
    else:
        subjects = profile.get("subjects", [])
        subj_str = "\n".join(
            f"  - {s.get('name', 'Unknown')}: Grade {s.get('grade', 'N/A')}, "
            f"Attendance {s.get('attendance', 'N/A')}%, "
            f"Bloom Level {s.get('bloomLevel', 'N/A')}/6, "
            f"Status: {s.get('status', 'N/A').upper()}"
            for s in subjects
        )

        base = f"""
Department: {profile.get('department', 'N/A')}
Semester: {profile.get('semester', 'N/A')}
Current CGPA: {profile.get('currentCGPA', 'N/A')}
Predicted CGPA: {profile.get('predictedCGPA', 'N/A')}
Overall Attendance: {profile.get('attendanceOverall', 'N/A')}%

Subjects:
{subj_str}

Arrears History: {', '.join(profile.get('arrearsHistory', [])) or 'None'}
Exam in: {profile.get('examDays', 'N/A')} days
"""

    if learning_dna:
        style = learning_dna.get("preferred_style") or "example-based"
        peak_hour = learning_dna.get("peak_hour")
        weak = learning_dna.get("weak_topics") or []
        strong = learning_dna.get("strong_topics") or []

        weak_str = ", ".join(
            w if isinstance(w, str) else str(w.get("topic") or w.get("subject_code") or "") for w in weak[:3]
        ) or "None logged yet"
        strong_str = ", ".join(
            s if isinstance(s, str) else str(s.get("topic") or s.get("subject_code") or "") for s in strong[:3]
        ) or "None logged yet"

        dna_block = f"""
Learning DNA:
- Preferred style: {style}
- Peak study hour (approx.): {f"{peak_hour}:00" if peak_hour is not None else "not known"}
- Weak topics (examples): {weak_str}
- Strong topics (examples): {strong_str}
"""
    else:
        dna_block = "\nLearning DNA: not available; assume average CS engineering student."

    return base + dna_block


def _extract_citations(message: str, profile: dict) -> list[dict]:
    """Auto-extract relevant citations from the student profile."""
    citations = []
    message_lower = message.lower()
    subjects = profile.get("subjects", [])

    for subject in subjects:
        name = subject.get("name", "").lower()
        # Check if the subject is mentioned in the message
        keywords = name.split() + [subject.get("code", "").lower()]
        if any(kw in message_lower for kw in keywords if len(kw) > 2):
            citations.append({
                "label": f"{subject.get('name')}: {subject.get('grade')} GPA",
                "source": f"ERP — Semester {profile.get('semester', '?')}"
            })
            if subject.get("attendance"):
                citations.append({
                    "label": f"Attendance: {subject.get('attendance')}%",
                    "source": "ERP Attendance Record"
                })

    return citations[:3]  # Max 3 citations per response
