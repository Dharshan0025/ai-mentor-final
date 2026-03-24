"""
AI-Mentor Agent Service — FastAPI Entry Point
All agent orchestration routes live here.
Run: uvicorn main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
import logging
import asyncio
import uuid
from datetime import datetime

from config import settings
from utils.llm import get_llm
from pydantic import BaseModel, Field
from schemas import (
    ChatRequest, ChatResponse, HealthResponse, AgentId
)
from orchestrator import get_orchestrator
from db import db, get_pool, close_pool
from scheduler import get_scheduler, run_scan_now
from pipeline_tracker import reset_tracker, get_tracker
from cache_layer import get_cached_response, cache_response, invalidate_cache
from learning_analytics import get_session_analytics

# ── Background task error handling ───────────────────────────────────────────
def handle_background_task_error(task: asyncio.Task):
    """Log exceptions from background tasks to prevent silent failures."""
    try:
        task.result()
    except asyncio.CancelledError:
        pass  # Task was cancelled, not an error
    except Exception as e:
        logger.error(f"🔴 Background task '{task.get_name()}' failed: {e}", exc_info=True)

def create_tracked_task(coro, name: str = "unnamed"):
    """Create a background task with error tracking and logging."""
    task = asyncio.create_task(coro)
    task.set_name(name)
    task.add_done_callback(handle_background_task_error)
    return task

# ── Mock student data (replace with DB in Phase 3) ──────────────────────────
MOCK_STUDENT = {
    "id": "22CSBS001",
    "name": "Dharshan B",
    "department": "Computer Science & Business Systems",
    "year": 4,
    "semester": 7,
    "college": "Anand Institute of Higher Technology",
    "currentCGPA": 7.4,
    "predictedCGPA": 7.6,
    "predictedCGPARange": [7.2, 8.0],
    "cgpaHistory": [7.0, 7.2, 6.9, 7.5, 7.1, 7.3, 7.4],
    "attendanceOverall": 80,
    "examDays": 18,
    "studyStreak": 5,
    "arrearsHistory": ["CS501 cleared — May 2024"],
    "subjects": [
        {"code": "CS701", "name": "Machine Learning",    "grade": 8.1, "attendance": 88, "creditWeight": 4, "bloomLevel": 5, "status": "safe",  "predicted": 8.0},
        {"code": "CS702", "name": "Operating Systems",   "grade": 5.1, "attendance": 65, "creditWeight": 4, "bloomLevel": 2, "status": "risk",  "predicted": 5.1},
        {"code": "CS703", "name": "Database Systems",    "grade": 6.8, "attendance": 78, "creditWeight": 3, "bloomLevel": 3, "status": "watch", "predicted": 6.8},
        {"code": "CS704", "name": "Computer Networks",   "grade": 6.0, "attendance": 76, "creditWeight": 3, "bloomLevel": 2, "status": "watch", "predicted": 6.1},
        {"code": "CS705", "name": "Software Engineering","grade": 8.6, "attendance": 92, "creditWeight": 3, "bloomLevel": 5, "status": "safe",  "predicted": 8.5},
        {"code": "CS706", "name": "Cloud Computing",     "grade": 7.5, "attendance": 83, "creditWeight": 3, "bloomLevel": 4, "status": "safe",  "predicted": 7.4},
    ],
    "sentimentHistory": [0.3, -0.1, 0.4, -0.2, 0.5, 0.2, -0.3, 0.6, 0.1, 0.4,
                         -0.1, 0.3, 0.5, -0.2, 0.4, 0.3, 0.1, 0.6, 0.2, 0.4,
                         -0.1, 0.3, 0.2, 0.5, 0.4, 0.3, 0.6, 0.1, 0.4, 0.5],
}

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── DB state ─────────────────────────────────────────────────────────────────
_db_connected = False

# ── Lifespan — DB pool init/close ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_connected
    try:
        await get_pool()
        _db_connected = True
        logger.info("Connected to Supabase")
    except Exception as e:
        logger.warning(f"DB unavailable, falling back to mock data: {e}")
        _db_connected = False

    # Start proactive alert scheduler
    scheduler = get_scheduler()
    # ── FIX: Add retry logic for scheduler startup ──
    max_retries = 3
    for attempt in range(max_retries):
        try:
            scheduler.start()
            logger.info("✅ Proactive scheduler started (attendance scan at 18:00 IST)")
            break
        except Exception as e:
            logger.error(f"🔴 Scheduler start failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                logger.critical("❌ Scheduler failed to start after retries - alerts DISABLED!")
            else:
                await asyncio.sleep(5)

    # ── FIX: Start background session cleanup task ──
    create_tracked_task(cleanup_stale_sessions(), name="session_cleanup")

    yield

    # Shutdown
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await close_pool()

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI-Mentor Agent Service",
    description="Multi-agent academic mentoring backend powered by LangGraph + Groq + Gemini",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, settings.node_api_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_student_profile(student_id: str) -> dict:
    """
    Fetch student profile from Supabase, falls back to mock if DB is unavailable.
    """
    if _db_connected:
        try:
            profile = await db.get_student_by_college_id(student_id)
            if profile:
                return profile
        except Exception as e:
            logger.warning(f"DB profile fetch failed ({e}), using mock")
    # Fallback: mock data
    return MOCK_STUDENT


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check — confirms all systems operational."""
    agents_ready = ["academic", "prediction", "emotional", "learning", "schedule"]
    llm_ready = bool(settings.groq_api_key) or bool(settings.nvidia_api_key)

    return HealthResponse(
        status="ok",
        version="0.2.0",
        agents_ready=agents_ready,
        db_connected=_db_connected,
        llm_ready=llm_ready,
    )


@app.get("/scheduler/health")
async def scheduler_health():
    """Check scheduler status and running jobs."""
    scheduler = get_scheduler()
    jobs = []
    try:
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "trigger": str(job.trigger),
                "next_run": str(job.next_run_time),
            })
    except Exception as e:
        logger.error(f"Failed to get scheduler jobs: {e}")

    return {
        "status": "healthy" if scheduler.running else "stopped",
        "running": scheduler.running,
        "jobs_count": len(jobs),
        "jobs": jobs,
    }


# ── Voice API (Nova Sonic) ───────────────────────────────────────────────────

class VoiceSynthesizeRequest(BaseModel):
    text: str
    personality: str = "professor"

@app.post("/voice/synthesize")
async def voice_synthesize(request: VoiceSynthesizeRequest):
    from nova_sonic import get_tts
    tts = get_tts(settings)

    async def generate():
        async for chunk in tts.stream_synthesize(request.text, request.personality):
            yield chunk

    return StreamingResponse(generate(), media_type="audio/wav")

@app.post("/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)):
    from nova_sonic import get_stt
    stt = get_stt(settings)
    audio_bytes = await audio.read()
    transcript = await stt.transcribe_audio(audio_bytes, audio.content_type or "audio/webm")
    return {"transcript": transcript}


@app.post("/auth/login")
async def agent_auth_login(body: dict):
    """
    Internal auth endpoint — called by Node.js backend only.
    Verifies college_id + password via bcrypt against the DB.
    Returns student profile dict on success, 401 on failure.
    JWT is issued by the Node.js layer, NOT here.
    """
    college_id = (body.get("college_id") or "").strip().upper()
    password = body.get("password") or ""

    if not college_id or not password:
        raise HTTPException(status_code=400, detail="college_id and password are required")

    if not _db_connected:
        # Dev fallback: allow any non-empty password for seeded IDs
        SEEDED_IDS = {
            "25CSBS001", "25CSBS018", "25CSBS035",
            "24CSBS007", "24CSBS021", "24CSBS044",
            "23CSBS004", "23CSBS019", "23CSBS038",
            "22CSBS001", "22CSBS015", "22CSBS042",
        }
        if college_id not in SEEDED_IDS:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return await get_student_profile(college_id)

    student = await db.authenticate_student(college_id, password)
    if not student:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return student



async def _track_learning_outcome(analytics, response, pipeline, student_profile):
    """Track learning outcomes from this exchange."""
    from learning_analytics import get_session_analytics

    # Track mentor response
    await analytics.track_message(
        "mentor_response",
        response.content,
        metadata={"agent": response.agent.value}
    )

    # Calculate response quality based on pipeline confidence
    if pipeline and "overall_confidence" in pipeline:
        await analytics.calculate_response_quality(pipeline["overall_confidence"])

    # Track if Bloom level increased
    if student_profile and "bloom_level" in student_profile:
        await analytics.track_learning_moment(
            concept=student_profile.get("subject", "general"),
            bloom_level=student_profile.get("bloom_level", 2),
            confidence=pipeline.get("overall_confidence", 0.85) if pipeline else 0.85
        )

    logger.info(f"📊 Learning tracked: Engagement={analytics.metrics['engagement_score']:.0f}, Quality={analytics.metrics['avg_response_quality']:.0f}")


async def _add_peer_insights_to_response(session_id: str, student_id: str, student_profile: dict):
    """Add peer comparison insights to session (for future reference)."""
    from peer_insights import PeerInsightsAnalyzer

    try:
        analyzer = PeerInsightsAnalyzer(student_id)
        peer_comparison = await analyzer.get_peer_comparison(student_profile)
        logger.info(f"✅ Peer insights calculated for {student_id}: {peer_comparison.get('summary', {}).get('overall_percentile', 'N/A')}th percentile")
    except Exception as e:
        logger.warning(f"Peer insights failed: {e}")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main orchestrated chat endpoint.
    Routes to academic/prediction/emotional/learning/schedule agents based on intent.
    Phase 2: synchronous response. Phase 3+: SSE streaming.
    Uses Redis caching for 5-10 min TTL on common queries.
    """
    # ── Check cache first (5-10 min TTL) ──
    cached = await get_cached_response(request.student_id, request.message)
    if cached:
        logger.info(f"✅ Returning cached response for {request.student_id}")
        cached.pop("cached_at", None)
        cached.pop("ttl_remaining", None)
        return ChatResponse(**cached)

    # ── FIX: Initialize pipeline tracker for this request ──
    reset_tracker()
    tracker = get_tracker()

    # ── FIX: Input validation to prevent malformed requests ──
    if not request.student_id or not request.student_id.strip():
        raise HTTPException(status_code=400, detail="student_id is required")
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    logger.info(f"Chat request | session={request.session_id} | student={request.student_id}")

    # ── Initialize learning analytics for this session ──
    analytics = get_session_analytics(request.session_id, request.student_id)
    await analytics.track_message("user_question", request.message)

    student_profile = await get_student_profile(request.student_id)
    if not student_profile or not student_profile.get("id"):
        raise HTTPException(status_code=404, detail="Student profile not found")
    learning_dna = {}
    if _db_connected:
        try:
            learning_dna = await db.get_learning_dna(request.student_id) or {}
        except Exception as e:
            logger.warning(f"Learning DNA preload failed for {request.student_id}: {e}")

    # Build initial state for LangGraph
    initial_state = {
        "message":         request.message,
        "session_id":      request.session_id,
        "student_id":      request.student_id,
        "lang":            request.lang.value,
        "history":         [msg.model_dump() for msg in request.history],
        "student_profile": student_profile,
        "learning_dna":    learning_dna,
        "student_snapshot": "",
        # Agent outputs (all None initially)
        "intent":              "",
        "agents_to_invoke":    [],
        "mentor_plan":         {},
        "academic_output":     None,
        "prediction_output":   None,
        "emotional_output":    None,
        "learning_output":     None,
        "schedule_output":     None,
        "career_output":       None,
        "rag_context":         None,
        "sentiment_score":     0.0,
        "final_response":      "",
        "ui_card":             None,
        "suggested_actions":   [],
        "xp_awarded":          0,
        "primary_agent":       "academic",
        "citations":           [],
        "tokens_used":         0,
        "model_used":          "",
        "models_used":         [],
    }

    try:
        orchestrator = get_orchestrator()
        final_state = await orchestrator.ainvoke(initial_state)

        # ── Fire-and-forget sentiment write-back ──────────────────────────
        # Extract score from state (emotional_node always sets this)
        sentiment_score = final_state.get("sentiment_score")
        if sentiment_score is not None and _db_connected:
            create_tracked_task(
                db.append_sentiment_point(
                    student_id=request.student_id,
                    score=sentiment_score,
                    message_snippet=request.message[:120],
                ),
                name=f"sentiment_write_{request.student_id}"
            )

        # ── Fire-and-forget episodic memory extraction ────────────────────
        if _db_connected:
            from memory_worker import extract_and_store_memories
            create_tracked_task(
                extract_and_store_memories(
                    student_id=request.student_id,
                    session_id=request.session_id,
                    message=request.message,
                    response=final_state.get("final_response", ""),
                    student_profile=student_profile,
                    db=db,
                ),
                name=f"memory_extract_{request.student_id}"
            )

        # ── Fire-and-forget message persistence ─────────────────────────────
        if _db_connected and student_profile.get("db_id"):
            db_id = student_profile["db_id"]
            # 1. Ensure the session exists
            await db.ensure_chat_session(request.session_id, db_id, title=request.message[:40])

            # 2. Save user message
            create_tracked_task(
                db.save_message(
                    session_id=request.session_id,
                    student_db_id=db_id,
                    role="user",
                    content=request.message,
                    lang=request.lang.value
                ),
                name=f"save_user_msg_{request.session_id}"
            )
            # 3. Save assistant message
            create_tracked_task(
                db.save_message(
                    session_id=request.session_id,
                    student_db_id=db_id,
                    role="assistant",
                    content=final_state.get("final_response", ""),
                    agent=final_state.get("primary_agent", "academic"),
                    citations=final_state.get("citations", []),
                    model_used=final_state.get("model_used", ""),
                    lang=request.lang.value
                ),
                name=f"save_asst_msg_{request.session_id}"
            )

        response = ChatResponse(
            session_id=request.session_id,
            agent=AgentId(final_state.get("primary_agent", "academic")),
            content=final_state.get("final_response", "I couldn't process that. Please try again."),
            citations=final_state.get("citations", []),
            tokens_used=final_state.get("tokens_used", 0),
            model_used=final_state.get("model_used", ""),
            ui_card=final_state.get("ui_card"),
            suggested_actions=final_state.get("suggested_actions", []),
            xp_awarded=final_state.get("xp_awarded", 0),
            pipeline=final_state.get("pipeline") if request.show_pipeline else None,
        )

        # ── Track learning outcomes ──
        create_tracked_task(
            _track_learning_outcome(
                analytics=analytics,
                response=response,
                pipeline=final_state.get("pipeline"),
                student_profile=student_profile,
            ),
            name=f"track_learning_{request.session_id}"
        )

        # ── Optional: Add peer insights to response (non-blocking) ──
        if request.show_pipeline:  # Only if user wants detailed insights
            create_tracked_task(
                _add_peer_insights_to_response(
                    session_id=request.session_id,
                    student_id=request.student_id,
                    student_profile=student_profile,
                ),
                name=f"peer_insights_{request.session_id}"
            )

        # ── Cache response for future queries (5 min TTL) ──
        create_tracked_task(
            cache_response(
                student_id=request.student_id,
                message=request.message,
                response_data=response.model_dump(),
                ttl_minutes=5
            ),
            name=f"cache_response_{request.session_id}"
        )

        return response

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Agent service temporarily unavailable")


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming chat endpoint — returns pipeline stages in real-time via SSE.
    Shows the AI thinking process as it happens.
    """
    # ── Initialize pipeline tracker ──
    reset_tracker()
    tracker = get_tracker()

    # ── Input validation ──
    if not request.student_id or not request.student_id.strip():
        raise HTTPException(status_code=400, detail="student_id is required")
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    logger.info(f"Chat stream request | session={request.session_id} | student={request.student_id}")

    student_profile = await get_student_profile(request.student_id)
    if not student_profile or not student_profile.get("id"):
        raise HTTPException(status_code=404, detail="Student profile not found")

    learning_dna = {}
    if _db_connected:
        try:
            learning_dna = await db.get_learning_dna(request.student_id) or {}
        except Exception as e:
            logger.warning(f"Learning DNA preload failed for {request.student_id}: {e}")

    # Build initial state for LangGraph
    initial_state = {
        "message":         request.message,
        "session_id":      request.session_id,
        "student_id":      request.student_id,
        "lang":            request.lang.value,
        "history":         [msg.model_dump() for msg in request.history],
        "student_profile": student_profile,
        "learning_dna":    learning_dna,
        "student_snapshot": "",
        "intent":              "",
        "agents_to_invoke":    [],
        "mentor_plan":         {},
        "academic_output":     None,
        "prediction_output":   None,
        "emotional_output":    None,
        "learning_output":     None,
        "schedule_output":     None,
        "career_output":       None,
        "rag_context":         None,
        "sentiment_score":     0.0,
        "final_response":      "",
        "ui_card":             None,
        "suggested_actions":   [],
        "xp_awarded":          0,
        "primary_agent":       "academic",
        "citations":           [],
        "tokens_used":         0,
        "model_used":          "",
        "models_used":         [],
    }

    async def stream_generator():
        """Stream pipeline stages as they complete."""
        try:
            orchestrator = get_orchestrator()
            final_state = await orchestrator.ainvoke(initial_state)

            # Stream each pipeline stage as it becomes available
            pipeline_data = final_state.get("pipeline")
            if pipeline_data:
                # Stage 1: Intent Parsing
                if pipeline_data.get("intent"):
                    yield f"event: stage\ndata: {json.dumps({'stage': 'intent', 'data': pipeline_data['intent']})}\n\n"

                # Stage 2: Agent Selection
                if pipeline_data.get("agent_selection"):
                    yield f"event: stage\ndata: {json.dumps({'stage': 'agent_selection', 'data': pipeline_data['agent_selection']})}\n\n"

                # Stage 3: Context Loading
                if pipeline_data.get("context"):
                    yield f"event: stage\ndata: {json.dumps({'stage': 'context', 'data': pipeline_data['context']})}\n\n"

                # Stage 4: Agent Reasoning
                if pipeline_data.get("agent_outputs"):
                    yield f"event: stage\ndata: {json.dumps({'stage': 'agent_outputs', 'data': pipeline_data['agent_outputs']})}\n\n"

                # Stage 5: Synthesis
                if pipeline_data.get("synthesis"):
                    yield f"event: stage\ndata: {json.dumps({'stage': 'synthesis', 'data': pipeline_data['synthesis']})}\n\n"

            # Stream final response
            yield f"event: response\ndata: {json.dumps({'content': final_state.get('final_response', ''), 'agent': final_state.get('primary_agent', 'academic')})}\n\n"

            # Stream metadata
            yield f"event: metadata\ndata: {json.dumps({'tokens': final_state.get('tokens_used', 0), 'model': final_state.get('model_used', ''), 'confidence': pipeline_data.get('overall_confidence', 0.85) if pipeline_data else 0.85})}\n\n"

            # Signal completion
            yield f"event: done\ndata: {json.dumps({'success': True})}\n\n"

            # ── Background tasks (fire-and-forget) ──
            sentiment_score = final_state.get("sentiment_score")
            if sentiment_score is not None and _db_connected:
                create_tracked_task(
                    db.append_sentiment_point(
                        student_id=request.student_id,
                        score=sentiment_score,
                        message_snippet=request.message[:120],
                    ),
                    name=f"sentiment_write_{request.student_id}"
                )

            if _db_connected:
                from memory_worker import extract_and_store_memories
                create_tracked_task(
                    extract_and_store_memories(
                        student_id=request.student_id,
                        session_id=request.session_id,
                        message=request.message,
                        response=final_state.get("final_response", ""),
                        student_profile=student_profile,
                        db=db,
                    ),
                    name=f"memory_extract_{request.student_id}"
                )

            if _db_connected and student_profile.get("db_id"):
                db_id = student_profile["db_id"]
                await db.ensure_chat_session(request.session_id, db_id, title=request.message[:40])
                create_tracked_task(
                    db.save_message(
                        session_id=request.session_id,
                        student_db_id=db_id,
                        role="user",
                        content=request.message,
                        lang=request.lang.value
                    ),
                    name=f"save_user_msg_{request.session_id}"
                )
                create_tracked_task(
                    db.save_message(
                        session_id=request.session_id,
                        student_db_id=db_id,
                        role="assistant",
                        content=final_state.get("final_response", ""),
                        agent=final_state.get("primary_agent", "academic"),
                        citations=final_state.get("citations", []),
                        model_used=final_state.get("model_used", ""),
                        lang=request.lang.value
                    ),
                    name=f"save_asst_msg_{request.session_id}"
                )

        except Exception as e:
            logger.error(f"Chat stream error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            yield f"event: done\ndata: {json.dumps({'success': False})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@app.get("/student/{student_id}/chat/sessions")
async def get_chat_sessions_endpoint(student_id: str):
    """Fetch recent chat sessions for a student."""
    if not _db_connected:
        return []
    profile = await get_student_profile(student_id)
    if not profile or "db_id" not in profile:
        return []
    return await db.get_chat_sessions(profile["db_id"])

@app.get("/student/{student_id}/chat/{session_id}/history")
async def get_chat_session_history(student_id: str, session_id: str):
    """Fetch history for a specific chat session."""
    if not _db_connected:
        return []
    # For extra security we could verify student_id matches session, keeping it simple
    return await db.get_chat_history(session_id)


@app.get("/student/{student_id}/tutor/options")
async def get_tutor_options(student_id: str):
    """
    Tutor UI options from DB only: subjects and topics per subject.
    Subjects from student profile (subject_profiles); topics from subject_syllabus.
    No hardcoded data.
    """
    options = await db.get_tutor_options(student_id)
    return options


@app.get("/student/{student_id}/profile")
async def get_profile(student_id: str):
    """Return student profile — Supabase (with mock fallback)."""
    from agents.prediction import compute_predicted_cgpa

    profile = await get_student_profile(student_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Student not found")

    result = compute_predicted_cgpa(profile)
    profile["predictedCGPA"] = result["cgpa"]
    profile["predictedCGPARange"] = result["range"]

    return profile


@app.get("/student/{student_id}/sentiment")
async def get_sentiment(student_id: str, limit: int = 30):
    """
    Return the live sentiment history for the student.
    Each point: { score: float, recorded_at: str }
    Also includes rolling_avg across all points and mood_label.
    """
    history = await db.get_sentiment_history(student_id, limit=limit)

    if not history:
        return {
            "student_id": student_id,
            "history": [],
            "rolling_avg": 0.0,
            "mood_label": "Neutral",
            "data_points": 0,
        }

    scores = [p["score"] for p in history]
    avg = round(sum(scores) / len(scores), 3)
    mood = "Positive" if avg > 0.2 else "Negative" if avg < -0.2 else "Neutral"

    return {
        "student_id": student_id,
        "history": history,
        "rolling_avg": avg,
        "mood_label": mood,
        "data_points": len(history),
    }


@app.get("/student/{student_id}/benchmark")
async def get_benchmark(student_id: str):
    """
    Peer benchmarking — CGPA and attendance percentiles vs same department/semester.
    Anonymous; no PII of other students exposed.
    """
    if not _db_connected:
        raise HTTPException(status_code=503, detail="Database unavailable")
    benchmark = await db.get_peer_benchmark(student_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Student not found")
    return benchmark


# ── XP / Gamification Endpoints ───────────────────────────────────────────────

class XPAwardRequest(BaseModel):
    student_id: str
    xp: int = Field(..., ge=1, le=500, description="XP points to award (1–500)")
    reason: str = ""


@app.post("/xp/award", summary="Award XP to a student")
async def award_xp(req: XPAwardRequest):
    """Award XP points for high-quality questions, quiz completions, etc."""
    if not _db_connected:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        pool = db._pool
        if pool is None:
            raise HTTPException(status_code=503, detail="DB pool unavailable")
        async with pool.acquire() as conn:
            await conn.execute("CALL award_xp($1, $2)", req.student_id, req.xp)
            row = await conn.fetchrow(
                "SELECT total_xp, level FROM student_xp WHERE student_id = $1",
                req.student_id,
            )
        return {
            "student_id": req.student_id,
            "xp_awarded": req.xp,
            "total_xp": row["total_xp"] if row else req.xp,
            "level": row["level"] if row else 1,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("XP award failed: %s", exc)
        raise HTTPException(status_code=500, detail="XP award failed")


@app.get("/xp/leaderboard", summary="Top-10 students by XP")
async def get_leaderboard(limit: int = 10):
    """Returns anonymised leaderboard — name initials + department only."""
    if not _db_connected:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        pool = db._pool
        if pool is None:
            raise HTTPException(status_code=503, detail="DB pool unavailable")
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT x.student_id, x.total_xp, x.level,
                       s.name, s.department
                FROM student_xp x
                LEFT JOIN students s ON s.student_id = x.student_id
                ORDER BY x.total_xp DESC
                LIMIT $1
                """,
                limit,
            )
        entries = [
            {
                "rank": i + 1,
                "student_id": r["student_id"],
                "display_name": (r["name"] or "Student")[:3] + "***",
                "department": r["department"] or "",
                "total_xp": r["total_xp"],
                "level": r["level"],
            }
            for i, r in enumerate(rows)
        ]
        return {"leaderboard": entries}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Leaderboard fetch failed: %s", exc)
        raise HTTPException(status_code=500, detail="Leaderboard unavailable")


@app.get("/student/{student_id}/memories", summary="Get episodic memories for a student")
async def get_memories(student_id: str, limit: int = 20):
    """Returns the most recent episodic memory facts extracted from past sessions."""
    if not _db_connected:
        raise HTTPException(status_code=503, detail="Database unavailable")
    from memory_worker import get_recent_memories
    memories = await get_recent_memories(db, student_id, limit=limit)
    return {"student_id": student_id, "memories": memories, "count": len(memories)}


@app.get("/student/{student_id}/parent-summary")
async def get_parent_summary(student_id: str):
    """
    Parent engagement v1 — weekly-style report: attendance, risk subjects, fees, alerts.
    Designed for parent-teacher meetings or parent portal.
    """
    if not _db_connected:
        raise HTTPException(status_code=503, detail="Database unavailable")
    summary = await db.get_parent_summary(student_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Student not found")
    return summary


@app.get("/student/{student_id}/mastery")
async def get_mastery(student_id: str):
    """
    Topic-level mastery view — summarizes bloom_progress and student_attempts
    for the student.
    """
    profile = await get_student_profile(student_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Student not found")

    db_id = profile.get("db_id")
    if not db_id:
        raise HTTPException(status_code=500, detail="Student profile missing db_id")

    mastery = await db.get_topic_mastery(db_id)
    return {
        "student_id": student_id,
        "student_name": profile.get("name"),
        "topics": mastery.get("topics", []),
        "attempts": mastery.get("attempts", []),
    }


@app.post("/student/{student_id}/simulate")
async def simulate_scenario(student_id: str, body: dict):
    """
    Scenario simulator — numeric CGPA delta + LLM explanation of the change.
    Body: { attendance_delta, assignment_delta, study_hours_delta }
    """
    from agents.prediction import compute_predicted_cgpa, run_sim_explanation
    import copy

    profile = await get_student_profile(student_id)

    improvement = {
        "attendance_delta":  float(body.get("attendance_delta", 0)),
        "assignment_delta":  float(body.get("assignment_delta", 0)),
        "study_hours_delta": float(body.get("study_hours_delta", 0)),
    }
    add_explanation = body.get("explain", False)  # frontend requests LLM explanation

    baseline_profile = copy.deepcopy(profile)
    baseline = compute_predicted_cgpa(baseline_profile)

    sim_profile = copy.deepcopy(profile)
    sim = compute_predicted_cgpa(sim_profile, improvement=improvement)

    subject_diffs = []
    for b_subj, s_subj in zip(baseline_profile.get("subjects", []), sim_profile.get("subjects", [])):
        before = b_subj.get("predicted", b_subj.get("grade", 0))
        after  = s_subj.get("predicted", b_subj.get("grade", 0))
        subject_diffs.append({
            "name":    b_subj.get("name"),
            "current": b_subj.get("grade", 0),
            "before":  round(before, 1),
            "after":   round(after, 1),
            "delta":   round(after - before, 2),
            "status":  s_subj.get("status", b_subj.get("status", "safe")),
        })

    # LLM explanation (async, optional)
    explanation = ""
    if add_explanation:
        explanation = await run_sim_explanation(
            profile, improvement, baseline["cgpa"], sim["cgpa"]
        )

    return {
        "student_id":      student_id,
        "baseline_cgpa":   baseline["cgpa"],
        "baseline_range":  baseline["range"],
        "simulated_cgpa":  sim["cgpa"],
        "simulated_range": sim["range"],
        "cgpa_delta":      round(sim["cgpa"] - baseline["cgpa"], 3),
        "subjects":        subject_diffs,
        "improvement":     improvement,
        "explanation":     explanation,
    }


@app.get("/student/{student_id}/predictions")
async def get_predictions(student_id: str):
    """
    Agentic prediction endpoint — 2-phase NVIDIA NIM (llama-3.3-70b-instruct) deep analysis.
    Phase 1: structured JSON (risk scores, arrear risk, critical moves)
    Phase 2: markdown narrative (conversational tutor-style explanation)
    Falls back to Groq if NVIDIA NIM is unavailable.
    """
    from agents.prediction import compute_predicted_cgpa, run_llm_analysis, build_prediction_fallback

    profile = await get_student_profile(student_id)

    # Fetch Learning DNA for richer context (non-fatal)
    learning_dna: dict = {}
    try:
        learning_dna = await db.get_learning_dna(student_id) or {}
    except Exception as e:
        logger.warning(f"Learning DNA unavailable for predictions ({e})")

    # Numeric CGPA forecast (sklearn linear regression)
    try:
        numeric = compute_predicted_cgpa(profile)
    except Exception as e:
        logger.warning(f"Numeric prediction failed for {student_id}: {e}")
        current_cgpa = profile.get("currentCGPA") or profile.get("cgpa") or 0.0
        numeric = {
            "cgpa": round(float(current_cgpa or 0.0), 2),
            "range": [round(max(0.0, float(current_cgpa or 0.0) - 0.3), 1), round(min(10.0, float(current_cgpa or 0.0) + 0.3), 1)],
            "confidence": 0.0,
        }
    subjects = profile.get("subjects") or []

    # 2-phase LLM deep analysis (async)
    try:
        analysis = await run_llm_analysis(profile, learning_dna)
    except Exception as e:
        logger.warning(f"Prediction analysis failed for {student_id}: {e}")
        analysis = build_prediction_fallback(profile)

    # Build per-subject prediction list (merge numeric + LLM deep_dive)
    deep_by_code = {d["code"]: d for d in analysis.get("subject_deep_dive", [])}
    subject_predictions = []
    for s in subjects:
        code = s.get("code", "")
        deep = deep_by_code.get(code, {})
        subject_predictions.append({
            "code":              code,
            "name":              s.get("name"),
            "current_grade":     s.get("grade"),
            "predicted_grade":   s.get("predicted"),
            "attendance":        s.get("live_attendance") or s.get("attendance"),
            "credit_weight":     s.get("creditWeight") or s.get("credit_weight", 3),
            "bloom_level":       s.get("bloomLevel") or s.get("bloom_level", 2),
            "status":            s.get("status"),
            "risk_score":        deep.get("risk_score", 0),
            "arrear_probability":deep.get("arrear_probability", 0.0),
            "root_causes":       deep.get("root_causes", _get_risk_drivers(s)),
            "immediate_actions": deep.get("immediate_actions", []),
            "prognosis":         deep.get("prognosis", s.get("status", "safe")),
        })

    risk_subjects  = [s for s in subjects if s.get("status") == "risk"]
    watch_subjects = [s for s in subjects if s.get("status") == "watch"]
    cgpa_verdict   = analysis.get("cgpa_verdict", {})

    return {
        "student_id":          student_id,
        "student_name":        profile.get("name"),
        # Numeric forecast
        "predicted_cgpa":      numeric["cgpa"],
        "cgpa_range":          numeric["range"],
        "confidence":          numeric.get("confidence", 0.7),
        # LLM supplemented verdict
        "cgpa_verdict":        cgpa_verdict,
        "trajectory_signal":   analysis.get("trajectory_signal", "stable"),
        "trajectory_reason":   analysis.get("trajectory_reason", ""),
        # Per-subject enriched list
        "subjects":            subject_predictions,
        # Aggregated risk lists
        "arrear_risk":         analysis.get("arrear_risk", []),
        "risk_subject_count":  len(risk_subjects),
        "watch_subject_count": len(watch_subjects),
        # LLM actionable intelligence
        "critical_moves":      analysis.get("critical_moves", []),
        "study_dna_impact":    analysis.get("study_dna_impact", ""),
        # LLM-generated markdown narrative
        "analysis_narrative":  analysis.get("analysis_narrative", ""),
        "providers":           analysis.get("providers", {}),
        "exam_days":           profile.get("examDays") or profile.get("exam_days"),
        "generated_at":        datetime.utcnow().isoformat(),
    }


@app.get("/student/{student_id}/schedule")
async def get_schedule(student_id: str):
    """AI-generated personalized study schedule using Groq LLM + real ERP data."""
    from agents.schedule import (
        generate_ai_schedule, generate_subject_tips,
        build_schedule_rationale, build_subject_breakdown
    )
    from datetime import datetime

    profile = await get_student_profile(student_id)

    # Fetch Learning DNA (non-fatal)
    learning_dna: dict = {}
    try:
        learning_dna = await db.get_learning_dna(student_id) or {}
    except Exception as e:
        logger.warning(f"Learning DNA unavailable for schedule ({e})")

    # Generate schedule with LLM (async, with fallback)
    week, _schedule_provider = await generate_ai_schedule(profile, learning_dna)

    # Generate per-subject tips (async LLM, capped at 4 subjects)
    subjects = profile.get("subjects", profile.get("subject_profiles", []))
    tips = await generate_subject_tips(subjects, learning_dna)

    # Derived stats
    subject_breakdown = build_subject_breakdown(week)
    rationale = build_schedule_rationale(profile, learning_dna)
    risk_subjects  = [s for s in subjects if s.get("status") == "risk"]
    watch_subjects = [s for s in subjects if s.get("status") == "watch"]
    total_mins = sum(sl.get("duration_min", 60) for d in week for sl in d.get("slots", []))
    risk_slots  = sum(1 for d in week for sl in d.get("slots", []) if sl.get("type") == "risk")
    exam_days   = profile.get("examDays") or profile.get("exam_days")
    peak_hour   = learning_dna.get("peak_hour")

    # Overdue assignments
    overdue_assignments = [
        {
            "subject_code": a.get("subject_code"),
            "title": a.get("title"),
            "due_date": str(a.get("due_date") or ""),
        }
        for a in profile.get("assignments", [])
        if a.get("submission_status") == "not_submitted"
    ]

    # Syllabus coverage gaps for frontend display
    coverage_summary = [
        {
            "subject_code": c.get("subject_code"),
            "subject_name": c.get("subject_name"),
            "unit_title": c.get("unit_title"),
            "coverage_pct": float(c.get("coverage_pct") or 0),
        }
        for c in profile.get("syllabusCoverage", profile.get("syllabus_coverage", []))
        if float(c.get("coverage_pct") or 0) < 70
    ][:6]

    return {
        "student_id":          student_id,
        "student_name":        profile.get("name"),
        "week":                week,
        "subject_breakdown":   list(subject_breakdown.values()),
        "tips":                tips,
        "total_study_hours":   round(total_mins / 60, 1),
        "risk_subject_hours":  round(risk_slots * 1.5, 1),
        "risk_subject_count":  len(risk_subjects),
        "watch_subject_count": len(watch_subjects),
        "exam_days":           exam_days,
        "peak_hour":           peak_hour,
        "preferred_style":     learning_dna.get("preferred_style"),
        "ai_rationale":        rationale,
        "overdue_assignments": overdue_assignments,
        "coverage_gaps":       coverage_summary,
        "generated_at":        datetime.utcnow().isoformat(),
    }



@app.get("/student/{student_id}/career")
async def get_career(student_id: str):
    """Generate full career intelligence report for the student."""
    from agents.career import generate_career_report
    profile = await get_student_profile(student_id)
    return generate_career_report(profile)


@app.post("/quiz/generate")
async def generate_quiz_endpoint(body: dict):
    """
    Generate AI-powered MCQ quiz questions for a given subject/topic/bloom level.
    Body: { subject, topic, bloom_level, student_id? }

    If student_id is provided, auto-resolves the real Bloom level for the subject
    from the student's ERP profile — prevents frontend from bypassing Bloom gating.
    Returns: { subject, topic, bloom_level, bloom_name, questions: [...], total }
    """
    from agents.learning import generate_quiz
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


def _get_risk_drivers(subject: dict) -> list[str]:

    drivers = []
    if subject.get("attendance", 100) < 75:
        drivers.append(f"Attendance at {subject.get('attendance')}% (below 75% threshold)")
    if subject.get("grade", 10) < 6.0:
        drivers.append(f"Grade {subject.get('grade')} is below pass threshold")
    if subject.get("bloomLevel", 6) <= 2:
        drivers.append("Bloom level ≤2 indicates surface-level understanding only")
    return drivers or ["Performing within expected range"]


# ════════════════════════════════════════════════════════════════════════
# PROACTIVE ALERTS — Attendance Cliff Warning + Sentiment Crash
# ════════════════════════════════════════════════════════════════════════

@app.get("/student/{student_id}/alerts")
async def get_alerts(student_id: str):
    """
    Return all unread proactive alerts for a student.
    Alerts are created by the nightly scheduler (APScheduler).
    Frontend polls this on load to show the notification badge.
    """
    alerts = await db.get_unread_alerts(student_id)
    count = len(alerts)
    return {
        "student_id": student_id,
        "unread_count": count,
        "alerts": alerts,
        "has_critical": any(a["severity"] == "critical" for a in alerts),
    }


@app.post("/student/{student_id}/alerts/{alert_id}/read")
async def dismiss_alert(student_id: str, alert_id: str):
    """Mark an alert as read (dismissed by the student)."""
    ok = await db.mark_alert_read(alert_id, student_id)
    return {"success": ok, "alert_id": alert_id}


@app.post("/student/{student_id}/alerts/scan")
async def trigger_scan(student_id: str):
    """
    Manual trigger — runs the attendance + sentiment scan immediately.
    Use this for testing without waiting for the nightly cron.
    """
    import asyncio
    asyncio.create_task(run_scan_now())
    return {
        "status": "scan_triggered",
        "message": "Attendance cliff scan started in background. Check /alerts in ~5 seconds.",
    }


@app.get("/student/{student_id}/alerts/stream")
async def stream_alerts(student_id: str, request: Request):
    """
    SSE endpoint — streams new alerts to the frontend in real-time.
    Keeps connection open, polls DB every 10s for new unread alerts,
    sends only newly-appeared alerts as SSE events.
    """

    async def event_generator():
        known_ids: set[str] = set()
        # Seed with current alerts so we don't re-fire them
        try:
            initial = await db.get_unread_alerts(student_id)
            known_ids = {a["id"] for a in initial}
        except Exception:
            pass

        # Send initial count so frontend can sync badge immediately
        yield f"event: count\ndata: {json.dumps({'unread_count': len(known_ids)})}\n\n"

        # ── FIX: Add max duration limit (1 hour) to prevent resource exhaustion ──
        start_time = datetime.now()
        MAX_DURATION_SECONDS = 3600

        while True:
            # Check 1: Client disconnected
            if await request.is_disconnected():
                logger.info(f"✅ SSE client disconnected: {student_id}")
                break

            # Check 2: Max duration exceeded
            if (datetime.now() - start_time).total_seconds() > MAX_DURATION_SECONDS:
                logger.info(f"✅ SSE max duration reached for {student_id} (1 hour)")
                break

            try:
                alerts = await db.get_unread_alerts(student_id)
                current_ids = {a["id"] for a in alerts}
                new_alerts = [a for a in alerts if a["id"] not in known_ids]

                if new_alerts:
                    for alert in new_alerts:
                        yield f"event: alert\ndata: {json.dumps(alert)}\n\n"
                    known_ids = current_ids

                # Always send a heartbeat count so badge stays accurate
                yield f"event: count\ndata: {json.dumps({'unread_count': len(current_ids)})}\n\n"
            except asyncio.CancelledError:
                logger.info(f"✅ SSE cancelled: {student_id}")
                break
            except Exception as e:
                logger.warning(f"🔴 SSE alert stream error: {e}")
                yield f"event: error\ndata: {json.dumps({'error': 'Internal error'})}\n\n"
                break  # Exit on error instead of continuing indefinitely

            await asyncio.sleep(10)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ════════════════════════════════════════════════════════════════════════
# PHASE 2: PROACTIVE INTELLIGENCE ENDPOINTS
# ════════════════════════════════════════════════════════════════════════

@app.get("/student/{student_id}/briefing")
async def get_proactive_briefing(student_id: str):
    """
    Proactive Intelligence Briefing — the 'Morning Mission Control'.
    Returns top urgent actions derived entirely from real ERP data.
    No LLM needed. Pure data-driven intelligence.
    """
    profile = await get_student_profile(student_id)
    alerts = []
    now = datetime.now()

    # ── Alert 1: Attendance Danger Zone ──────────────────────────────────
    for subj in profile.get("subjects", []):
        att = subj.get("live_attendance") or subj.get("attendance") or 0
        total = subj.get("total_classes", 0)
        name = subj.get("name", subj.get("code"))

        if att < 65:
            alerts.append({
                "type": "critical",
                "icon": "🚨",
                "category": "attendance",
                "subject": name,
                "message": f"{name}: {att}% attendance — DETENTION RISK. Attend ALL remaining classes.",
                "priority": 1,
            })
        elif att < 75:
            # Calculate classes needed to reach 75%
            attended = subj.get("attended", 0)
            # classes_needed = ceil((0.75 * (total + x) - attended) / 0.25)
            classes_needed = max(0, int((0.75 * total - attended) / 0.25) + 1)
            alerts.append({
                "type": "warning",
                "icon": "⚠️",
                "category": "attendance",
                "subject": name,
                "message": f"{name}: {att}% attendance (below 75%). Attend next {classes_needed} class(es) without fail.",
                "priority": 2,
                "classes_needed": classes_needed,
            })
        elif att < 80:
            alerts.append({
                "type": "notice",
                "icon": "📊",
                "category": "attendance",
                "subject": name,
                "message": f"{name}: {att}% — dropping toward 75% danger zone. Don't miss any.",
                "priority": 3,
            })

    # ── Alert 2: Unsubmitted Assignments ─────────────────────────────────
    overdue = [
        a for a in profile.get("assignments", [])
        if a.get("submission_status") == "not_submitted"
    ]
    if overdue:
        names = ", ".join(a.get("title", a.get("subject_code")) for a in overdue[:2])
        alerts.append({
            "type": "warning",
            "icon": "📝",
            "category": "assignments",
            "message": f"{len(overdue)} assignment(s) not submitted: {names}. This directly impacts internal marks.",
            "priority": 2,
            "count": len(overdue),
        })

    # ── Alert 3: Exam Countdown ───────────────────────────────────────────
    exam_days = profile.get("examDays", 0)
    if exam_days and exam_days <= 30:
        risk_subjects = [s["name"] for s in profile.get("subjects", []) if s.get("status") == "risk"]
        msg = f"End semester exam in {exam_days} days."
        if risk_subjects:
            msg += f" Priority: {', '.join(risk_subjects[:2])} (at-risk)."
        alerts.append({
            "type": "info",
            "icon": "📅",
            "category": "exam",
            "message": msg,
            "priority": 3,
            "days": exam_days,
        })

    # ── Alert 4: Placement Intelligence ──────────────────────────────────
    placement = profile.get("placement", [])
    shortlisted = [p for p in placement if p.get("status") == "shortlisted"]
    if shortlisted:
        company = shortlisted[0].get("company_name", "a company")
        alerts.append({
            "type": "info",
            "icon": "🚀",
            "category": "placement",
            "message": f"Shortlisted at {company}. Interview prep recommended: DSA + core CS subjects.",
            "priority": 4,
        })

    # ── Alert 5: Syllabus Gap Warning ─────────────────────────────────────
    coverage = profile.get("syllabusCoverage", [])
    low_coverage = [
        c for c in coverage
        if float(c.get("coverage_pct") or 0) < 50 and int(c.get("unit_number", 0)) <= 3
    ]
    if low_coverage:
        subj_name = low_coverage[0].get("subject_name", "")
        unit = low_coverage[0].get("unit_title", f"Unit {low_coverage[0].get('unit_number')}")
        alerts.append({
            "type": "info",
            "icon": "📚",
            "category": "syllabus",
            "message": f"{subj_name}: {unit} only {low_coverage[0].get('coverage_pct')}% covered by teacher. Self-study this unit now.",
            "priority": 4,
        })

    # ── Alert 6: Study Streak ─────────────────────────────────────────────
    streak = profile.get("studyStreak", 0)
    if streak == 0:
        alerts.append({
            "type": "nudge",
            "icon": "💡",
            "category": "motivation",
            "message": "No study streak active. Start a 25-minute focused session today to rebuild momentum.",
            "priority": 5,
        })
    elif streak >= 7:
        alerts.append({
            "type": "positive",
            "icon": "🔥",
            "category": "motivation",
            "message": f"{streak}-day study streak! You're in the top consistency band. Keep it up.",
            "priority": 6,
        })

    # Sort by priority and return top 5
    alerts.sort(key=lambda x: x["priority"])
    top_alerts = alerts[:5]

    # ── AI-Generated Morning Brief (NVIDIA NIM / Groq fallback) ─────────────
    ai_brief = None
    try:
        from langchain_openai import ChatOpenAI
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage

        risk_subjects = [s["name"] for s in profile.get("subjects", []) if s.get("status") == "risk"]
        watch_subjects = [s["name"] for s in profile.get("subjects", []) if s.get("status") == "watch"]
        alerts_text = "\n".join(f"- {a['message']}" for a in top_alerts)
        lang_pref = profile.get("langPref", "en")

        BRIEF_SYSTEM = (
            "You are the AI Mentor for a college student in India. "
            "Write a short, warm, personal Morning Mission Control brief (max 60 words). "
            "Tone: like a smart friend who knows their academic data — direct, caring, never generic. "
            "Rules: address student by first name only; lead with the MOST urgent item; "
            "maximum 3 actionable points; end with one short motivational line tied to their "
            "specific situation. If lang is 'ta', respond in Tamil. Otherwise English."
        )

        brief_prompt = (
            f"Student: {profile.get('name', 'Student').split()[0]}\n"
            f"Current CGPA: {profile.get('currentCGPA')} | Exam in: {profile.get('examDays')} days\n"
            f"Risk subjects: {', '.join(risk_subjects) or 'None'}\n"
            f"Watch subjects: {', '.join(watch_subjects) or 'None'}\n"
            f"Today's alerts:\n{alerts_text}\n"
            f"Language preference: {lang_pref}\n\n"
            "Write the morning brief now."
        )

        if settings.nvidia_api_key:
            llm = ChatOpenAI(
                api_key=settings.nvidia_api_key,
                base_url=settings.nvidia_base_url,
                model=settings.nvidia_model,
                temperature=0.7,
                max_tokens=150,
            )
        else:
            llm = ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                temperature=0.7,
                max_tokens=150,
            )

        result = await llm.ainvoke([
            SystemMessage(content=BRIEF_SYSTEM),
            HumanMessage(content=brief_prompt),
        ])
        ai_brief = (result.content or "").strip()

    except Exception as e:
        logger.warning(f"AI brief generation failed (non-fatal): {e}")
        ai_brief = (
            top_alerts[0]["message"] if top_alerts
            else f"Good morning, {profile.get('name', '').split()[0] or 'student'}! Review your schedule and stay on track today."
        )

    # ── Identify Primary and Secondary Actions ────────────────────────────
    # 1. Primary Action: Highest priority critical or warning alert
    primary_action_alert = top_alerts[0] if top_alerts else None
    primary_action = None
    if primary_action_alert:
        primary_action = {
            "title": primary_action_alert["message"],
            "type": primary_action_alert["type"],
            "icon": primary_action_alert["icon"],
            "actionText": "Take Action",
            "link": "/tutor" if primary_action_alert["category"] in ["attendance", "exam", "syllabus"] else "/schedule",
            "context": primary_action_alert.get("subject") or primary_action_alert.get("category"),
        }

    # 2. Secondary Actions: Other alerts (not the primary one)
    secondary_actions = []
    for alert in top_alerts[1:4]: # Take the next 3 alerts
        secondary_actions.append({
            "title": alert["message"],
            "type": alert["type"],
            "icon": alert["icon"],
            "actionText": "Resolve",
            "link": "/chat" if alert["category"] == "assignments" else "/career" if alert["category"] == "placement" else "/tutor",
            "context": alert.get("subject") or alert.get("category"),
        })

    # 3. Momentum Wins: Positive alerts
    momentum_wins = []
    for alert in alerts:
        if alert["type"] == "positive":
            momentum_wins.append(alert["message"])
            
    # Add passing internal exam prediction rule if available
    for subj in profile.get("subjects", []):
         if subj.get("predicted", 0) > 8.0 and subj.get("status") == "safe":
             momentum_wins.append(f"Predicted ~{subj['predicted']} CGPA in {subj.get('name')}. You are excelling!")
             break # Just one momentum win for brevity

    return {
        "student_id": student_id,
        "student_name": profile.get("name"),
        "generated_at": now.isoformat(),
        "exam_days": profile.get("examDays"),
        "ai_brief": ai_brief,
        "briefing": top_alerts,
        "primaryAction": primary_action,
        "secondaryActions": secondary_actions,
        "momentumWins": list(set(momentum_wins))[:2], # max 2 unique wins
        "total_alerts": len(alerts),
        "summary": {
            "critical": sum(1 for a in alerts if a["type"] == "critical"),
            "warning": sum(1 for a in alerts if a["type"] == "warning"),
            "info": sum(1 for a in alerts if a["type"] in ("info", "notice")),
        }
    }


@app.get("/student/{student_id}/min-scores")
async def get_minimum_scores(student_id: str, target_cgpa: float = 7.5):
    """
    Minimum Score Calculator — exact marks needed per subject to hit a CGPA target.
    Pure ERP math. No AI required.
    Formula: min_score = (target_gpa_points - earned_gpa_points) / remaining_credit_weight * 10
    """
    profile = await get_student_profile(student_id)
    subjects = profile.get("subjects", [])

    current_cgpa = profile.get("currentCGPA", 0)
    cgpa_history = profile.get("cgpaHistory", [])

    # Total credits earned so far
    credits_earned = profile.get("total_credits_earned", 0)
    credits_required = profile.get("total_credits_required", 180)

    results = []
    for subj in subjects:
        grade = subj.get("grade", 0)
        credit = subj.get("creditWeight", 3)
        name = subj.get("name", subj.get("code"))
        status = subj.get("status", "safe")

        # Grade points needed in this subject to "help" meet the target
        # Simple model: if current grade < target*0.9, student needs to improve
        grade_gap = max(0, (target_cgpa * 0.9) - grade)

        # What internal test score (out of 50) would push pred grade above 7?
        # Approximation: internal = 50% of total, ESE = 50%
        # If current internal grade contribution is low, calculate min internal score
        current_internal_contribution = grade * 0.5  # approximation
        min_internal = min(50, max(0, round((target_cgpa - grade * 0.5) * 2 + 5, 1)))
        min_ese = min(100, max(0, round((target_cgpa - grade * 0.3) * 3 + 10, 1)))

        results.append({
            "code":           subj.get("code"),
            "name":           name,
            "current_grade":  grade,
            "credit_weight":  credit,
            "status":         status,
            "target_grade":   round(target_cgpa * 0.9, 1),
            "grade_gap":      round(grade_gap, 1),
            "min_internal_marks": min_internal,  # out of 50
            "min_ese_marks":      min_ese,        # out of 100
            "is_achievable":  grade >= target_cgpa - 2.0,
        })

    # Sort: risk first, then watch, then safe
    order = {"risk": 0, "watch": 1, "safe": 2}
    results.sort(key=lambda x: order.get(x["status"], 3))

    return {
        "student_id":      student_id,
        "student_name":    profile.get("name"),
        "current_cgpa":    current_cgpa,
        "target_cgpa":     target_cgpa,
        "gap":             round(target_cgpa - current_cgpa, 2),
        "credits_earned":  credits_earned,
        "credits_required": credits_required,
        "subjects":        results,
        "message": (
            f"To reach CGPA {target_cgpa}, focus on "
            + ", ".join(r["name"] for r in results if r["status"] == "risk")
            or "all subjects are on track"
        ),
    }


# ════════════════════════════════════════════════════════════════════════
# PHASE 7: AI VISUAL TUTOR — Streaming, Syllabus-Aware, Visual Teaching
# Enhanced: full personalization via build_tutor_context; server-side session
# ════════════════════════════════════════════════════════════════════════

# In-memory tutor session store: session_id -> { "turns": [{role, content}], "lesson_summary": str }
# ── FIX: Add locking to prevent race conditions on concurrent access ──
tutor_sessions: dict[str, dict] = {}
tutor_sessions_lock = asyncio.Lock()
tutor_session_last_access: dict[str, datetime] = {}
SESSION_TTL_MINUTES = 60


async def cleanup_stale_sessions():
    """Background task to remove tutor sessions older than TTL. Prevents memory leak."""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        now = datetime.now()
        async with tutor_sessions_lock:
            stale = [
                sid for sid, last_access in tutor_session_last_access.items()
                if (now - last_access).total_seconds() > SESSION_TTL_MINUTES * 60
            ]
            for sid in stale:
                tutor_sessions.pop(sid, None)
                tutor_session_last_access.pop(sid, None)
            if stale:
                logger.info(f"✅ Cleaned up {len(stale)} stale tutor sessions (TTL exceeded)")


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


def _build_step_rules(plan_steps: list, bloom_level: int) -> str:
    """
    Build the step + checkpoint teaching rules section of the system prompt.
    If plan_steps are provided (from the pre-generated lesson plan), use the
    exact step titles and checkpoint positions from the plan.
    Otherwise fall back to the generic 4-6 step rule.
    """
    bloom_depth = (
        'basics and recall' if bloom_level <= 2
        else 'application and analysis' if bloom_level <= 4
        else 'evaluation and creation'
    )

    section_format = """For EVERY step, produce these sections:
   a. [NARRATION] — 2-4 spoken sentences. Use analogies and real-world examples. Be conversational.
      For math/formula topics include LaTeX wrapped in $$...$$ inline.
   b. [DIAGRAM] — A valid Mermaid.js diagram illustrating this step's concept. REQUIRED for every step.
      Use ONLY: flowchart TD, sequenceDiagram, stateDiagram-v2, classDiagram.
      Max 8 nodes. No inline styles or fill colors.
      Example: flowchart TD\\n    A[Concept] --> B[Detail] --> C[Result]
   c. [CODE] (only for CS/algorithm topics): short walkthrough block followed by HIGHLIGHT: and EXPLAIN: lines."""

    if not plan_steps:
        return f"""2. Teach the topic in 4-6 clear STEPS. Each step builds on the previous.
3. {section_format}
4. After STEP 2 and STEP 4, add a [CHECKPOINT] block with: Question, Type: mcq, Options: A)..B)..C)..D).., Correct: X, Explanation.
5. End with a brief summary.
6. Adapt depth to Bloom level {bloom_level}: {bloom_depth}."""

    n = len(plan_steps)
    checkpoint_steps = [s["step_num"] for s in plan_steps if s.get("checkpoint_after")]

    step_list = "\n".join(
        f"   STEP {s['step_num']}: {s.get('title', 'Step ' + str(s['step_num']))}"
        + (" ← add [CHECKPOINT] after this step" if s.get("checkpoint_after") else "")
        for s in plan_steps
    )

    if checkpoint_steps:
        cp_rule = f"4. Add a [CHECKPOINT] block immediately after STEP {' and STEP '.join(str(x) for x in checkpoint_steps)} only. Do NOT add checkpoints after any other steps. Each checkpoint must have: Question, Type: mcq, Options: A)..B)..C)..D).., Correct: X, Explanation."
    else:
        cp_rule = "4. No checkpoints needed for this lesson."

    return f"""2. Teach the topic in exactly {n} STEPS using the pre-planned structure below. Use these exact titles in order:
{step_list}
3. {section_format}
{cp_rule}
5. End with a brief summary.
6. Adapt depth to Bloom level {bloom_level}: {bloom_depth}."""


@app.post("/student/{student_id}/tutor/teach")
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
    language = body.get("language", "en")  # "en" | "ta" | "thanglish"
    lesson_plan_steps = body.get("lesson_plan_steps") or []  # pre-generated plan steps from frontend

    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    # ── FIX: Thread-safe session initialization ──
    async with tutor_sessions_lock:
        if session_id not in tutor_sessions:
            tutor_sessions[session_id] = {"turns": [], "lesson_summary": None}
        tutor_session_last_access[session_id] = datetime.now()

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

    _student_name = profile.get('name', 'Student')

    # Language instruction block — placed at the very top so the LLM commits to it first
    if language == "ta":
        _lang_block = f"""══════════════════════════════════════════
மொழி நிர்பந்தம் (MANDATORY LANGUAGE RULE):
══════════════════════════════════════════
நீ ஒரு தமிழ் ஆசிரியர். எல்லா [NARRATION] பகுதிகளும் தமிழிலேயே இருக்க வேண்டும்.
CRITICAL: Every single [NARRATION] must be written in Tamil script (தமிழ்).
- Technical terms (like "algorithm", "array", "function") can stay in English
- All explanations, examples, analogies MUST be in Tamil
- Greet as: "வணக்கம் {_student_name}! இன்று நாம் {topic} பற்றி படிக்கப் போகிறோம்."
- [DIAGRAM] labels and [CHECKPOINT] questions stay in English
- Writing narrations in English = WRONG. தமிழில் மட்டுமே எழுதவும்.
══════════════════════════════════════════"""
    elif language == "thanglish":
        _lang_block = f"""══════════════════════════════════════════
MANDATORY LANGUAGE RULE — THANGLISH ONLY:
══════════════════════════════════════════
CRITICAL: Every [NARRATION] MUST be written in Thanglish (Tamil words written in English letters).
- You are a friendly Tamil-speaking tutor who naturally mixes Tamil with English technical terms
- Write EXACTLY like how Tamil students talk to each other: natural, casual, warm
- Technical terms stay in English. Everything else in Tamil transliterated.
- Greet as: "Vanakkam {_student_name}! Indha lesson la namma {topic} pathi paarkalam."
- Bad example (DO NOT do this): "In this step, we will learn about graphs."
- Good example: "Dei {_student_name}, ippo namba graph nu enna nu therinjukalam — oru set of nodes irukku, avangala edges connect pannuthu. Real life la Facebook friends list exact ah idhe thaan!"
- Another good example: "Enna kekureenga na, Binary Search la sorted array eduthu middle element ah check pannuva — correct ah irundha found, illa na half ah cut pannuva. Time O(log n) aagum because every step la array half aaguthu!"
- [DIAGRAM] labels and [CHECKPOINT] questions stay in English
- Writing narrations in English = WRONG. Thanglish matum use pannunga.
══════════════════════════════════════════"""
    else:
        _lang_block = ""

    system_prompt = f"""{_lang_block}
You are an expert AI Tutor teaching an engineering student. You know this student's full context; never give a generic lesson. Adapt every step to their Bloom level and mastery. If they have weak topics in this subject, acknowledge and build from there. Be friendly and conversational like a real teacher — not a textbook.

STUDENT CONTEXT:
- Name: {_student_name}
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
1. STEP 1 MUST open with a personal greeting that SPEAKS THE STUDENT'S DETAILS ALOUD:
   - Address them by name: {_student_name}
   - Mention their department ({profile.get('department','')}) and semester ({profile.get('semester','')})
   - Mention their CGPA ({profile.get('currentCGPA','')}) and Bloom level ({bloom_level}/6) naturally
   - Say you've tailored this lesson specifically for them
   - Then introduce the topic "{topic}" and what they'll learn
   - {"தமிழிலேயே கூறவும் — மாணவரின் பெயரையும், துறையையும், CGPA-வையும் தமிழில் கூறவும்." if language == "ta" else "Thanglish la sollunga — student name, dept, CGPA ellam mention pannunga." if language == "thanglish" else ""}
   - Example English: "Hey {_student_name}! You're in {profile.get('department','')} Semester {profile.get('semester','')}, CGPA {profile.get('currentCGPA','')}. I've prepared this lesson at Bloom level {bloom_level} just for you. Today we're diving into {topic}!"
{_build_step_rules(lesson_plan_steps, bloom_level)}
FORMAT YOUR RESPONSE EXACTLY LIKE THIS (repeat for each step):

[STEP 1: Title of Step]
[NARRATION]
Your {"தமிழ்" if language == "ta" else "Thanglish" if language == "thanglish" else "English"} explanation here...

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

            # ── Try Groq first, fall back to NVIDIA NIM ───────────────────────
            full_text = None
            if settings.groq_api_key:
                try:
                    from langchain_groq import ChatGroq
                    llm_groq = ChatGroq(
                        api_key=settings.groq_api_key,
                        model=settings.groq_model,
                        temperature=0.5,
                        max_tokens=4000,
                        request_timeout=30,
                    )
                    result = await llm_groq.ainvoke([
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=f"Teach me: {topic}"),
                    ])
                    full_text = result.content or ""
                    logger.info(f"Groq lesson generated for topic: {topic}")
                except Exception as ge:
                    logger.warning(f"Groq call failed ({ge}), falling back to NVIDIA NIM")
                    full_text = None

            # ── NVIDIA NIM fallback ───────────────────────────────────────────
            if not full_text and settings.nvidia_api_key:
                from langchain_openai import ChatOpenAI
                llm_nvidia = ChatOpenAI(
                    api_key=settings.nvidia_api_key,
                    base_url=settings.nvidia_base_url,
                    model=settings.nvidia_model,
                    temperature=0.5,
                    max_tokens=4000,
                    request_timeout=60,
                )
                result = await llm_nvidia.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"Teach me: {topic}"),
                ])
                full_text = result.content or ""

            # ── Parse structured response into step events ──────────────
            import re
            from agents.teacher import parse_checkpoints_from_lesson

            step_pattern = re.compile(r'\[STEP\s+(\d+):\s*([^\]]+)\]', re.IGNORECASE)
            latex_pattern = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)

            # Per-step patterns (searched within each step's own text slice)
            _narr_re  = re.compile(r'\[NARRATION\]\s*\n(.*?)(?=\[DIAGRAM\]|\[CODE\]|\[CHECKPOINT\]|\Z)', re.DOTALL | re.IGNORECASE)
            _diag_re  = re.compile(r'```mermaid\s*\n(.*?)```', re.DOTALL)
            _code_re  = re.compile(
                r'\[CODE\]\s*\n```(\w+)?\s*\n(.*?)```\s*\nHIGHLIGHT:\s*([^\n]*)\nEXPLAIN:\s*([^\n\[]*)',
                re.DOTALL | re.IGNORECASE,
            )
            _cp_re    = re.compile(
                r'\[CHECKPOINT\].*?Question:\s*(.+?)\n.*?Type:\s*(\w+).*?Options:\s*(.+?)\n.*?Correct:\s*([A-D]).*?Explanation:\s*(.+?)(?=\[STEP|\Z)',
                re.DOTALL | re.IGNORECASE,
            )

            steps = list(step_pattern.finditer(full_text))

            if not steps:
                logger.warning(f"No steps found in lesson for {topic}, using fallback")
                yield f"event: step\ndata: {json.dumps({'step': 1, 'title': topic})}\n\n"
                sentences = re.split(r'(?<=[.!?])\s+', full_text)
                for sent in sentences[:50]:
                    if sent.strip():
                        yield f"event: narration\ndata: {json.dumps({'text': sent.strip()})}\n\n"
                        await asyncio.sleep(0.05)
                yield f"event: done\ndata: {json.dumps({'fallback': True})}\n\n"
                return

            for i, step_match in enumerate(steps):
                step_num   = int(step_match.group(1))
                step_title = step_match.group(2).strip()

                yield f"event: step\ndata: {json.dumps({'step': step_num, 'title': step_title})}\n\n"

                # Slice text belonging to this step only
                step_start = step_match.end()
                step_end   = steps[i + 1].start() if i + 1 < len(steps) else len(full_text)
                step_text  = full_text[step_start:step_end]

                # ── Narration ────────────────────────────────────────────
                narr_match = _narr_re.search(step_text)
                if narr_match:
                    narr_text = narr_match.group(1).strip()
                    latex_matches = latex_pattern.findall(narr_text)
                    for latex in latex_matches:
                        yield f"event: equation\ndata: {json.dumps({'latex': latex.strip(), 'display': 'inline', 'step': step_num})}\n\n"
                    sentences = re.split(r'(?<=[.!?])\s+', narr_text)
                    for sent in sentences:
                        sent = sent.strip()
                        if sent:
                            yield f"event: narration\ndata: {json.dumps({'text': sent})}\n\n"
                            await asyncio.sleep(0.05)

                # ── Diagram (searched within this step's text only) ──────
                diag_match = _diag_re.search(step_text)
                if diag_match:
                    mermaid_code = diag_match.group(1).strip()
                    yield f"event: diagram\ndata: {json.dumps({'mermaid': mermaid_code, 'title': step_title})}\n\n"

                # ── Code walkthrough ─────────────────────────────────────
                code_match = _code_re.search(step_text)
                if code_match:
                    lang        = (code_match.group(1) or 'python').strip()
                    code        = code_match.group(2).strip()
                    highlights  = [int(x.strip()) for x in code_match.group(3).split(',') if x.strip().isdigit()]
                    explanation = code_match.group(4).strip()
                    yield f"event: code_block\ndata: {json.dumps({'language': lang, 'code': code, 'highlight_lines': highlights, 'explanation': explanation, 'step': step_num})}\n\n"

                # ── Checkpoint (searched within this step's text only) ───
                cp_match = _cp_re.search(step_text)
                if cp_match:
                    question = cp_match.group(1).strip()
                    q_type   = cp_match.group(2).strip().lower()
                    options_raw = cp_match.group(3).strip()
                    correct  = cp_match.group(4).strip()
                    explanation = cp_match.group(5).strip()
                    options = re.findall(r'[A-D]\)\s*([^A-D\)]+?)(?=[A-D]\)|$)', options_raw + ' ')
                    cp_data = {
                        "question":    question,
                        "type":        q_type,
                        "options":     [o.strip() for o in options],
                        "correct":     correct,
                        "explanation": explanation,
                        "after_step":  step_num,
                        "step_before": step_num,
                        "step_after":  step_num + 1,
                        "topic":       topic,
                    }
                    yield f"event: checkpoint\ndata: {json.dumps(cp_data)}\n\n"

                await asyncio.sleep(0.1)

            # ── FIX: Thread-safe session update ──
            async with tutor_sessions_lock:
                if session_id in tutor_sessions:
                    tutor_sessions[session_id]["lesson_summary"] = f"Lesson: {topic}, steps 1–{len(steps)}"
                    tutor_sessions[session_id]["last_step"] = len(steps)
                    tutor_session_last_access[session_id] = datetime.now()

            # ── Fire-and-forget: record lesson completion for spaced repetition
            create_tracked_task(
                db.record_lesson_completion(
                    student_id=student_id,
                    subject_code=subject_code,
                    topic=topic,
                    steps_completed=len(steps),
                    bloom_level=bloom_level,
                ),
                name=f"record_lesson_{student_id}_{topic}"
            )

            yield f"event: done\ndata: {json.dumps({'total_steps': len(steps)})}\n\n"

        except Exception as e:
            logger.error(f"🔴 Tutor teach error: {e}", exc_info=True)
            # ── FIX: Always send done event even on error ──
            yield f"event: error\ndata: {json.dumps({'error': 'Lesson generation failed', 'step': 'unknown'})}\n\n"
            yield f"event: done\ndata: {json.dumps({'error': True})}\n\n"

    return StreamingResponse(
        stream_lesson(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/student/{student_id}/tutor/session/clear")
async def tutor_session_clear(student_id: str, body: dict):
    """Clear a tutor session (e.g. for 'New conversation'). Body: { session_id }"""
    sid = body.get("session_id")
    # ── FIX: Thread-safe session deletion ──
    async with tutor_sessions_lock:
        if sid and sid in tutor_sessions:
            del tutor_sessions[sid]
            tutor_session_last_access.pop(sid, None)
    return {"ok": True}


@app.post("/student/{student_id}/tutor/ask")
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
    language = (body.get("language") or "en").strip().lower()

    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    # ── FIX: Thread-safe session initialization and retrieval ──
    session_turns = []
    if session_id:
        async with tutor_sessions_lock:
            if session_id not in tutor_sessions:
                tutor_sessions[session_id] = {"turns": [], "lesson_summary": None}
            session_turns = tutor_sessions[session_id].get("turns", [])[-10:]
            tutor_session_last_access[session_id] = datetime.now()
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

    # ── FIX: Thread-safe lesson summary retrieval ──
    lesson_summary = ""
    if session_id:
        async with tutor_sessions_lock:
            if session_id in tutor_sessions:
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

    _student_name = profile.get('name', 'Student')
    if language == "ta":
        _lang_block = """══════════════════════════════════════════
MANDATORY LANGUAGE RULE — TAMIL ONLY:
══════════════════════════════════════════
CRITICAL: You MUST answer ENTIRELY in Tamil script (தமிழ்).
- Every sentence in your answer must be in Tamil.
- Do NOT write English sentences, even for technical terms. Write the term in English but explain it in Tamil.
- Wrong: "In this step, we learn about arrays."
- Correct: "இந்த படிநிலையில், arrays என்றால் என்ன என்று பார்க்கலாம்."
══════════════════════════════════════════"""
    elif language == "thanglish":
        _lang_block = f"""══════════════════════════════════════════
MANDATORY LANGUAGE RULE — THANGLISH ONLY:
══════════════════════════════════════════
CRITICAL: You MUST answer ENTIRELY in Thanglish (Tamil written in English letters).
- Every sentence must be Tamil spoken, written in English letters.
- Do NOT write full English sentences. Tamil words, English script.
- Bad: "In this step, we will learn about graphs."
- Good: "Dei {_student_name}, ippo namba graph pathi pesalam. Oru node-ku rendu edge irukku nu therinjukkom, appo enna aagum?"
══════════════════════════════════════════"""
    else:
        _lang_block = ""

    system_prompt = f"""{_lang_block}
You are the AI Tutor for {_student_name} — a {profile.get('department','')} student in Semester {profile.get('semester','')} with CGPA {profile.get('currentCGPA','')}. You know this student personally. Address them by name. Adapt every answer to their Bloom level {bloom}/6 and {style} learning style. Reference their mastery gaps when relevant. Never give a generic answer — always make it feel personal.{session_context}

STUDENT CONTEXT:
- Name: {_student_name}
- Department: {profile.get('department','CSBS')} · Semester: {profile.get('semester','')} · CGPA: {profile.get('currentCGPA','—')}
- Bloom level: {bloom}/6. Learning style: {style}
{f'- Mastery: {mastery_block}' if mastery_block else ''}

SYLLABUS (current subject units):
{syllabus_text}
{rag_section}
Answer their follow-up question in 2–4 short paragraphs. Be conversational and personal — use their name.
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
        # Try Groq first, fall back to NVIDIA NIM
        if settings.groq_api_key:
            try:
                from langchain_groq import ChatGroq
                llm = ChatGroq(
                    api_key=settings.groq_api_key,
                    model=settings.groq_model,
                    temperature=0.4,
                    max_tokens=800,
                    request_timeout=30,
                )
            except Exception as ge:
                logger.warning(f"Groq init failed for tutor_ask, trying NVIDIA: {ge}")
                llm = None
        if llm is None and settings.nvidia_api_key:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                api_key=settings.nvidia_api_key,
                base_url=settings.nvidia_base_url,
                model=settings.nvidia_model,
                temperature=0.4,
                max_tokens=800,
                request_timeout=60,
            )

        result = await llm.ainvoke(lc_messages)
        text = (result.content or "").strip()
        mermaid_block = None
        if "```mermaid" in text:
            import re
            m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
            if m:
                mermaid_block = m.group(1).strip()

        # ── FIX: Thread-safe turns update and confusion detection ──
        if session_id:
            async with tutor_sessions_lock:
                if session_id in tutor_sessions:
                    tutor_sessions[session_id]["turns"].append({"role": "user", "content": question})
                    tutor_sessions[session_id]["turns"].append({"role": "assistant", "content": text})
                    tutor_session_last_access[session_id] = datetime.now()
                    session_turns = tutor_sessions[session_id].get("turns", [])
                else:
                    session_turns = []
        else:
            session_turns = []

        # ── Confusion detection (fire-and-forget) ────────────────────────
        if session_turns:
            from agents.teacher import detect_confusion
            if detect_confusion(session_turns, topic, threshold=3):
                create_tracked_task(
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

        # ── FIX: Thread-safe turns update ──
        if session_id:
            async with tutor_sessions_lock:
                if session_id in tutor_sessions:
                    tutor_sessions[session_id]["turns"].append({"role": "user", "content": question})
                    tutor_sessions[session_id]["turns"].append({"role": "assistant", "content": text})
                    tutor_session_last_access[session_id] = datetime.now()
        return {"answer": text, "mermaid": mermaid_block}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tutor ask error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════════════════
# V1 TEACHING CORE — Lesson Plan, Checkpoint, Due Topics, Session State
# ════════════════════════════════════════════════════════════════════════

@app.get("/student/{student_id}/tutor/lesson-plan")
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
            db_id,
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


@app.post("/student/{student_id}/tutor/checkpoint")
async def evaluate_checkpoint(student_id: str, body: dict):
    """
    Evaluate a student's checkpoint answer (free-text or MCQ).
    MCQ answers are evaluated client-side; this endpoint handles short-answer evaluation.
    Also persists the result to bloom_progress + Learning DNA.

    Body: { session_id, question, student_answer, correct_answer, subject_code, topic,
            question_type: 'mcq'|'short', correct_index?: int, selected_index?: int }
    Returns: { correct, score, feedback, misconceptions, unlock_next }
    """
    from agents.teacher import evaluate_checkpoint_answer

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


@app.post("/student/{student_id}/tutor/generate-quiz")
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


@app.get("/student/{student_id}/tutor/due-topics")
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


@app.get("/student/{student_id}/tutor/session/{session_id}/state")
async def get_session_state(student_id: str, session_id: str):
    """
    Return the current tutor session state for resume functionality.
    Frontend can use this to restore lesson progress after page refresh.
    """
    # ── FIX: Thread-safe session state retrieval ──
    async with tutor_sessions_lock:
        if session_id not in tutor_sessions:
            return {
                "session_id":        session_id,
                "exists":            False,
                "last_step":         0,
                "checkpoints_passed": [],
                "lesson_summary":    None,
            }
        sess = tutor_sessions[session_id]
        tutor_session_last_access[session_id] = datetime.now()
        return {
            "session_id":         session_id,
            "exists":             True,
            "last_step":          sess.get("last_step", 0),
            "checkpoints_passed": sess.get("checkpoints_passed", []),
            "lesson_summary":     sess.get("lesson_summary"),
            "turn_count":         len(sess.get("turns", [])),
        }



# ════════════════════════════════════════════════════════════════════════
# V3 VOICE TEACHING — Nova Sonic TTS + Transcribe STT
# ════════════════════════════════════════════════════════════════════════

@app.get("/student/{student_id}/tutor/voice/settings")
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


@app.post("/student/{student_id}/tutor/voice/speak")
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


@app.post("/student/{student_id}/tutor/voice/transcribe")
async def tutor_voice_transcribe(student_id: str, request: Request):
    """
    Speech-to-Text transcription endpoint.
    Accepts raw audio bytes (audio/webm or audio/wav) as request body.
    Returns: { transcript, confidence?, language }
    Falls back to empty transcript if AWS creds are not set (browser STT handles it).
    """
    # Server-side STT is stubbed (browser handles STT via Web Speech API)
    return {"transcript": "", "language": "en-US", "provider": "browser-stt"}


@app.post("/student/{student_id}/tutor/clarify")
async def tutor_clarify(
    student_id: str,
    audio: UploadFile = File(...),
    subject_code: str = Form(""),
    topic: str = Form(""),
    language: str = Form("en"),
    session_id: str = Form(""),
    lesson_context: str = Form(""),
):
    """
    Voice doubt clarification during a live lesson.

    1. Transcribes doubt via Sarvam Saaras V3 (Groq Whisper fallback).
    2. Generates a personalised clarification using full student profile.
    3. Returns {transcript, clarification, audio_base64} — Sarvam Bulbul V2 WAV.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from utils.stt import transcribe_audio
    import utils.tts as tts_util
    import base64 as b64mod

    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"

    # ── Step 1: Transcribe via Saaras V3 (Groq Whisper fallback) ─────────────
    try:
        transcript = await transcribe_audio(audio_bytes, mime_type, language)
    except Exception as e:
        logger.error(f"STT failed for clarify: {e}")
        raise HTTPException(status_code=500, detail=f"Could not transcribe audio: {e}")

    if not transcript:
        return {"transcript": "", "clarification": "", "audio_base64": None}

    # ── Step 2: Load student profile for personalisation ─────────────────────
    ctx = await build_tutor_context(student_id, subject_code or "GEN", topic or "")
    profile = (ctx or {}).get("profile") or {}
    learning_dna = (ctx or {}).get("learning_dna") or {}

    student_name = profile.get("name") or student_id
    dept = profile.get("department") or profile.get("dept") or "Engineering"
    year = profile.get("year") or profile.get("current_year") or ""
    cgpa = profile.get("cgpa") or profile.get("gpa") or ""
    bloom = (ctx or {}).get("bloom_level") or 2
    style = learning_dna.get("preferred_style") or "visual"
    mastery_weak = (ctx or {}).get("mastery_weak") or ""
    mastery_strong = (ctx or {}).get("mastery_strong") or ""
    accuracy = None
    total_q = learning_dna.get("total_questions") or 0
    correct = learning_dna.get("correct_answers") or 0
    if total_q:
        accuracy = round(100 * correct / total_q, 1)

    # Build student info block
    student_block = f"Student: {student_name}, {dept}{f', Year {year}' if year else ''}{f', CGPA {cgpa}' if cgpa else ''}."
    bloom_labels = {1: "remember facts", 2: "understand concepts", 3: "apply knowledge",
                    4: "analyse and compare", 5: "evaluate critically", 6: "create/design"}
    bloom_block = f"Current learning level: Bloom {bloom} ({bloom_labels.get(bloom, 'understand')})."
    mastery_block = ""
    if mastery_weak:
        mastery_block += f"Weak areas: {mastery_weak}. "
    if mastery_strong:
        mastery_block += f"Strong areas: {mastery_strong}. "
    if accuracy is not None:
        mastery_block += f"Quiz accuracy: {accuracy}%."
    context_block = f"\nLesson context: {lesson_context}" if lesson_context else ""

    # ── Step 3: Language instruction ──────────────────────────────────────────
    if language == "ta":
        lang_rule = """══════════════════════════════════════════
MANDATORY: Answer ENTIRELY in Tamil script (தமிழ்).
Technical terms stay in English; all explanations in Tamil.
══════════════════════════════════════════"""
    elif language == "thanglish":
        lang_rule = f"""══════════════════════════════════════════
MANDATORY: Answer ENTIRELY in Thanglish (Tamil spoken, English letters).
Bad: "In this step, we learn about arrays."
Good: "Correct daa {student_name}! Array nu oru collection of elements — oru row-la values store panrom."
══════════════════════════════════════════"""
    else:
        lang_rule = ""

    system = f"""{lang_rule}
You are a warm, expert AI tutor in the middle of teaching a lesson.
The student just paused to ask a voice doubt. Answer it and send them back to the lesson.

{student_block}
{bloom_block}
{mastery_block}
Subject: {subject_code or 'Engineering'}. Topic: {topic or 'current topic'}.{context_block}

Rules:
- Address the student by first name ({student_name.split()[0]}).
- Answer ONLY the doubt — do not re-teach the entire topic.
- Pitch your explanation to Bloom level {bloom} (not too advanced, not too simple).
- Be concise: 3-5 sentences maximum.
- Be conversational, warm, and encouraging — like a friendly senior student.
- If helpful, give one quick analogy or micro-example.
- End with a brief encouragement and say you're continuing the lesson."""

    user_msg = f"Student's doubt (voice): {transcript}"

    try:
        llm, _ = get_llm(temperature=0.4, max_tokens=350)
        result = await llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=user_msg),
        ])
        clarification = (result.content or "").strip()
    except Exception as e:
        logger.error(f"LLM clarification failed: {e}")
        raise HTTPException(status_code=500, detail="Could not generate clarification")

    # ── Step 4: Sarvam Bulbul V2 TTS (always try — all 3 languages) ──────────
    audio_base64 = None
    if settings.sarvam_api_key:
        try:
            wav_bytes = await tts_util.synthesize(clarification, language)
            audio_base64 = b64mod.b64encode(wav_bytes).decode("utf-8")
        except Exception as e:
            logger.warning(f"Sarvam TTS failed for clarify ({language}): {e}")

    return {
        "transcript": transcript,
        "clarification": clarification,
        "audio_base64": audio_base64,
        "language": language,
    }


@app.post("/student/{student_id}/tutor/tts")
async def tutor_tts(student_id: str, body: dict):
    """
    Text-to-Speech via Sarvam Bulbul V2 — all languages (en, ta, thanglish).
    Body: { text, language }
    Returns: audio/wav bytes, or 204 so client falls back to browser TTS.
    """
    import utils.tts as tts_util
    from fastapi.responses import Response

    text = (body.get("text") or "").strip()
    language = (body.get("language") or "en").strip().lower()

    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    if not settings.sarvam_api_key:
        logger.warning("Sarvam TTS skipped — SARVAM_API_KEY not set")
        return Response(status_code=204)

    try:
        wav_bytes = await tts_util.synthesize(text, language)
        logger.debug(f"Sarvam TTS OK student={student_id} lang={language} chars={len(text)} wav={len(wav_bytes)}B")
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        logger.warning(f"Sarvam TTS failed (student={student_id}, lang={language}): {e}")
        return Response(status_code=204)



# ════════════════════════════════════════════════════════════════════════
# V4 MEMORY + INTELLIGENCE — SM-2 Spaced Repetition + LangChain RAG
# ════════════════════════════════════════════════════════════════════════

@app.post("/student/{student_id}/tutor/checkpoint/record")
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



@app.get("/student/{student_id}/tutor/due-topics/smart")
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


@app.get("/student/{student_id}/tutor/weak-areas")
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


@app.get("/student/{student_id}/tutor/progress")
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


@app.post("/student/{student_id}/tutor/rag-query")
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


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — V5 MULTI-AGENT TUTOR ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/student/{student_id}/tutor/deep-evaluate")
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


@app.post("/student/{student_id}/tutor/doubt-resolve")
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



# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — V6 GAMIFICATION + CLASSROOM EXPERIENCE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/student/{student_id}/xp")
async def get_student_xp(student_id: str):
    """
    Get full XP summary: total_xp, level, streak, level_progress,
    xp_to_next_level, badges [], recent_ledger [].
    Used by Progress dashboard and Tutor XP ring.
    """
    from gamification import get_gamification_agent

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    gami = await get_gamification_agent()
    summary = await gami.get_xp_summary(student["db_id"])
    summary["student_id"] = student_id
    return summary


@app.post("/student/{student_id}/xp/award")
async def award_student_xp(student_id: str, body: dict):
    """
    Award XP for an action. Checks badge conditions.
    Body: { action, amount?, metadata? }
    Returns: { total_xp, level, xp_gained, streak_days, level_progress, badges_earned }
    Valid actions: lesson_complete, checkpoint_pass, exam_complete, exam_perfect
    """
    from gamification import get_gamification_agent

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    action   = (body.get("action") or "lesson_complete").strip()
    amount   = body.get("amount")
    metadata = body.get("metadata") or {}

    gami = await get_gamification_agent()
    result = await gami.award_xp(
        student_db_id=student["db_id"],
        action=action,
        amount=int(amount) if amount is not None else None,
        metadata=metadata,
    )
    return result


@app.get("/student/{student_id}/tutor/timeline")
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


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5 — V7 KNOWLEDGE ENGINE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

# ── 5A: RAG / Syllabus Search ────────────────────────────────────────────────

@app.get("/rag/search")
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


@app.post("/admin/rag/ingest-syllabus")
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


# ── 5B: PDF / Document Upload ────────────────────────────────────────────────

@app.post("/student/{student_id}/documents/upload")
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


@app.get("/student/{student_id}/documents")
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


@app.delete("/student/{student_id}/documents/{doc_id}")
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


# ── 5C: PYQ Analyzer ────────────────────────────────────────────────────────

@app.post("/student/{student_id}/pyq/analyze")
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


@app.get("/student/{student_id}/pyq/history")
async def get_pyq_history(student_id: str, limit: int = 10):
    """List past PYQ analyses for a student."""
    from pyq_analyzer import get_pyq_history as _get_history
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    pool = await get_pool()
    return {"analyses": await _get_history(pool, student["db_id"], limit)}


# ── 5D: Concept Graph ─────────────────────────────────────────────────────

@app.post("/student/{student_id}/concept-graph")
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


@app.get("/student/{student_id}/concept-graph/{subject_code}")
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


# ── 5E: Auto Notes Generator ─────────────────────────────────────────────

@app.post("/student/{student_id}/notes/generate")
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


@app.get("/student/{student_id}/notes")
async def list_student_notes(student_id: str, limit: int = 20):
    """List all saved notes for a student (summary only)."""
    from notes_generator import list_notes
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    pool = await get_pool()
    return {"notes": await list_notes(pool, student["db_id"], limit)}


@app.get("/student/{student_id}/notes/{note_id}")
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


@app.delete("/student/{student_id}/notes/{note_id}")
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


# ── Entry ──────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6 — V8–V10 ADVANCED INTELLIGENCE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

# ── 6A/6B: Hesitation-Aware Checkpoint Evaluation ───────────────────────────

@app.post("/student/{student_id}/tutor/evaluate-adaptive")
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


# ── 6E: Skill Gap Analyzer ───────────────────────────────────────────────────

@app.get("/student/{student_id}/skill-gap")
async def get_skill_gap(student_id: str, domain: str = None):
    """
    Analyze skill gaps between student mastery and career domain requirements.
    Query param: domain (optional, auto-detected from career profile if not given)
    """
    from skill_gap import analyze_skill_gap
    from agents.career import compute_career_profile
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Resolve domain: use provided or detect from career profile
    primary_domain = domain
    if not primary_domain:
        try:
            profile = await db.get_student_full_profile(student_id)
            career  = compute_career_profile(profile or {})
            primary_domain = career.get("primary_domain", "Software Developer")
        except Exception:
            primary_domain = "Software Developer"

    # Get subject names for context
    subject_names = []
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT subject_code FROM student_learning_memory WHERE student_db_id = $1",
                student["db_id"],
            )
        subject_names = [r["subject_code"] for r in rows]
    except Exception:
        pass

    pool = await get_pool()
    gap_report = await analyze_skill_gap(
        student_db_id=student["db_id"],
        primary_domain=primary_domain,
        pool=pool,
        subject_names=subject_names,
    )
    return gap_report


# ── 6F: Study Roadmap ─────────────────────────────────────────────────────────

@app.post("/student/{student_id}/roadmap/generate")
async def generate_study_roadmap(student_id: str, body: dict):
    """
    Generate a personalized week-by-week study roadmap.
    Body: { subjects: [str], weeks?: int, exam_date?: str }
    """
    from roadmap_generator import generate_roadmap, save_roadmap
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    subjects  = body.get("subjects") or []
    weeks     = min(int(body.get("weeks", 4)), 12)
    exam_date = body.get("exam_date")

    pool = await get_pool()

    roadmap = await generate_roadmap(
        student_db_id=student["db_id"],
        subjects=subjects,
        weeks=weeks,
        exam_date=exam_date,
        pool=pool,
    )

    # Cache to DB
    try:
        roadmap_id = await save_roadmap(pool, student["db_id"], roadmap, subjects, weeks, exam_date)
        roadmap["roadmap_id"] = roadmap_id
    except Exception as e:
        logger.warning(f"Roadmap save error: {e}")

    return roadmap


@app.get("/student/{student_id}/roadmap")
async def get_student_roadmap(student_id: str):
    """Fetch the most recent study roadmap for a student."""
    from roadmap_generator import get_latest_roadmap
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    pool    = await get_pool()
    roadmap = await get_latest_roadmap(pool, student["db_id"])

    if not roadmap:
        raise HTTPException(
            status_code=404,
            detail="No roadmap found. Generate one via POST /roadmap/generate first."
        )
    return roadmap


# ── 6G: Resume + Interview Coach ─────────────────────────────────────────────

@app.post("/student/{student_id}/career/resume-review")
async def review_resume(student_id: str, body: dict):
    """
    AI-powered resume review with ATS scoring.
    Body: { resume_text }
    Returns: { ats_score, strengths, gaps, improvements, keyword_suggestions }
    """
    import re as _re
    from groq import AsyncGroq

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    resume_text = (body.get("resume_text") or "").strip()
    if not resume_text:
        raise HTTPException(status_code=400, detail="'resume_text' is required")

    # Get career domain for context
    domain = "Software Developer"
    try:
        from agents.career import compute_career_profile
        profile = await db.get_student_full_profile(student_id)
        career_data = compute_career_profile(profile or {})
        domain = career_data.get("primary_domain", domain)
    except Exception:
        pass

    prompt = f"""You are an expert ATS-aware resume reviewer for Indian engineering students.

Target Career Domain: {domain}
Resume Text:
{resume_text[:4000]}

Perform a comprehensive ATS review. Return ONLY valid JSON:
{{
  "ats_score": <0-100, ATS compatibility score>,
  "overall_rating": "poor|fair|good|excellent",
  "summary": "<2-sentence overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "gaps": ["<gap 1>", "<gap 2>"],
  "improvements": [
    {{
      "section": "<Resume section>",
      "issue": "<what's wrong>",
      "fix": "<exact fix suggestion>"
    }}
  ],
  "keyword_suggestions": ["<keyword to add>", ...],
  "action_score": <0-100, how action-verb driven the bullets are>,
  "quantification_score": <0-100, how well achievements are quantified>
}}

Scoring criteria:
- ATS keywords present for {domain}
- Clear contact info and formatting
- Action verbs (Developed, Built, Designed, Implemented)
- Quantified achievements (%, numbers, scale)
- Relevant projects/internships
- Education section completeness
"""

    try:
        groq_client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an ATS expert. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()
        match = _re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group() if match else raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {str(e)}")

    result["domain"] = domain
    return result


@app.post("/student/{student_id}/career/interview-prep")
async def generate_interview_prep(student_id: str, body: dict):
    """
    Generate domain-specific interview Q&A.
    Body: { domain?: str, topics?: [str], count?: int }
    Returns: { domain, questions: [{ q, a, tips, difficulty }] }
    """
    import re as _re
    from groq import AsyncGroq

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    domain = (body.get("domain") or "").strip()
    topics = body.get("topics") or []
    count  = min(int(body.get("count", 10)), 15)

    if not domain:
        try:
            from agents.career import compute_career_profile
            profile = await db.get_student_full_profile(student_id)
            career_data = compute_career_profile(profile or {})
            domain = career_data.get("primary_domain", "Software Developer")
        except Exception:
            domain = "Software Developer"

    topics_str = f"Focus topics: {', '.join(topics)}" if topics else ""

    prompt = f"""You are an expert technical interview coach for Indian engineering students.
Career Domain: {domain}
{topics_str}

Generate {count} interview questions with expert answers.

Return ONLY valid JSON:
{{
  "questions": [
    {{
      "q":           "<interview question>",
      "a":           "<comprehensive answer>",
      "tips":        "<1-2 tips for answering this well in an interview>",
      "difficulty":  "easy|medium|hard",
      "type":        "technical|behavioral|system_design|coding_logic"
    }}
  ]
}}

Rules:
- Mix: 60% technical, 20% behavioral, 20% project/system design
- Answers: 3-5 sentences, concrete and structured
- Include STAR method hints for behavioral questions
- Reflect actual questions asked by Indian product companies in 2025
"""

    try:
        groq_client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an interview coach. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
        )
        raw = resp.choices[0].message.content.strip()
        match = _re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group() if match else raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Interview prep failed: {str(e)}")

    result["domain"] = domain
    return result


@app.get("/student/{student_id}/career/roadmap-timeline")
async def get_career_roadmap_timeline(student_id: str, domain: str = None):
    """Month-by-month career readiness timeline based on semester + CGPA."""
    from agents.career import build_roadmap_timeline, compute_career_profile

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    profile = await get_student_profile(student_id)
    timeline = build_roadmap_timeline(profile, domain)
    intel    = compute_career_profile(profile)

    return {
        "domain":   domain or intel["primary_domain"],
        "semester": intel["semester"],
        "cgpa":     intel["cgpa"],
        "timeline": timeline,
    }


@app.post("/student/{student_id}/career/project-ideas")
async def generate_career_project_ideas(student_id: str, body: dict = None):
    """Generate 3 personalised project ideas based on career domain."""
    import re as _re
    from groq import AsyncGroq
    from agents.career import compute_career_profile, DOMAIN_SKILLS, CERT_MAP

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    body    = body or {}
    profile = await get_student_profile(student_id)
    intel   = compute_career_profile(profile)
    domain  = (body.get("domain") or "").strip() or intel["primary_domain"]
    skills  = DOMAIN_SKILLS.get(domain, ["Python", "REST APIs"])
    cgpa    = intel["cgpa"]
    semester = intel["semester"]

    prompt = f"""You are a senior software engineer mentoring an Indian CS/CSBS student.

Student profile:
- Target domain: {domain}
- CGPA: {cgpa} | Semester: {semester}
- Key skills to build: {', '.join(skills[:5])}

Generate exactly 3 project ideas that:
1. Are realistic to build in 2-4 weeks as a student
2. Use the domain's key tech stack
3. Are impressive enough for a resume/GitHub
4. Progress in difficulty (beginner → intermediate → advanced)

Return ONLY valid JSON:
{{
  "projects": [
    {{
      "title": "<specific project name>",
      "description": "<2-sentence description of what it does and why it's impressive>",
      "tech_stack": ["<tech1>", "<tech2>", "<tech3>"],
      "skills_built": ["<skill1>", "<skill2>"],
      "difficulty": "beginner|intermediate|advanced",
      "weeks": <1-4>,
      "github_hint": "<repo name like: ml-resume-parser>"
    }}
  ]
}}

Make ideas SPECIFIC to {domain} — not generic todo apps."""

    try:
        groq_client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a senior engineer. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=1500,
        )
        raw = resp.choices[0].message.content.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        match = _re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group() if match else raw)
    except Exception as e:
        result = {
            "projects": [
                {
                    "title": f"{domain} Starter Project",
                    "description": f"A beginner project showcasing core {domain} skills. Build and deploy a working prototype.",
                    "tech_stack": skills[:3],
                    "skills_built": skills[:2],
                    "difficulty": "beginner",
                    "weeks": 2,
                    "github_hint": f"{domain.lower().replace('/', '-').replace(' ', '-')}-starter",
                }
            ]
        }

    result["domain"] = domain
    return result


@app.get("/student/{student_id}/career/digest")
async def get_career_digest_endpoint(student_id: str):
    """Weekly personalised career digest — focus area, next skill, LeetCode topic, key actions."""
    from agents.career import get_career_digest

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    profile = await get_student_profile(student_id)
    return get_career_digest(profile)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7 — V8, V9, V10 Completion Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# ── 7F: AI Live Debugger ──────────────────────────────────────────────────────
from problems_generator import debug_code, generate_problems

class DebugRequest(BaseModel):
    code: str
    stderr: str = ""
    language: str = "python"

@app.post("/debug/analyze")
async def analyze_code_error(body: DebugRequest):
    """AI-powered code debugger — explains error and suggests fix."""
    result = await debug_code(body.code, body.stderr, body.language)
    return result


# ── 7F: Interactive Problem Builder ──────────────────────────────────────────
class ProblemGenRequest(BaseModel):
    subject_code: str
    topic: str
    count: int = 5
    mode: str = "mixed"          # mcq | short | coding | mixed | olympiad | hackathon
    difficulty: str = "medium"

@app.post("/student/{student_id}/problems/generate")
async def generate_student_problems(student_id: str, body: ProblemGenRequest):
    """Generate practice problems for a topic and save to problem bank."""
    # Get subject name
    subject_name = body.subject_code
    try:
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT name FROM subjects WHERE code = $1", body.subject_code
            )
            if row:
                subject_name = row["name"]
    except Exception:
        pass

    problems = await generate_problems(
        subject_name=subject_name,
        topic=body.topic,
        count=min(body.count, 10),
        mode=body.mode,
        difficulty=body.difficulty,
    )

    # Save to student_problem_bank
    saved_ids = []
    try:
        async with db.pool.acquire() as conn:
            for p in problems:
                row = await conn.fetchrow(
                    """INSERT INTO student_problem_bank
                       (student_id, subject_code, topic, type, question, options,
                        correct_index, correct_answer, hint, bloom_level, difficulty,
                        tags, explanation, mode)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                       RETURNING id""",
                    student_id, body.subject_code, body.topic,
                    p["type"], p["question"],
                    json.dumps(p.get("options", [])),
                    p.get("correct_index", 0), p.get("correct_answer", ""),
                    p.get("hint", ""), p.get("bloom_level", 3),
                    p.get("difficulty", body.difficulty),
                    json.dumps(p.get("tags", [])),
                    p.get("explanation", ""), body.mode
                )
                saved_ids.append(str(row["id"]))
    except Exception as e:
        logging.warning(f"[problems] Could not save to DB: {e}")

    return {"problems": problems, "saved_count": len(saved_ids)}


@app.get("/student/{student_id}/problems")
async def get_student_problems(
    student_id: str,
    subject_code: str = None,
    topic: str = None,
    limit: int = 20,
):
    """Get student's saved problem bank."""
    try:
        async with db.pool.acquire() as conn:
            query = """SELECT id, subject_code, topic, type, question, options,
                              correct_index, correct_answer, hint, bloom_level,
                              difficulty, tags, explanation, mode, attempted,
                              correct, created_at
                       FROM student_problem_bank
                       WHERE student_id = $1"""
            params = [student_id]
            if subject_code:
                params.append(subject_code)
                query += f" AND subject_code = ${len(params)}"
            if topic:
                params.append(topic)
                query += f" AND topic = ${len(params)}"
            query += f" ORDER BY created_at DESC LIMIT {limit}"
            rows = await conn.fetch(query, *params)
            problems = [dict(r) for r in rows]
            for p in problems:
                p["options"] = json.loads(p["options"]) if isinstance(p["options"], str) else p["options"]
                p["tags"]    = json.loads(p["tags"]) if isinstance(p["tags"], str) else p["tags"]
            return {"problems": problems}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/student/{student_id}/problems/{problem_id}/attempt")
async def attempt_problem(student_id: str, problem_id: str, body: dict):
    """Record a problem attempt (correct/incorrect)."""
    is_correct = body.get("is_correct", False)
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                """UPDATE student_problem_bank
                   SET attempted = true, correct = $1, attempted_at = NOW()
                   WHERE id = $2 AND student_id = $3""",
                is_correct, problem_id, student_id
            )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/student/{student_id}/problems/{problem_id}")
async def delete_problem(student_id: str, problem_id: str):
    """Delete a problem from student's bank."""
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM student_problem_bank WHERE id = $1 AND student_id = $2",
                problem_id, student_id
            )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 7C: Competitive Leaderboard ───────────────────────────────────────────────
@app.get("/leaderboard")
async def get_leaderboard(subject_code: str = None, limit: int = 10):
    """Get top students ranked by XP (optionally filtered by subject)."""
    try:
        async with db.pool.acquire() as conn:
            if subject_code:
                rows = await conn.fetch(
                    """SELECT sx.student_id,
                              COALESCE(sp.name, sx.student_id) as name,
                              COALESCE(sp.section, '') as section,
                              sx.total_xp, sx.level, sx.streak_days,
                              RANK() OVER (ORDER BY sx.total_xp DESC) as rank
                       FROM student_xp sx
                       LEFT JOIN student_profiles sp ON sx.student_id = sp.college_id
                       ORDER BY sx.total_xp DESC LIMIT $1""",
                    limit
                )
            else:
                rows = await conn.fetch(
                    """SELECT sx.student_id,
                              COALESCE(sp.name, sx.student_id) as name,
                              COALESCE(sp.section, '') as section,
                              sx.total_xp, sx.level, sx.streak_days,
                              RANK() OVER (ORDER BY sx.total_xp DESC) as rank
                       FROM student_xp sx
                       LEFT JOIN student_profiles sp ON sx.student_id = sp.college_id
                       ORDER BY sx.total_xp DESC LIMIT $1""",
                    limit
                )
            return {"leaderboard": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 7D: Session Break Log ────────────────────────────────────────────────────
@app.post("/student/{student_id}/session/break-log")
async def log_break(student_id: str, body: dict):
    """Log when a student took a study break (for analytics)."""
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO session_break_log (student_id, break_at, session_minutes)
                   VALUES ($1, NOW(), $2)
                   ON CONFLICT DO NOTHING""",
                student_id, body.get("session_minutes", 45)
            )
        return {"ok": True}
    except Exception:
        return {"ok": True}  # Non-critical, never fail



# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8 — V2 / V6 / V8 / V9 Completion Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# ── V2A: Diagram History ──────────────────────────────────────────────────────

@app.post("/student/{student_id}/tutor/session/diagrams")
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


@app.get("/student/{student_id}/tutor/session/diagrams")
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


# ── V6A: Session Replay ────────────────────────────────────────────────────────

@app.post("/student/{student_id}/tutor/session/event")
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


@app.get("/student/{student_id}/tutor/session/{session_id}/events")
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


# ── V6B: Peer Learning Study Rooms ────────────────────────────────────────────

import secrets as _secrets


@app.post("/student/{student_id}/study-room/create")
async def create_study_room(student_id: str, body: dict):
    """Create a new study room. Returns room_code to share with peers."""
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    room_code    = _secrets.token_urlsafe(6).upper()[:8]
    topic        = (body.get("topic") or "General Study").strip()
    subject_code = (body.get("subject_code") or "").strip()

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO study_rooms (room_code, creator_id, topic, subject_code)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (room_code) DO NOTHING
                """,
                room_code, student_id, topic, subject_code,
            )
        return {"room_code": room_code, "topic": topic, "subject_code": subject_code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/study-room/{room_code}")
async def get_study_room(room_code: str):
    """Get info and recent messages for a study room."""
    from db import get_pool

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            room = await conn.fetchrow(
                "SELECT room_code, creator_id, topic, subject_code, created_at FROM study_rooms WHERE room_code = $1",
                room_code.upper(),
            )
            if not room:
                raise HTTPException(status_code=404, detail="Study room not found")
            messages = await conn.fetch(
                """
                SELECT id, sender_id, sender_name, message, sent_at
                FROM study_room_messages
                WHERE room_code = $1
                ORDER BY sent_at ASC LIMIT 100
                """,
                room_code.upper(),
            )
        return {
            "room": dict(room),
            "messages": [dict(m) for m in messages],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/study-room/{room_code}/message")
async def post_room_message(room_code: str, body: dict):
    """Post a message to a study room (simple polling-based)."""
    from db import get_pool

    sender_id   = (body.get("sender_id") or "").strip()
    sender_name = (body.get("sender_name") or "Student").strip()
    message     = (body.get("message") or "").strip()

    if not sender_id or not message:
        raise HTTPException(status_code=400, detail="'sender_id' and 'message' are required")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            room = await conn.fetchval("SELECT room_code FROM study_rooms WHERE room_code = $1", room_code.upper())
            if not room:
                raise HTTPException(status_code=404, detail="Study room not found")
            row = await conn.fetchrow(
                """
                INSERT INTO study_room_messages (room_code, sender_id, sender_name, message)
                VALUES ($1, $2, $3, $4)
                RETURNING id, sent_at
                """,
                room_code.upper(), sender_id, sender_name[:100], message[:2000],
            )
            # Update last_activity
            await conn.execute(
                "UPDATE study_rooms SET last_activity = NOW() WHERE room_code = $1", room_code.upper()
            )
        return {"message_id": row["id"], "sent_at": str(row["sent_at"])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── V8A: Attention Heartbeat ──────────────────────────────────────────────────

@app.post("/student/{student_id}/analytics/attention")
async def record_attention_heartbeat(student_id: str, body: dict):
    """
    Receive a visibility heartbeat from the frontend.
    Body: { is_visible: bool, session_id?: str }
    """
    from db import get_pool

    student = await db.get_student_by_college_id(student_id)
    if not student:
        return {"ok": True}  # silently ignore

    is_visible = bool(body.get("is_visible", True))
    session_id = body.get("session_id", "")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO session_attention_log (student_db_id, session_id, is_visible)
                VALUES ($1, $2, $3)
                """,
                student["db_id"], session_id or "", is_visible,
            )
    except Exception as e:
        logger.debug(f"Attention heartbeat save error (non-critical): {e}")

    return {"ok": True}


@app.get("/student/{student_id}/analytics/burnout")
async def get_burnout_analysis(student_id: str):
    """
    Analyze recent session patterns and break logs to detect burnout risk.
    Returns: { burnout_score, risk_level, signals, recommendation }
    """
    from db import get_pool
    from adaptive_engine import detect_burnout

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Get last 7 days of break logs
            break_rows = await conn.fetch(
                """
                SELECT session_minutes, break_at
                FROM session_break_log
                WHERE student_id = $1
                  AND break_at > NOW() - INTERVAL '7 days'
                ORDER BY break_at DESC
                """,
                student_id,
            )
            # Get attention data
            attention_rows = await conn.fetch(
                """
                SELECT is_visible, heartbeat_at
                FROM session_attention_log
                WHERE student_db_id = $1
                  AND heartbeat_at > NOW() - INTERVAL '1 day'
                ORDER BY heartbeat_at ASC
                """,
                student["db_id"],
            )
    except Exception:
        break_rows = []
        attention_rows = []

    break_log = [
        {"session_minutes": r["session_minutes"], "break_at": str(r["break_at"])}
        for r in break_rows
    ]
    attention_log = [
        {"is_visible": r["is_visible"], "ts": str(r["heartbeat_at"])}
        for r in attention_rows
    ]

    return detect_burnout(break_log, attention_log)


@app.post("/student/{student_id}/analytics/silence-alert")
async def handle_silence_alert(student_id: str, body: dict):
    """
    Called by frontend when student hasn't interacted for > 45s during lesson.
    Returns: { confusion_suspected, suggestion, directive }
    """
    from adaptive_engine import check_silence_confusion

    student = await db.get_student_by_college_id(student_id)
    if not student:
        return {"confusion_suspected": False, "suggestion": "Continue studying!"}

    silence_ms = int(body.get("silence_ms", 45000))
    topic      = body.get("topic", "")
    step       = int(body.get("step_num", 0))

    return check_silence_confusion(silence_ms, topic, step)


@app.get("/student/{student_id}/analytics/attention-score")
async def get_attention_score(student_id: str):
    """
    Compute attention score from recent heartbeats.
    Returns: { score, hidden_pct, total_heartbeats, recommendation }
    """
    from db import get_pool
    from adaptive_engine import estimate_attention_score

    student = await db.get_student_by_college_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT is_visible, heartbeat_at
                FROM session_attention_log
                WHERE student_db_id = $1
                  AND heartbeat_at > NOW() - INTERVAL '2 hours'
                ORDER BY heartbeat_at ASC
                """,
                student["db_id"],
            )
        heartbeats = [{"is_visible": r["is_visible"]} for r in rows]
        return estimate_attention_score(heartbeats)
    except Exception as e:
        return {"score": 1.0, "hidden_pct": 0, "total_heartbeats": 0, "recommendation": "Keep studying!"}


# ── V9: Study Mode Profiles ───────────────────────────────────────────────────

STUDY_MODE_PROFILES = {
    "concept": {
        "mode": "concept",
        "label": "Concept Deep-Dive",
        "icon": "🧠",
        "description": "Learn every detail thoroughly with full explanations and examples.",
        "bloom_action": "maintain",
        "bloom_level": 2,
        "focus": ["understand", "analyze"],
    },
    "fast_track": {
        "mode": "fast_track",
        "label": "Fast-Track",
        "icon": "⚡",
        "description": "Move quickly — skip scaffolding, advance Bloom level rapidly.",
        "bloom_action": "advance",
        "bloom_level": 4,
        "focus": ["apply", "analyze"],
    },
    "exam": {
        "mode": "exam",
        "label": "Exam Mode",
        "icon": "📝",
        "description": "Focus on key points, shortcuts, and exam-ready summaries.",
        "bloom_action": "maintain",
        "bloom_level": 3,
        "focus": ["remember", "understand", "apply"],
    },
    "slow_deep": {
        "mode": "slow_deep",
        "label": "Slow & Deep",
        "icon": "🐢",
        "description": "Mastery-first learning — never advance until fully understood.",
        "bloom_action": "slow",
        "bloom_level": 1,
        "focus": ["remember", "understand"],
    },
    "olympiad": {
        "mode": "olympiad",
        "label": "Olympiad",
        "icon": "🏆",
        "description": "Challenge-level problems, edge cases, and deep theory.",
        "bloom_action": "advance",
        "bloom_level": 6,
        "focus": ["evaluate", "create"],
    },
    "hackathon": {
        "mode": "hackathon",
        "label": "Hackathon Prep",
        "icon": "🚀",
        "description": "Practical, project-oriented learning with real-world application.",
        "bloom_action": "advance",
        "bloom_level": 5,
        "focus": ["apply", "create"],
    },
    "interview": {
        "mode": "interview",
        "label": "Interview Prep",
        "icon": "💼",
        "description": "Technical Q&A, system design, and behavioral questions.",
        "bloom_action": "maintain",
        "bloom_level": 4,
        "focus": ["apply", "analyze", "evaluate"],
    },
}


@app.get("/tutor/study-modes")
async def get_study_modes():
    """List all available study mode profiles."""
    return {"modes": list(STUDY_MODE_PROFILES.values())}


@app.get("/tutor/study-modes/{mode}")
async def get_study_mode(mode: str):
    """Get a specific study mode profile."""
    profile = STUDY_MODE_PROFILES.get(mode)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Unknown mode '{mode}'. Valid: {list(STUDY_MODE_PROFILES)}")
    return profile


# ── V3: Multi-language teach hint (applied via lesson-plan + teach endpoints) ─
# (Already supported via lang param in teach body + prompt — this endpoint
# provides frontend with available languages)

@app.get("/tutor/supported-languages")
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


# ── Learning Analytics Endpoints ───────────────────────────────────────────────
# ── Commitment Contracts Endpoints ─────────────────────────────────────────────
@app.post("/student/{student_id}/commitment/create")
async def create_commitment(student_id: str, body: dict):
    """Create a new study commitment."""
    from commitment_contracts import get_commitment_manager

    manager = get_commitment_manager(student_id)
    contract = await manager.create_contract(
        commitment=body.get("commitment", ""),
        target_date=body.get("target_date", ""),
        frequency=body.get("frequency", "daily"),
        goal_metric=body.get("goal_metric", ""),
    )
    return {"success": True, "contract": contract.to_dict()}


@app.post("/student/{student_id}/commitment/check-in")
async def check_in_commitment(student_id: str, body: dict):
    """Record progress on a commitment."""
    from commitment_contracts import get_commitment_manager

    manager = get_commitment_manager(student_id)
    result = await manager.check_in_on_commitment(
        commitment_text=body.get("commitment", ""),
        progress=int(body.get("progress", 0)),
        notes=body.get("notes", ""),
    )
    return {"success": result is not None, "check_in": result}


@app.get("/student/{student_id}/commitment/active")
async def get_active_commitments(student_id: str):
    """Get all active commitments for a student."""
    from commitment_contracts import get_commitment_manager

    manager = get_commitment_manager(student_id)
    await manager.load_contracts()
    active = await manager.get_active_contracts()
    return {"active_commitments": [c.to_dict() for c in active]}


@app.get("/student/{student_id}/commitment/summary")
async def get_commitment_summary(student_id: str):
    """Get commitment summary for a student."""
    from commitment_contracts import get_commitment_manager

    manager = get_commitment_manager(student_id)
    await manager.load_contracts()
    return manager.get_summary()


# ── Peer Insights Endpoints ────────────────────────────────────────────────────
@app.get("/student/{student_id}/peer/comparison")
async def get_peer_comparison(student_id: str):
    """Get peer comparison data for a student."""
    from peer_insights import PeerInsightsAnalyzer

    student_profile = await get_student_profile(student_id)
    if not student_profile:
        raise HTTPException(status_code=404, detail="Student not found")

    analyzer = PeerInsightsAnalyzer(student_id)
    return await analyzer.get_peer_comparison(student_profile)


@app.get("/student/{student_id}/peer/suggestions")
async def get_peer_suggestions(student_id: str):
    """Get personalized suggestions based on peer comparison."""
    from peer_insights import PeerInsightsAnalyzer, PeerInsightsSuggestions

    student_profile = await get_student_profile(student_id)
    if not student_profile:
        raise HTTPException(status_code=404, detail="Student not found")

    analyzer = PeerInsightsAnalyzer(student_id)
    peer_comparison = await analyzer.get_peer_comparison(student_profile)
    suggestions = await PeerInsightsSuggestions.suggest_next_steps(student_profile, peer_comparison)

    return {
        "student_id": student_id,
        "suggestions": suggestions,
        "peer_comparison_summary": peer_comparison.get("summary", {}),
    }


@app.get("/student/{student_id}/learning/metrics")
async def get_learning_metrics(student_id: str):
    """Get aggregated learning metrics for a student."""
    from learning_analytics import get_student_learning_metrics
    return await get_student_learning_metrics(student_id)


@app.get("/session/{session_id}/learning/summary")
async def get_session_learning_summary(session_id: str):
    """Get learning summary for a specific session."""
    from learning_analytics import get_session_analytics
    analytics = get_session_analytics(session_id)
    return analytics.get_summary()


# ── Cache Management Endpoints ──────────────────────────────────────────────────
@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics (admin only)."""
    from cache_layer import get_cache_stats
    return await get_cache_stats()


@app.post("/cache/clear")
async def clear_cache():
    """Clear all cache entries (admin only)."""
    from cache_layer import clear_all_cache
    success = await clear_all_cache()
    return {"success": success, "message": "Cache cleared" if success else "Cache clear failed"}


@app.post("/cache/invalidate/{student_id}")
async def invalidate_student_cache(student_id: str):
    """Invalidate all cache for a specific student (admin only)."""
    success = await invalidate_cache(student_id)
    return {"success": success, "message": f"Cache invalidated for {student_id}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.agent_service_host,
        port=settings.agent_service_port,
        reload=settings.env == "development",
        log_level=settings.log_level.lower(),
    )
