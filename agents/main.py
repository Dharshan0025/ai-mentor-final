"""
AI-Mentor Agent Service — FastAPI Entry Point
All agent orchestration routes live here.
Run: uvicorn main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
import logging
import asyncio
import uuid
from datetime import datetime

from config import settings
from schemas import (
    ChatRequest, ChatResponse, HealthResponse, AgentId
)
from orchestrator import get_orchestrator
from db import db, get_pool, close_pool
from scheduler import get_scheduler, run_scan_now

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
    try:
        scheduler.start()
        logger.info("Proactive scheduler started (attendance scan at 18:00 IST)")
    except Exception as e:
        logger.warning(f"Scheduler failed to start: {e}")

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
    llm_ready = bool(settings.groq_api_key) or bool(settings.aws_bearer_token_bedrock)

    return HealthResponse(
        status="ok",
        version="0.2.0",
        agents_ready=agents_ready,
        db_connected=_db_connected,
        llm_ready=llm_ready,
    )


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



@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main orchestrated chat endpoint.
    Routes to academic/prediction/emotional/learning/schedule agents based on intent.
    Phase 2: synchronous response. Phase 3+: SSE streaming.
    """
    logger.info(f"Chat request | session={request.session_id} | student={request.student_id}")

    student_profile = await get_student_profile(request.student_id)

    # Build initial state for LangGraph
    initial_state = {
        "message":         request.message,
        "session_id":      request.session_id,
        "student_id":      request.student_id,
        "lang":            request.lang.value,
        "history":         [msg.model_dump() for msg in request.history],
        "student_profile": student_profile,
        # Agent outputs (all None initially)
        "intent":              "",
        "agents_to_invoke":    [],
        "academic_output":     None,
        "prediction_output":   None,
        "emotional_output":    None,
        "learning_output":     None,
        "schedule_output":     None,
        "career_output":       None,
        "rag_context":         None,
        "sentiment_score":     0.0,
        "final_response":      "",
        "primary_agent":       "academic",
        "citations":           [],
        "tokens_used":         0,
        "model_used":          "",
    }

    try:
        orchestrator = get_orchestrator()
        final_state = await orchestrator.ainvoke(initial_state)

        # ── Fire-and-forget sentiment write-back ──────────────────────────
        # Extract score from state (emotional_node always sets this)
        sentiment_score = final_state.get("sentiment_score")
        if sentiment_score is not None and _db_connected:
            asyncio.create_task(
                db.append_sentiment_point(
                    student_id=request.student_id,
                    score=sentiment_score,
                    message_snippet=request.message[:120],
                )
            )

        return ChatResponse(
            session_id=request.session_id,
            agent=AgentId(final_state.get("primary_agent", "academic")),
            content=final_state.get("final_response", "I couldn't process that. Please try again."),
            citations=final_state.get("citations", []),
            tokens_used=final_state.get("tokens_used", 0),
            model_used=final_state.get("model_used", ""),
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Agent service temporarily unavailable")


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
    Scenario simulator — run compute_predicted_cgpa() with improvement deltas.

    Body:
      { attendance_delta: int, assignment_delta: int, study_hours_delta: float }

    Returns:
      {
        baseline_cgpa, baseline_range,
        simulated_cgpa, simulated_range,
        cgpa_delta,
        subjects: [{ name, current, simulated, delta, status }]
      }
    """
    from agents.prediction import compute_predicted_cgpa
    import copy

    profile = await get_student_profile(student_id)

    improvement = {
        "attendance_delta":   float(body.get("attendance_delta", 0)),
        "assignment_delta":   float(body.get("assignment_delta", 0)),
        "study_hours_delta":  float(body.get("study_hours_delta", 0)),
    }

    # Baseline (no improvement)
    baseline_profile = copy.deepcopy(profile)
    baseline = compute_predicted_cgpa(baseline_profile)

    # Simulated (with improvement deltas)
    sim_profile = copy.deepcopy(profile)
    sim = compute_predicted_cgpa(sim_profile, improvement=improvement)

    # Build per-subject diff
    subject_diffs = []
    for b_subj, s_subj in zip(baseline_profile.get("subjects", []), sim_profile.get("subjects", [])):
        before = b_subj.get("predicted", b_subj.get("grade", 0))
        after  = s_subj.get("predicted", b_subj.get("grade", 0))
        subject_diffs.append({
            "name":      b_subj["name"],
            "current":   b_subj.get("grade", 0),
            "before":    round(before, 1),
            "after":     round(after, 1),
            "delta":     round(after - before, 2),
            "status":    s_subj.get("status", b_subj.get("status", "safe")),
        })

    return {
        "student_id":       student_id,
        "baseline_cgpa":    baseline["cgpa"],
        "baseline_range":   baseline["range"],
        "simulated_cgpa":   sim["cgpa"],
        "simulated_range":  sim["range"],
        "cgpa_delta":       round(sim["cgpa"] - baseline["cgpa"], 3),
        "subjects":         subject_diffs,
        "improvement":      improvement,
    }


@app.get("/student/{student_id}/predictions")
async def get_predictions(student_id: str):
    """
    Generate AI predictions for the student.
    Uses the deterministic CGPA calculator + Gemini narrative.
    """
    from agents.prediction import compute_predicted_cgpa
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage

    profile = await get_student_profile(student_id)
    result = compute_predicted_cgpa(profile)
    subjects = profile.get("subjects", [])

    # Build prediction response
    subject_predictions = []
    for s in subjects:
        risk_prob = 0.0
        if s.get("status") == "risk":
            risk_prob = 0.7
        elif s.get("status") == "watch":
            risk_prob = 0.3

        subject_predictions.append({
            "code": s.get("code"),
            "name": s.get("name"),
            "current_grade": s.get("grade"),
            "predicted_grade": s.get("predicted"),
            "attendance": s.get("attendance"),
            "credit_weight": s.get("creditWeight", 3),
            "status": s.get("status"),
            "arrear_probability": risk_prob,
            "key_drivers": _get_risk_drivers(s),
        })

    return {
        "student_id": student_id,
        "predicted_cgpa": result["cgpa"],
        "cgpa_range": result["range"],
        "confidence": 0.78,
        "subjects": subject_predictions,
        "narrative": f"Based on {profile.get('semester')} semesters of ERP data, your predicted CGPA is {result['cgpa']} (range: {result['range'][0]}–{result['range'][1]}). Focus on {', '.join(s.get('name','') for s in subjects if s.get('status') == 'risk')} to protect your CGPA.",
        "generated_at": datetime.utcnow().isoformat(),
    }


@app.get("/student/{student_id}/schedule")
async def get_schedule(student_id: str):
    """Generate a personalized study schedule for the student."""
    from agents.schedule import generate_week_schedule
    from datetime import datetime

    profile = await get_student_profile(student_id)
    week = generate_week_schedule(profile)

    subjects = profile.get("subjects", [])
    risk_subjects = [s for s in subjects if s.get("status") == "risk"]
    total_slots = sum(len(d["slots"]) for d in week)
    risk_slots  = sum(1 for d in week for sl in d["slots"] if sl["type"] == "risk")

    return {
        "student_id": student_id,
        "week": week,
        "total_study_hours": round(sum(sl["duration_min"] for d in week for sl in d["slots"]) / 60, 1),
        "risk_subject_hours": round(risk_slots * 1.5, 1),
        "generated_at": datetime.utcnow().isoformat(),
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

        while True:
            if await request.is_disconnected():
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
            except Exception as e:
                logger.warning(f"SSE alert stream error: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

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

    # ── AI-Generated Morning Brief ────────────────────────────────────────
    # Claude (Amazon Bedrock) synthesizes real ERP alerts into a conversational brief.
    ai_brief = None
    try:
        import boto3

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

        # Build boto3 client — use bearer token if available, else IAM keys
        bedrock_kwargs: dict = {"region_name": settings.aws_region}
        bearer = settings.aws_bearer_token_bedrock or settings.bedrock_api_key or ""
        if bearer:
            # boto3 picks up AWS_BEARER_TOKEN_BEDROCK from env automatically
            import os
            os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", bearer)
        else:
            bedrock_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            bedrock_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key


        client = boto3.client("bedrock-runtime", **bedrock_kwargs)

        response = client.converse(
            modelId=settings.bedrock_model_id,
            system=[{"text": BRIEF_SYSTEM}],
            messages=[{"role": "user", "content": [{"text": brief_prompt}]}],
            inferenceConfig={"maxTokens": 150, "temperature": 0.7},
        )
        ai_brief = response["output"]["message"]["content"][0]["text"].strip()

    except Exception as e:
        logger.warning(f"AI brief generation failed (non-fatal): {e}")
        ai_brief = (
            top_alerts[0]["message"] if top_alerts
            else f"Good morning, {profile.get('name', '').split()[0] or 'student'}! Review your schedule and stay on track today."
        )

    return {
        "student_id": student_id,
        "student_name": profile.get("name"),
        "generated_at": now.isoformat(),
        "exam_days": profile.get("examDays"),
        "ai_brief": ai_brief,
        "briefing": top_alerts,
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

# In-memory tutor session store.
# Shape:
#   session_id -> {
#     "turns": [{role, content}],   # Q&A history (existing)
#     "lesson_summary": str | None, # brief summary (existing)
#     "lesson_plan": LessonPlan | None,  # Phase 6: structured plan
#     "current_concept_index": int,      # Phase 7: which concept we're on
#     "topic": str,                      # current topic
#     "subject_code": str,               # current subject
#     "interrupted": bool,               # True if last action was an interrupt
#   }
tutor_sessions: dict[str, dict] = {}


def _new_session() -> dict:
    """Factory for a fresh tutor session — all keys present, fully backward-compatible."""
    return {
        # Existing (Phase 1-5)
        "turns": [],
        "lesson_summary": None,
        # Phase 6-8
        "lesson_plan": None,
        "current_concept_index": 0,
        "topic": "",
        "subject_code": "",
        "interrupted": False,
        # Phase 6B — Interactive Teaching
        "current_phase": "teaching",      # teaching | waiting_answer | evaluating
        "last_question": "",
        "expected_points": [],
        "attempt_count": 0,               # resets per concept
        "explanation_level": "moderate",  # simple | moderate | advanced
        "concepts_mastered": [],          # list of concept indices mastered
        "concepts_failed": [],            # indices that needed re-explain
        # Phase 10 — Visual Teaching
        "last_diagram": None,             # last DiagramResult dict
        "diagram_history": [],            # list of { concept_index, mermaid_code, visual_type }
        # Phase 11 — Voice Teaching
        "voice_mode": False,
        "voice_status": "idle",           # idle | listening | thinking | speaking
        "last_transcript": "",
        "speaking": False,
        "interrupt_requested": False,
    }

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

    # Phase 12 - Long-Term Mentor Memory
    learning_summary = {}
    if db_id:
        try:
            learning_summary = await get_learning_summary(db_id, subject_code)
        except Exception as e:
            logger.error(f"Failed to fetch learning summary: {e}")

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
        "learning_summary": learning_summary,
    }


# ════════════════════════════════════════════════════════════════════════
# PHASE 6–8: TRUE TEACHING ENGINE
# teach/start → plan lesson + stream concept 1
# teach/next  → advance to next concept (optionally evaluate student answer)
# interrupt   → answer doubt, preserve lesson position, signal resume
# ════════════════════════════════════════════════════════════════════════

from teacher_brain import (
    plan_lesson,
    build_concept_system_prompt,
    build_reexplain_prompt,
    build_interrupt_system_prompt,
    get_teacher_llm,
    evaluate_student_answer,
    adjust_explanation_level,
)
from visual_engine import generate_mermaid_diagram, validate_mermaid
from voice_engine import NovaSonicBridge, build_voice_system_prompt, VoiceEvent
from memory_agent import (
    update_learning_memory,
    record_study_session,
    get_learning_summary,
    generate_study_plan,
    get_progress_data,
    get_dashboard_data
)
from voice_engine import NovaSonicBridge, build_voice_system_prompt, VoiceEvent

# Active voice sessions: session_id → NovaSonicBridge instance
_voice_bridges: dict[str, NovaSonicBridge] = {}


async def _stream_concept_step(
    concept,
    ctx: dict,
    step_num: int,
    total_steps: int,
    session_id: str,
    explanation_level: str = "moderate",
    prev_concept_title: str = "",
):
    """
    Internal SSE generator for one concept step.
    Emits: step → narration → diagram? → diagram_explanation? → checkpoint → done_concept
    Uses Visual Engine for intelligent diagram generation.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    import re

    is_last = step_num == total_steps

    # ════ VISUAL PLANNING: decide if this concept needs a diagram ═══════════
    visual_plan = None
    if concept.needs_diagram:
        try:
            visual_plan = await generate_visual_plan(concept, ctx)
        except Exception as e:
            logger.warning(f"Visual plan failed: {e}")
            visual_plan = {
                "visual_required": concept.needs_diagram,
                "visual_type": "flowchart",
                "description": f"Visual representation of {concept.title}",
            }

    system_prompt = build_concept_system_prompt(
        concept, ctx, is_last,
        explanation_level=explanation_level,
        prev_concept_title=prev_concept_title,
    )
    llm = get_teacher_llm(temperature=0.45, max_tokens=1200)

    # ── Emit step header ──────────────────────────────────────────────────────────
    yield f"event: step\ndata: {json.dumps({'step': step_num, 'title': concept.title})}\n\n"

    try:
        result = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Teach concept {step_num}: {concept.title}"),
        ])
        full_text = (result.content or "").strip()
    except Exception as e:
        logger.error(f"Concept stream LLM failed: {e}")
        full_text = (
            f"[NARRATION]\n{concept.explanation}\n\n"
            f"For example: {concept.example}\n\n"
            f"[CHECKPOINT]\n{concept.checkpoint_question}"
        )

    # ── Parse narration block ────────────────────────────────────────────────────
    narr_match = re.search(r"\[NARRATION\]\s*\n(.*?)(?=\[DIAGRAM\]|\[CHECKPOINT\]|\Z)", full_text, re.DOTALL | re.IGNORECASE)
    if narr_match:
        narr_text = narr_match.group(1).strip()
        sentences = re.split(r'(?<=[.!?])\s+', narr_text)
        for sent in sentences:
            sent = sent.strip()
            if sent:
                yield f"event: narration\ndata: {json.dumps({'text': sent})}\n\n"
                await asyncio.sleep(0.04)
    else:
        yield f"event: narration\ndata: {json.dumps({'text': concept.explanation})}\n\n"
        await asyncio.sleep(0.04)

    # ── Diagram: use Visual Engine if visual_plan says required ─────────────
    use_visual_engine = visual_plan and visual_plan.get("visual_required", False)

    if use_visual_engine:
        # Generate via dedicated visual engine
        try:
            diagram_result = await generate_mermaid_diagram(
                topic=ctx.get("topic", ""),
                concept_title=concept.title,
                visual_type=visual_plan["visual_type"],
                description=visual_plan["description"],
                ctx=ctx,
            )
            yield f"event: diagram\ndata: {json.dumps({'mermaid': diagram_result.mermaid_code, 'title': concept.title, 'visual_type': diagram_result.visual_type})}\n\n"

            # Emit diagram explanation (teacher walks through the diagram)
            if diagram_result.explanation:
                yield f"event: diagram_explanation\ndata: {json.dumps({'text': diagram_result.explanation})}\n\n"

            # Store in session diagram history
            sess = tutor_sessions.get(session_id)
            if sess is not None:
                sess["last_diagram"] = {
                    "mermaid_code": diagram_result.mermaid_code,
                    "visual_type": diagram_result.visual_type,
                    "concept_title": concept.title,
                }
                diag_history = sess.get("diagram_history", [])
                diag_history.append({
                    "concept_index": concept.index,
                    "mermaid_code": diagram_result.mermaid_code,
                    "visual_type": diagram_result.visual_type,
                    "concept_title": concept.title,
                })
                sess["diagram_history"] = diag_history

        except Exception as e:
            logger.warning(f"Visual engine diagram failed: {e}. Falling back to LLM output.")
            # Fallback: try to use diagram from LLM output
            diag_match = re.search(r"```mermaid\s*\n(.*?)```", full_text, re.DOTALL)
            if diag_match:
                mermaid_code = diag_match.group(1).strip()
                yield f"event: diagram\ndata: {json.dumps({'mermaid': mermaid_code, 'title': concept.title})}\n\n"
    elif concept.needs_diagram:
        # Fallback: parse diagram from LLM output directly
        diag_match = re.search(r"```mermaid\s*\n(.*?)```", full_text, re.DOTALL)
        if diag_match:
            mermaid_code = diag_match.group(1).strip()
            yield f"event: diagram\ndata: {json.dumps({'mermaid': mermaid_code, 'title': concept.title})}\n\n"

    # ── Emit checkpoint question ────────────────────────────────────────────
    # If visual engine produced a diagram question, use that; else use concept's
    checkpoint_q = concept.checkpoint_question
    if use_visual_engine and diagram_result and diagram_result.diagram_question:
        checkpoint_q = diagram_result.diagram_question

    yield f"event: checkpoint\ndata: {json.dumps({'question': checkpoint_q})}\n\n"

    # ── Emit concept done ───────────────────────────────────────────────────
    has_more = not is_last
    payload = {
        "concept_index": concept.index,
        "has_more": has_more,
        "had_diagram": bool(use_visual_engine),
    }
    if has_more:
        payload["next_title"] = ""
    yield f"event: done_concept\ndata: {json.dumps(payload)}\n\n"


@app.post("/student/{student_id}/tutor/teach/start")
async def tutor_teach_start(student_id: str, body: dict, request: Request):
    """
    Phase 6–7: Start a structured lesson.

    1. Builds student context (profile, DNA, syllabus, mastery).
    2. Calls teacher_brain.plan_lesson() → structured LessonPlan (3–5 concepts).
    3. Stores plan in tutor_sessions.
    4. Streams the FIRST concept via SSE.

    Body: { subject_code, topic, session_id? }

    SSE events:
      session_id   → { session_id }
      lesson_plan  → { total_concepts, topic, difficulty_level, teaching_style, concept_titles }
      step         → { step, title }
      narration    → { text }
      diagram      → { mermaid, title }   (if concept needs visual)
      checkpoint   → { question }
      done_concept → { concept_index, has_more, next_title? }
    """
    subject_code = (body.get("subject_code") or "").strip()
    topic = (body.get("topic") or "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())

    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    # Initialize or reuse session
    if session_id not in tutor_sessions:
        tutor_sessions[session_id] = _new_session()
    sess = tutor_sessions[session_id]

    ctx = await build_tutor_context(student_id, subject_code, topic)
    if not ctx:
        raise HTTPException(status_code=404, detail="Student not found")

    async def stream():
        # Emit session ID first so frontend can store it
        yield f"event: session_id\ndata: {json.dumps({'session_id': session_id})}\n\n"

        # ── Plan the lesson ───────────────────────────────────────────────
        try:
            lp = await plan_lesson(student_id, subject_code, topic, ctx)
        except Exception as e:
            logger.error(f"plan_lesson failed: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': 'Could not create lesson plan'})}\n\n"
            return

        # Persist lesson plan in session
        sess["lesson_plan"] = lp
        sess["current_concept_index"] = 0
        sess["topic"] = topic
        sess["subject_code"] = subject_code
        sess["lesson_summary"] = f"Lesson on '{topic}' — {lp.total_concepts} concepts"
        sess["interrupted"] = False
        sess["current_phase"] = "teaching"
        sess["attempt_count"] = 0
        sess["explanation_level"] = adjust_explanation_level(sess)
        sess["concepts_mastered"] = []
        sess["concepts_failed"] = []

        # Emit lesson plan summary
        yield f"event: lesson_plan\ndata: {json.dumps(lp.to_summary_dict())}\n\n"

        # ── Stream concept 0 ──────────────────────────────────────────────────────────
        concept = lp.concepts[0]
        level = sess.get("explanation_level", "moderate")
        async for chunk in _stream_concept_step(
            concept, ctx, step_num=1, total_steps=lp.total_concepts,
            session_id=session_id, explanation_level=level,
        ):
            yield chunk

        sess["current_phase"] = "waiting_answer"
        yield f"event: done\ndata: {json.dumps({'total_concepts': lp.total_concepts})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/student/{student_id}/tutor/teach/next")
async def tutor_teach_next(student_id: str, body: dict, request: Request):
    """
    Phase 6B: Interactive teach/next — Evaluate → Decide → Advance or Re-explain.

    Flow:
      1. If student_answer provided → evaluate via evaluate_student_answer()
      2. If understood → mark concept mastered, advance to next concept
      3. If NOT understood & attempts < 2 → re-explain same concept simpler
      4. If NOT understood & attempts >= 2 → acknowledge struggle, advance anyway

    Body: { session_id, student_answer?: string }

    SSE events:
      evaluation    → { score, understood, feedback }  (if answer provided)
      reexplain     → { text }                        (if re-explaining)
      acknowledge   → { text }                        (if advancing after evaluation)
      step, narration, diagram, checkpoint, done_concept
      lesson_complete → { topic, total_concepts, message, mastered, struggled }
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    session_id = (body.get("session_id") or "").strip()
    student_answer = (body.get("student_answer") or "").strip()

    if not session_id or session_id not in tutor_sessions:
        raise HTTPException(status_code=400, detail="Valid session_id required. Call /tutor/teach/start first.")

    sess = tutor_sessions[session_id]
    lp = sess.get("lesson_plan")

    if not lp:
        raise HTTPException(status_code=400, detail="No active lesson plan. Call /tutor/teach/start first.")

    topic = sess.get("topic", "")
    subject_code = sess.get("subject_code", "")

    ctx = await build_tutor_context(student_id, subject_code, topic)
    if not ctx:
        raise HTTPException(status_code=404, detail="Student not found")

    async def stream():
        import re as _re
        current_idx = sess.get("current_concept_index", 0)
        current_concept = lp.concepts[current_idx] if current_idx < lp.total_concepts else None
        attempt_count = sess.get("attempt_count", 0)

        should_advance = True  # default: move to next concept

        # ════ PHASE 1: EVALUATE STUDENT ANSWER ═════════════════════════════════════
        if student_answer and current_concept:
            sess["current_phase"] = "evaluating"

            eval_result = await evaluate_student_answer(student_answer, current_concept, ctx)

            # Emit evaluation result
            yield f"event: evaluation\ndata: {json.dumps({'score': eval_result.score, 'understood': eval_result.understood, 'feedback': eval_result.feedback})}\n\n"

            # Phase 12: Log to long-term memory
            try:
                profile = ctx.get("profile", {})
                db_id = profile.get("db_id")
                if db_id:
                    await update_learning_memory(
                        student_id=db_id,
                        subject_code=ctx.get("subject_code", ""),
                        topic=ctx.get("topic", ""),
                        concept=current_concept.title,
                        score=eval_result.score
                    )
            except Exception as e:
                logger.error(f"Learning memory update failed: {e}")

            # Log into session
            sess["turns"].append({"role": "user", "content": student_answer})
            sess["turns"].append({"role": "assistant", "content": eval_result.feedback})

            if eval_result.understood:
                # ── Student understood → mark mastered, advance ────────────
                mastered = sess.get("concepts_mastered", [])
                if current_idx not in mastered:
                    mastered.append(current_idx)
                    sess["concepts_mastered"] = mastered
                sess["attempt_count"] = 0
                should_advance = True
            else:
                # ── Student did NOT understand ────────────────────────────
                if attempt_count < 2:
                    # Re-explain same concept with different approach
                    sess["attempt_count"] = attempt_count + 1
                    sess["current_phase"] = "teaching"

                    reexplain_sys = build_reexplain_prompt(current_concept, ctx, attempt_count)
                    llm = get_teacher_llm(temperature=0.5, max_tokens=800)

                    try:
                        re_result = await llm.ainvoke([
                            SystemMessage(content=reexplain_sys),
                            HumanMessage(content=f"Re-explain: {current_concept.title}"),
                        ])
                        re_text = (re_result.content or "").strip()
                    except Exception as e:
                        logger.warning(f"Re-explain LLM failed: {e}")
                        re_text = (
                            f"[NARRATION]\nNo problem. Let me explain {current_concept.title} differently. "
                            f"{current_concept.explanation}\n\n"
                            f"[CHECKPOINT]\n{current_concept.checkpoint_question}"
                        )

                    # Parse and stream re-explanation narration
                    narr_match = _re.search(
                        r"\[NARRATION\]\s*\n(.*?)(?=\[CHECKPOINT\]|\Z)",
                        re_text, _re.DOTALL | _re.IGNORECASE,
                    )
                    if narr_match:
                        narr = narr_match.group(1).strip()
                        sentences = _re.split(r'(?<=[.!?])\s+', narr)
                        for sent in sentences:
                            sent = sent.strip()
                            if sent:
                                yield f"event: reexplain\ndata: {json.dumps({'text': sent})}\n\n"
                                await asyncio.sleep(0.04)
                    else:
                        yield f"event: reexplain\ndata: {json.dumps({'text': re_text[:500]})}\n\n"

                    # New checkpoint from re-explanation
                    ckpt_match = _re.search(
                        r"\[CHECKPOINT\]\s*\n(.*?)$",
                        re_text, _re.DOTALL | _re.IGNORECASE,
                    )
                    new_q = ckpt_match.group(1).strip() if ckpt_match else current_concept.checkpoint_question
                    yield f"event: checkpoint\ndata: {json.dumps({'question': new_q})}\n\n"

                    sess["last_question"] = new_q
                    sess["current_phase"] = "waiting_answer"
                    should_advance = False

                    yield f"event: done_concept\ndata: {json.dumps({'concept_index': current_idx, 'has_more': True, 'reexplain_attempt': attempt_count + 1})}\n\n"
                    return  # stop here — wait for next answer
                else:
                    # Max retries reached → mark as struggled, advance anyway
                    failed = sess.get("concepts_failed", [])
                    if current_idx not in failed:
                        failed.append(current_idx)
                        sess["concepts_failed"] = failed
                    sess["attempt_count"] = 0
                    should_advance = True

                    yield f"event: acknowledge\ndata: {json.dumps({'text': f'No worries! This is a tough concept. We\'ll come back to {current_concept.title} later. Let\'s move on for now.'})}\n\n"

        # ════ PHASE 2: ADVANCE TO NEXT CONCEPT ════════════════════════════════════
        if not should_advance:
            return

        next_idx = current_idx + 1
        sess["current_concept_index"] = next_idx
        sess["interrupted"] = False
        sess["attempt_count"] = 0

        # Update explanation level based on session performance
        sess["explanation_level"] = adjust_explanation_level(sess)
        level = sess["explanation_level"]

        if next_idx >= lp.total_concepts:
            # All concepts done
            mastered = sess.get("concepts_mastered", [])
            failed = sess.get("concepts_failed", [])
            completion_msg = (
                f"Great work! We've covered all {lp.total_concepts} concepts "
                f"in today's lesson on '{topic}'. "
            )
            if mastered:
                completion_msg += f"You mastered {len(mastered)} out of {lp.total_concepts} concepts. "
            if failed:
                struggled_titles = [lp.concepts[i].title for i in failed if i < lp.total_concepts]
                completion_msg += f"We should revisit: {', '.join(struggled_titles)}. "
            completion_msg += "Try the quiz to cement your understanding!"

            # Phase 12: Record study session
            try:
                profile = ctx.get("profile", {})
                db_id = profile.get("db_id")
                if db_id:
                    from datetime import datetime
                    await record_study_session(
                        student_id=db_id,
                        subject_code=ctx.get("subject_code", ""),
                        topic=ctx.get("topic", ""),
                        duration_minutes=20,  # Estimated duration
                        concepts_covered=lp.total_concepts,
                        concepts_mastered=len(mastered),
                        concepts_struggled=len(failed),
                        peak_hour=datetime.now().hour,
                        score_avg=round(len(mastered) / max(lp.total_concepts, 1), 2)
                    )
            except Exception as e:
                logger.error(f"Failed to record study session: {e}")

            yield f"event: lesson_complete\ndata: {json.dumps({'topic': topic, 'total_concepts': lp.total_concepts, 'message': completion_msg, 'mastered': len(mastered), 'struggled': len(failed)})}\n\n"
            return

        # ── Stream next concept with continuity ───────────────────────────────
        concept = lp.concepts[next_idx]
        prev_title = lp.concepts[current_idx].title if current_idx < lp.total_concepts else ""

        sess["current_phase"] = "teaching"
        async for chunk in _stream_concept_step(
            concept, ctx,
            step_num=next_idx + 1,
            total_steps=lp.total_concepts,
            session_id=session_id,
            explanation_level=level,
            prev_concept_title=prev_title,
        ):
            yield chunk

        sess["current_phase"] = "waiting_answer"
        yield f"event: done\ndata: {json.dumps({'concept_index': next_idx})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/student/{student_id}/tutor/interrupt")
async def tutor_interrupt(student_id: str, body: dict):
    """
    Phase 8: Student interrupts mid-lesson with a question.

    Answers the doubt briefly (2–4 sentences).
    Preserves lesson_plan and current_concept_index — lesson resumes from same spot.
    Response always ends with: "Let's continue from where we left."

    Body: { session_id, question }

    Returns JSON (not SSE — interrupts should feel instant):
      {
        answer: str,
        resume_concept_index: int,
        resume_concept_title: str,
      }
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    session_id = (body.get("session_id") or "").strip()
    question = (body.get("question") or "").strip()

    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    if not session_id or session_id not in tutor_sessions:
        raise HTTPException(status_code=400, detail="Valid session_id required. Start a lesson first.")

    sess = tutor_sessions[session_id]
    lp = sess.get("lesson_plan")
    topic = sess.get("topic", "")
    subject_code = sess.get("subject_code", "")

    ctx = await build_tutor_context(student_id, subject_code, topic)
    if not ctx:
        raise HTTPException(status_code=404, detail="Student not found")

    # Current concept (may be None if lesson not started)
    current_idx = sess.get("current_concept_index", 0)
    current_concept = lp.concepts[current_idx] if lp and current_idx < lp.total_concepts else None

    # Build interrupt-specific system prompt
    if lp and current_concept:
        system_prompt = build_interrupt_system_prompt(current_concept, lp, ctx)
    else:
        # Fallback: no active lesson plan, treat like a regular Q&A
        profile = ctx.get("profile", {})
        student_name = profile.get("name", "Student").split()[0]
        system_prompt = (
            f"You are a tutor helping {student_name}. "
            "Answer the student's question in 2–4 sentences. "
            "End with: \"Let's continue from where we left.\""
        )

    try:
        llm = get_teacher_llm(temperature=0.4, max_tokens=250)
        result = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=question),
        ])
        answer = (result.content or "").strip()

        # Enforce the resume signal if LLM forgot it
        if "let's continue" not in answer.lower():
            answer += "\n\nLet's continue from where we left."

    except Exception as e:
        logger.error(f"Interrupt LLM failed: {e}", exc_info=True)
        answer = (
            f"That's a great question! {question[:80]}… "
            "I'll give you a fuller explanation once we finish this concept. "
            "Let's continue from where we left."
        )

    # Log into session (interrupt doesn't reset lesson state)
    sess["interrupted"] = True
    sess["turns"].append({"role": "user", "content": f"[INTERRUPT] {question}"})
    sess["turns"].append({"role": "assistant", "content": answer})

    return {
        "answer": answer,
        "resume_concept_index": current_idx,
        "resume_concept_title": current_concept.title if current_concept else "",
    }


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

    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    if session_id not in tutor_sessions:
        tutor_sessions[session_id] = _new_session()

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
   b. [DIAGRAM] — A valid Mermaid.js diagram for this step's concept.
      Prefer diagrams that look like real teaching aids: flowcharts for processes, sequence diagrams for protocols, state diagrams for state machines. Use clear, short labels (2-4 words per node). ONLY use: flowchart TD, sequenceDiagram, stateDiagram-v2, classDiagram.
      Keep diagrams SIMPLE — max 8 nodes. No inline styles or fill colors in node labels.
      Valid example: flowchart TD\\n    A[Start] --> B[Process] --> C[End]
4. End with a brief summary and suggest a follow-up quiz.
5. Adapt depth to Bloom level {bloom_level}: {'basics and recall' if bloom_level <= 2 else 'application and analysis' if bloom_level <= 4 else 'evaluation and creation'}.

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
...and so on.

IMPORTANT: Every [DIAGRAM] MUST contain valid Mermaid syntax inside a ```mermaid code fence.
Do NOT add fill colors, style clauses, or any CSS inside the diagram."""

    async def stream_lesson():
        try:
            yield f"event: session_id\ndata: {json.dumps({'session_id': session_id})}\n\n"
            full_text = None

            # ── Try Bedrock first (inference profile via converse API) ────────
            use_bedrock = (
                settings.aws_access_key_id and settings.aws_secret_access_key
            )
            if use_bedrock:
                try:
                    import boto3
                    from asyncio import get_event_loop
                    client_bedrock = boto3.client(
                        "bedrock-runtime",
                        region_name=settings.aws_region,
                        aws_access_key_id=settings.aws_access_key_id,
                        aws_secret_access_key=settings.aws_secret_access_key,
                    )

                    def _bedrock_call():
                        return client_bedrock.converse(
                            modelId=settings.bedrock_model_id,
                            system=[{"text": system_prompt}],
                            messages=[{"role": "user", "content": [{"text": f"Teach me: {topic}"}]}],
                            inferenceConfig={"maxTokens": 4000, "temperature": 0.5},
                        )

                    loop = get_event_loop()
                    br_response = await loop.run_in_executor(None, _bedrock_call)
                    full_text = br_response["output"]["message"]["content"][0]["text"]
                    logger.info(f"Bedrock converse succeeded for topic: {topic}")
                except Exception as be:
                    logger.warning(f"Bedrock call failed ({be}), falling back to Groq")
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

            # Parse the structured response into steps
            import re
            step_pattern = re.compile(r'\[STEP\s+(\d+):\s*([^\]]+)\]', re.IGNORECASE)
            narration_pattern = re.compile(r'\[NARRATION\]\s*\n(.*?)(?=\[DIAGRAM\]|\[STEP|\Z)', re.DOTALL | re.IGNORECASE)
            diagram_pattern = re.compile(r'```mermaid\s*\n(.*?)```', re.DOTALL)

            steps = list(step_pattern.finditer(full_text))
            narrations = list(narration_pattern.finditer(full_text))
            diagrams = list(diagram_pattern.finditer(full_text))

            if not steps:
                # Fallback: send as one big narration
                yield f"event: step\ndata: {json.dumps({'step': 1, 'title': topic})}\n\n"
                yield f"event: narration\ndata: {json.dumps({'text': full_text[:2000]})}\n\n"
                yield f"event: done\ndata: {json.dumps({})}\n\n"
                return

            for i, step_match in enumerate(steps):
                step_num = step_match.group(1)
                step_title = step_match.group(2).strip()

                yield f"event: step\ndata: {json.dumps({'step': int(step_num), 'title': step_title})}\n\n"

                # Find narration for this step
                if i < len(narrations):
                    narr_text = narrations[i].group(1).strip()
                    # Split into sentences for smoother TTS
                    sentences = re.split(r'(?<=[.!?])\s+', narr_text)
                    for sent in sentences:
                        sent = sent.strip()
                        if sent:
                            yield f"event: narration\ndata: {json.dumps({'text': sent})}\n\n"
                            await asyncio.sleep(0.05)

                # Find diagram for this step
                if i < len(diagrams):
                    mermaid_code = diagrams[i].group(1).strip()
                    yield f"event: diagram\ndata: {json.dumps({'mermaid': mermaid_code, 'title': step_title})}\n\n"

                await asyncio.sleep(0.1)

            if session_id in tutor_sessions:
                tutor_sessions[session_id]["lesson_summary"] = f"Lesson: {topic}, steps 1–{len(steps)}"
            yield f"event: done\ndata: {json.dumps({'total_steps': len(steps)})}\n\n"

        except Exception as e:
            logger.error(f"Tutor teach error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream_lesson(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/student/{student_id}/tutor/session/clear")
async def tutor_session_clear(student_id: str, body: dict):
    """Clear a tutor session (e.g. for 'New conversation'). Body: { session_id }"""
    sid = body.get("session_id")
    if sid and sid in tutor_sessions:
        del tutor_sessions[sid]
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

    system_prompt = f"""You are the AI Tutor for an engineering student. They are learning "{topic}" in {subject_name}. Continue the conversation naturally. Reference what you already taught or what the student asked. Vary your explanations; do not repeat the same sentences. If they ask to explain again, use different examples or a different angle. Sometimes offer a one-sentence recap question; when the student answers, briefly confirm or correct.{session_context}

STUDENT CONTEXT:
- Name: {profile.get('name', 'Student')}
- Bloom level: {bloom}/6. Learning style: {style}
{f'- Mastery: {mastery_block}' if mastery_block else ''}

SYLLABUS (current subject units):
{syllabus_text}

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
        use_bedrock = (
            (settings.aws_access_key_id and settings.aws_secret_access_key)
            or bool(settings.bedrock_api_key)
        )
        if use_bedrock:
            try:
                from langchain_aws import ChatBedrock
                kwargs = {
                    "region_name": settings.aws_region,
                    "model_id": settings.bedrock_model_id,
                    "model_kwargs": {"temperature": 0.4, "max_tokens": 800},
                }
                if settings.aws_access_key_id and settings.aws_secret_access_key:
                    kwargs["aws_access_key_id"] = settings.aws_access_key_id
                    kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
                elif settings.bedrock_api_key:
                    kwargs["bedrock_api_key"] = settings.bedrock_api_key
                llm = ChatBedrock(**kwargs)
            except Exception as be:
                logger.warning(f"Bedrock init failed, using Gemini: {be}")
                llm = None
        if llm is None:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                google_api_key=settings.google_api_key,
                model=settings.gemini_flash_model,
                temperature=0.4,
                max_output_tokens=800,
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
        return {"answer": text, "mermaid": mermaid_block}
    except Exception as invoke_err:
        err_msg = (getattr(invoke_err, "message", None) or str(invoke_err)).lower()
        if "accessdenied" in err_msg or "authentication failed" in err_msg or "api key" in err_msg:
            logger.warning(f"Bedrock auth failed ({invoke_err}), falling back to Gemini")
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                google_api_key=settings.google_api_key,
                model=settings.gemini_flash_model,
                temperature=0.4,
                max_output_tokens=800,
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


# ════════════════════════════════════════════════════════════════════════════════
# PHASE 11: REAL-TIME VOICE TUTOR
# ════════════════════════════════════════════════════════════════════════════════


@app.post("/student/{student_id}/tutor/voice/start")
async def tutor_voice_start(student_id: str, body: dict):
    """
    Phase 11: Enable voice mode for the tutor.

    Body: { subject_code, topic, session_id?, voice_id?: "matthew"|"ruth"|"tiffany" }

    Initializes a Nova Sonic bidirectional session with teacher persona.
    Returns: { session_id, voice_mode, status, voice_id }
    """
    subject_code = body.get("subject_code", "")
    topic = body.get("topic", "")
    session_id = body.get("session_id") or f"{student_id}:{subject_code}:{topic}"
    voice_id = body.get("voice_id", "matthew")

    # Ensure session exists
    if session_id not in tutor_sessions:
        tutor_sessions[session_id] = _new_session()
    sess = tutor_sessions[session_id]

    # Build tutor context for personalized voice prompt
    try:
        ctx = await build_tutor_context(student_id, subject_code, topic)
    except Exception:
        ctx = {"profile": {"name": student_id}, "bloom_level": 2, "style": "example-based"}

    voice_prompt = build_voice_system_prompt(ctx, topic=topic)

    # Create and start the Nova Sonic bridge
    bridge = NovaSonicBridge(
        voice_id=voice_id,
        system_prompt=voice_prompt,
    )

    try:
        await bridge.start_session()
    except Exception as e:
        logger.error(f"Voice session start failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Voice session failed: {str(e)}"},
        )

    # Store the bridge
    _voice_bridges[session_id] = bridge

    # Update session state
    sess["voice_mode"] = True
    sess["voice_status"] = "listening"
    sess["speaking"] = False
    sess["interrupt_requested"] = False
    sess["topic"] = topic
    sess["subject_code"] = subject_code

    return {
        "session_id": session_id,
        "voice_mode": True,
        "status": "listening",
        "voice_id": voice_id,
    }


@app.post("/student/{student_id}/tutor/voice/stop")
async def tutor_voice_stop(student_id: str, body: dict):
    """
    Phase 11: Disable voice mode and cleanup Nova Sonic session.

    Body: { session_id }

    Returns: { voice_mode, status }
    """
    session_id = body.get("session_id", "")

    # End the Nova Sonic bridge if active
    bridge = _voice_bridges.pop(session_id, None)
    if bridge:
        try:
            await bridge.end_session()
        except Exception as e:
            logger.warning(f"Voice session cleanup error: {e}")

    # Update session state
    sess = tutor_sessions.get(session_id)
    if sess:
        sess["voice_mode"] = False
        sess["voice_status"] = "idle"
        sess["speaking"] = False
        sess["interrupt_requested"] = False

    return {"voice_mode": False, "status": "idle"}


@app.websocket("/student/{student_id}/tutor/voice/ws")
async def tutor_voice_ws(websocket, student_id: str):
    """
    Phase 11: Real-time voice WebSocket for bidirectional audio streaming.

    Client → Server messages (JSON):
        { "type": "audio", "data": "<base64 LPCM 16kHz>" }
        { "type": "text", "data": "transcript text" }
        { "type": "interrupt" }
        { "type": "init", "session_id": "..." }

    Server → Client messages (JSON):
        { "type": "audio", "data": "<base64 LPCM 24kHz>" }
        { "type": "text", "data": "assistant transcript" }
        { "type": "transcript", "data": "user transcript (STT)" }
        { "type": "status", "data": "listening|thinking|speaking|idle" }
        { "type": "error", "data": "error message" }
    """
    from starlette.websockets import WebSocketDisconnect

    await websocket.accept()

    session_id = None
    bridge = None

    try:
        # Wait for init message with session_id
        init_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        if init_msg.get("type") != "init" or not init_msg.get("session_id"):
            await websocket.send_json({"type": "error", "data": "Send init with session_id first"})
            await websocket.close()
            return

        session_id = init_msg["session_id"]
        bridge = _voice_bridges.get(session_id)

        if not bridge or not bridge.is_active:
            await websocket.send_json({"type": "error", "data": "No active voice session. Call voice/start first."})
            await websocket.close()
            return

        sess = tutor_sessions.get(session_id, {})
        await websocket.send_json({"type": "status", "data": "listening"})

        # ── Task 1: Forward Nova Sonic events → WebSocket client ──
        async def forward_events():
            try:
                async for event in bridge.events():
                    msg = {"type": event.type, "data": event.data}
                    await websocket.send_json(msg)

                    # Update session state
                    if event.type == "status":
                        sess["voice_status"] = event.data
                        sess["speaking"] = event.data == "speaking"
                    elif event.type == "transcript":
                        sess["last_transcript"] = event.data
            except Exception as e:
                logger.warning(f"Voice forward task error: {e}")

        forward_task = asyncio.create_task(forward_events())

        # ── Task 2: Receive client messages → Nova Sonic ──
        try:
            while True:
                msg = await websocket.receive_json()
                msg_type = msg.get("type", "")
                msg_data = msg.get("data", "")

                if msg_type == "audio":
                    # Raw audio from client mic
                    await bridge.send_audio_chunk(msg_data)

                elif msg_type == "text":
                    # Text input (typed or transcript)
                    sess["last_transcript"] = msg_data
                    sess["voice_status"] = "thinking"

                    # If tutor is currently speaking, this is an interrupt
                    if sess.get("speaking"):
                        sess["interrupt_requested"] = True
                        logger.info(f"Voice interrupt: '{msg_data[:50]}...'")

                    await bridge.send_text_input(msg_data)

                elif msg_type == "interrupt":
                    sess["interrupt_requested"] = True
                    sess["voice_status"] = "listening"
                    logger.info("Manual interrupt requested")

        except WebSocketDisconnect:
            logger.info(f"Voice WebSocket disconnected: {session_id}")
        except Exception as e:
            logger.error(f"Voice WebSocket error: {e}", exc_info=True)

        # Cleanup
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass

    except asyncio.TimeoutError:
        await websocket.send_json({"type": "error", "data": "Init timeout"})
        await websocket.close()
    except Exception as e:
        logger.error(f"Voice WS setup error: {e}", exc_info=True)
        try:
            await websocket.close()
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════════
# PHASE 12: MENTOR PROGRESS & DASHBOARD APIs
# ════════════════════════════════════════════════════════════════════════════════

@app.get("/student/{student_id}/mentor/progress")
async def get_mentor_progress(student_id: str):
    """
    Phase 12: Returns long-term progress metrics for the student.
    """
    profile = await get_student_profile(student_id)
    if not profile or not profile.get("db_id"):
        return {"error": "Student not found"}
    
    try:
        data = await get_progress_data(profile["db_id"])
        return data
    except Exception as e:
        logger.error(f"Progress data error: {e}", exc_info=True)
        return {"error": "Failed to fetch progress"}


@app.get("/student/{student_id}/mentor/dashboard")
async def get_mentor_dashboard(student_id: str):
    """
    Phase 12: Returns mentor dashboard statistics and dynamic study plans.
    """
    profile = await get_student_profile(student_id)
    if not profile or not profile.get("db_id"):
        return {"error": "Student not found"}
    
    try:
        data = await get_dashboard_data(profile["db_id"])
        
        # Optionally generate study plan using primary LLM if they have weak topics
        # We will use subject_code = None to get a generic plan
        plan = await generate_study_plan(profile["db_id"], "General/Weak Areas")
        data["study_plan"] = plan
        
        return data
    except Exception as e:
        logger.error(f"Dashboard data error: {e}", exc_info=True)
        return {"error": "Failed to fetch dashboard"}


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.agent_service_host,
        port=settings.agent_service_port,
        reload=settings.env == "development",
        log_level=settings.log_level.lower(),
    )
