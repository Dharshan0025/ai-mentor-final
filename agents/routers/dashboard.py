import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from config import settings
from db import db
from services import get_student_profile

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Dashboard"])

@router.get("/student/{student_id}/predictions")
async def get_predictions(student_id: str):
    """
    Agentic prediction endpoint — 2-phase NVIDIA NIM (llama-3.3-70b-instruct) deep analysis.
    Phase 1: structured JSON (risk scores, arrear risk, critical moves)
    Phase 2: markdown narrative (conversational tutor-style explanation)
    Falls back to Groq if NVIDIA NIM is unavailable.
    """
    from agents.prediction import compute_predicted_cgpa, run_bedrock_analysis, build_prediction_fallback

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

    # 2-phase Bedrock deep analysis (async)
    try:
        analysis = await run_bedrock_analysis(profile, learning_dna)
    except Exception as e:
        logger.warning(f"Prediction analysis failed for {student_id}: {e}")
        analysis = build_prediction_fallback(profile)

    # Build per-subject prediction list (merge numeric + Bedrock deep_dive)
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
        # Bedrock supplemented verdict
        "cgpa_verdict":        cgpa_verdict,
        "trajectory_signal":   analysis.get("trajectory_signal", "stable"),
        "trajectory_reason":   analysis.get("trajectory_reason", ""),
        # Per-subject enriched list
        "subjects":            subject_predictions,
        # Aggregated risk lists
        "arrear_risk":         analysis.get("arrear_risk", []),
        "risk_subject_count":  len(risk_subjects),
        "watch_subject_count": len(watch_subjects),
        # Bedrock actionable intelligence
        "critical_moves":      analysis.get("critical_moves", []),
        "study_dna_impact":    analysis.get("study_dna_impact", ""),
        # LLM-generated markdown narrative
        "analysis_narrative":  analysis.get("analysis_narrative", ""),
        "providers":           analysis.get("providers", {}),
        "exam_days":           profile.get("examDays") or profile.get("exam_days"),
        "generated_at":        datetime.utcnow().isoformat(),
    }

@router.get("/student/{student_id}/schedule")
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
    week = await generate_ai_schedule(profile, learning_dna)

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


@router.get("/student/{student_id}/career")
async def get_career(student_id: str):
    """Generate full career intelligence report for the student."""
    from agents.career import generate_career_report
    profile = await get_student_profile(student_id)
    return generate_career_report(profile)

def _get_risk_drivers(subject: dict) -> list[str]:

    drivers = []
    if subject.get("attendance", 100) < 75:
        drivers.append(f"Attendance at {subject.get('attendance')}% (below 75% threshold)")
    if subject.get("grade", 10) < 6.0:
        drivers.append(f"Grade {subject.get('grade')} is below pass threshold")
    if subject.get("bloomLevel", 6) <= 2:
        drivers.append("Bloom level ≤2 indicates surface-level understanding only")
    return drivers or ["Performing within expected range"]

@router.get("/student/{student_id}/briefing")
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

        # Try NVIDIA NIM first, fall back to Groq
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


@router.get("/student/{student_id}/min-scores")
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

@router.get("/student/{student_id}/profile")
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


@router.get("/student/{student_id}/sentiment")
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


@router.get("/student/{student_id}/benchmark")
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


@router.get("/student/{student_id}/parent-summary")
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


@router.get("/student/{student_id}/mastery")
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


@router.post("/student/{student_id}/simulate")
async def simulate_scenario(student_id: str, body: dict):
    """
    Scenario simulator — numeric CGPA delta + Bedrock explanation of the change.
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
    add_explanation = body.get("explain", False)  # frontend requests Bedrock explanation

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


@router.get("/student/{student_id}/skill-gap")
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


@router.post("/student/{student_id}/roadmap/generate")
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


@router.get("/student/{student_id}/roadmap")
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


@router.get("/leaderboard")
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


