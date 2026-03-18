"""
AI-Mentor — Agentic Prediction Engine (v2)
2-phase Amazon Bedrock (ChatGPT 120b) analysis:
  Phase 1 → Structured JSON: per-subject diagnosis, arrear risk, critical moves
  Phase 2 → Markdown narrative: conversational deep-dive like a personal tutor
Fallback: Groq (llama-3.3-70b-versatile) if Bedrock fails.
"""
import json
import logging
import numpy as np
from sklearn.linear_model import LinearRegression
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings

logger = logging.getLogger(__name__)


def _to_float(value, default: float) -> float:
    """Coerce DB/ERP values safely for prediction math."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

# ── Phase-1 prompt (structured JSON) ────────────────────────────────────────
_PHASE1_SYSTEM = """You are an advanced academic prediction AI. Perform a deep statistical and contextual analysis of the student's data.

Output ONLY a valid JSON object (no markdown, no explanation):
{
  "trajectory_signal": "declining|stable|improving",
  "trajectory_reason": "2-sentence data-driven explanation",
  "cgpa_verdict": {
    "pessimistic": <float>,
    "realistic": <float>,
    "optimistic": <float>,
    "confidence_pct": <int 50-95>,
    "key_factor": "1 sentence"
  },
  "subject_deep_dive": [
    {
      "code": "CS702",
      "name": "Operating Systems",
      "risk_score": <int 0-100>,
      "root_causes": ["cause 1", "cause 2"],
      "immediate_actions": ["specific action 1", "specific action 2"],
      "prognosis": "improving|stable|declining",
      "arrear_probability": <float 0-1>
    }
  ],
  "arrear_risk": [
    { "code": "CS702", "name": "...", "probability": <float 0-1>, "warning": "1 sentence critical warning" }
  ],
  "critical_moves": [
    { "priority": 1, "action": "specific action", "impact": "CGPA +0.x", "timeline": "2 weeks" },
    { "priority": 2, "action": "...", "impact": "...", "timeline": "..." },
    { "priority": 3, "action": "...", "impact": "...", "timeline": "..." }
  ],
  "study_dna_impact": "2 sentences on how learning DNA profile affects predicted outcome"
}

Rules:
- risk_score: 0=no risk, 100=certain arrear
- Use actual subject names/codes from the data
- arrear_risk only includes subjects with arrear_probability > 0.35
- Every action must be SPECIFIC and ACTIONABLE (not generic advice)
"""

# ── Phase-2 prompt (markdown narrative) ─────────────────────────────────────
_PHASE2_SYSTEM = """You are an empathetic but honest academic mentor AI. Write a detailed, personalized academic analysis for the student.

Format: markdown with bold, bullet lists. 500-650 words. Structure:
1. Opening verdict (2 sentences — direct, data-driven)
2. **Subject Deep Dive** — 2-3 sentences per subject (start with highest-risk)
3. **Your 3 Critical Priorities this Week** — numbered list with specific steps
4. **CGPA Outlook** — optimistic vs pessimistic scenario, what drives each
5. Closing (1-2 sentences — motivational but honest)

Do NOT use clichés ("hard work pays off"). Be specific. Reference real grades, attendance %, bloom levels.
"""


def _get_llm(temperature: float = 0.2, max_tokens: int = 1500):
    """Return Bedrock ChatGPT first, fall back to Groq."""
    try:
        from langchain_aws import ChatBedrock
        return ChatBedrock(
            model_id=settings.bedrock_model_id,
            region_name=settings.aws_region,
            model_kwargs={"temperature": temperature, "max_tokens": max_tokens},
        ), "bedrock"
    except Exception as e:
        logger.warning(f"Bedrock init failed ({e}), using Groq")
        from langchain_groq import ChatGroq
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=temperature,
            max_tokens=max_tokens,
        ), "groq"


def _build_context(profile: dict, learning_dna: dict | None = None) -> str:
    subjects = profile.get("subjects", [])
    cgpa_history = profile.get("cgpaHistory", [])
    risk_s  = [s for s in subjects if s.get("status") == "risk"]
    watch_s = [s for s in subjects if s.get("status") == "watch"]
    safe_s  = [s for s in subjects if s.get("status") == "safe"]
    dna = learning_dna or {}

    def fmt_subject(s):
        return (
            f"  - [{s.get('code','?')}] {s.get('name')}: "
            f"grade={s.get('grade')}/10, attendance={s.get('live_attendance') or s.get('attendance','?')}%, "
            f"bloom={s.get('bloomLevel') or s.get('bloom_level',2)}/6, "
            f"credits={s.get('creditWeight') or s.get('credit_weight',3)}, "
            f"status={s.get('status')}"
        )

    lines = [
        f"Student: {profile.get('name','?')} | CGPA: {profile.get('currentCGPA')} | Semester: {profile.get('semester')}",
        f"CGPA History: {cgpa_history}",
        f"Exam in: {profile.get('examDays') or profile.get('exam_days','?')} days",
        f"Study streak: {profile.get('studyStreak', profile.get('study_streak', 0))} days",
        "",
        f"AT-RISK subjects ({len(risk_s)}):",
        *[fmt_subject(s) for s in risk_s],
        f"WATCH subjects ({len(watch_s)}):",
        *[fmt_subject(s) for s in watch_s],
        f"SAFE subjects ({len(safe_s)}):",
        *[fmt_subject(s) for s in safe_s],
    ]
    if dna:
        lines += [
            "",
            f"Learning DNA: peak_hour={dna.get('peak_hour','?')}, "
            f"style={dna.get('preferred_style','?')}, "
            f"weak_topics={[w if isinstance(w, str) else str(w.get('topic','')) for w in (dna.get('weak_topics') or [])[:3]]}"
        ]
    # Syllabus coverage gaps
    coverage = profile.get("syllabusCoverage", profile.get("syllabus_coverage", []))
    low_cov = [f"{c.get('subject_name','?')} ({c.get('coverage_pct',0)}%)" for c in coverage if float(c.get("coverage_pct") or 100) < 60]
    if low_cov:
        lines.append(f"Low syllabus coverage: {', '.join(low_cov[:4])}")
    return "\n".join(lines)


async def run_bedrock_analysis(profile: dict, learning_dna: dict | None = None) -> dict:
    """
    2-phase async analysis:
    Phase 1 → structured JSON (temp 0.1)
    Phase 2 → markdown narrative (temp 0.35)
    Returns merged dict with all fields.
    """
    context = _build_context(profile, learning_dna)

    # Phase 1 — Structured JSON
    llm1, provider1 = _get_llm(temperature=0.1, max_tokens=1800)
    phase1_result = {}
    try:
        resp1 = await llm1.ainvoke([
            SystemMessage(content=_PHASE1_SYSTEM),
            HumanMessage(content=f"Analyze this student:\n\n{context}"),
        ])
        raw = resp1.content.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        phase1_result = json.loads(raw)
        logger.info(f"✅ Phase 1 analysis via {provider1}")
    except Exception as e:
        logger.warning(f"Phase 1 failed ({e}), using fallback schema")
        subjects = profile.get("subjects", [])
        phase1_result = _fallback_phase1(profile, subjects)

    # Phase 2 — markdown narrative
    llm2, provider2 = _get_llm(temperature=0.35, max_tokens=900)
    narrative = ""
    try:
        phase1_summary = json.dumps({
            "trajectory_signal": phase1_result.get("trajectory_signal"),
            "cgpa_verdict": phase1_result.get("cgpa_verdict"),
            "subject_deep_dive": phase1_result.get("subject_deep_dive", [])[:4],
            "critical_moves": phase1_result.get("critical_moves", []),
        }, indent=2)
        resp2 = await llm2.ainvoke([
            SystemMessage(content=_PHASE2_SYSTEM),
            HumanMessage(content=f"Student data:\n{context}\n\nPhase 1 analysis:\n{phase1_summary}\n\nWrite the narrative:"),
        ])
        narrative = resp2.content.strip()
        logger.info(f"✅ Phase 2 narrative via {provider2}")
    except Exception as e:
        logger.warning(f"Phase 2 failed ({e}), using fallback narrative")
        narrative = _fallback_narrative(profile, phase1_result)

    return {
        **phase1_result,
        "analysis_narrative": narrative,
        "providers": {"phase1": provider1, "phase2": provider2},
    }


async def run_bedrock_sim_explanation(
    profile: dict,
    improvement: dict,
    baseline_cgpa: float,
    simulated_cgpa: float,
) -> str:
    """Generate a 3-sentence Bedrock explanation for why the simulation changed the CGPA."""
    llm, _ = _get_llm(temperature=0.3, max_tokens=300)
    delta = round(simulated_cgpa - baseline_cgpa, 3)
    prompt = (
        f"Student CGPA: {baseline_cgpa} → {simulated_cgpa} (delta {'+' if delta >= 0 else ''}{delta}).\n"
        f"Changes: attendance +{improvement.get('attendance_delta', 0)}%, "
        f"assignments +{improvement.get('assignment_delta', 0)}%, "
        f"study hours +{improvement.get('study_hours_delta', 0)}h/day.\n"
        f"Student has {len([s for s in profile.get('subjects', []) if s.get('status') == 'risk'])} at-risk subjects.\n\n"
        f"In exactly 3 sentences, explain the predicted CGPA change. "
        f"Be specific about which improvement had the most impact and why. "
        f"End with one concrete next step."
    )
    try:
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        return resp.content.strip()
    except Exception as e:
        logger.warning(f"Sim explanation failed ({e})")
        if delta > 0:
            return f"Improving attendance by {improvement.get('attendance_delta', 0)}% would directly reduce absentee penalties and boost internal assessment marks, contributing the most to the CGPA gain. Completing more assignments adds grade points across all subjects simultaneously. Start by attending all classes this week to set the habit."
        return "The changes you selected would have minimal impact on your CGPA projection. Focus on improving attendance in at-risk subjects first, as that carries the highest grade weighting. Consistent attendance above 75% is the single most impactful change you can make this month."


# ── Fallback schemas ──────────────────────────────────────────────────────────
def _fallback_phase1(profile: dict, subjects: list) -> dict:
    risk  = [s for s in subjects if s.get("status") == "risk"]
    watch = [s for s in subjects if s.get("status") == "watch"]
    cgpa  = float(profile.get("currentCGPA") or 7.0)
    hist  = profile.get("cgpaHistory", [])
    trend = "declining" if len(hist) >= 2 and hist[-1] < hist[-2] else "stable" if len(hist) < 2 else "improving"

    deep_dive = []
    for s in subjects:
        grade = float(s.get("grade") or 7.0)
        att   = float(s.get("live_attendance") or s.get("attendance") or 80)
        risk_score = min(100, max(0, int((7.0 - grade) * 20 + (80 - att) * 0.8)))
        arrear_prob = 0.7 if s.get("status") == "risk" else 0.3 if s.get("status") == "watch" else 0.05
        deep_dive.append({
            "code": s.get("code", "?"),
            "name": s.get("name", "?"),
            "risk_score": risk_score,
            "root_causes": [
                f"Grade {grade}/10 is below passing threshold" if grade < 6.5 else "Borderline grade",
                f"Attendance {att}% is {'below' if att < 75 else 'near'} minimum 75%",
            ],
            "immediate_actions": [
                "Attend all remaining classes to recover attendance",
                "Complete pending assignments before the next exam",
            ],
            "prognosis": s.get("status", "safe"),
            "arrear_probability": arrear_prob,
        })

    arrear_risk = [
        {"code": s.get("code"), "name": s.get("name"), "probability": 0.7, "warning": f"Grade {s.get('grade')}/10 and low attendance put this subject at serious arrear risk."}
        for s in risk
    ]

    return {
        "trajectory_signal": trend,
        "trajectory_reason": f"CGPA trend is {trend} based on {len(hist)} semesters of data.",
        "cgpa_verdict": {
            "pessimistic": round(cgpa - 0.4, 1),
            "realistic":   round(cgpa, 1),
            "optimistic":  round(min(10, cgpa + 0.3), 1),
            "confidence_pct": 65,
            "key_factor": f"{len(risk)} at-risk subjects are dragging the weighted average down.",
        },
        "subject_deep_dive": deep_dive,
        "arrear_risk": arrear_risk,
        "critical_moves": [
            {"priority": 1, "action": f"Attend all classes in {risk[0]['name'] if risk else 'at-risk subjects'}", "impact": "CGPA +0.2", "timeline": "2 weeks"},
            {"priority": 2, "action": "Complete all overdue assignments", "impact": "CGPA +0.1", "timeline": "1 week"},
            {"priority": 3, "action": "Schedule 2hr daily revision for weak subjects", "impact": "CGPA +0.1", "timeline": "3 weeks"},
        ],
        "study_dna_impact": "Your learning patterns suggest you retain information better during focused sessions. Avoid passive reading and shift to practice-based recall.",
    }


def _fallback_narrative(profile: dict, phase1: dict) -> str:
    cgpa    = profile.get("currentCGPA", "?")
    verdict = phase1.get("cgpa_verdict", {})
    moves   = phase1.get("critical_moves", [])
    traj    = phase1.get("trajectory_signal", "stable")
    subjects = profile.get("subjects", [])
    risk   = [s for s in subjects if s.get("status") == "risk"]

    narrative = f"**Your current CGPA of {cgpa} puts you on a {traj} trajectory** with a realistic projection of {verdict.get('realistic', '?')} next semester.\n\n"
    if risk:
        narrative += "**Subject Deep Dive**\n\n"
        for s in risk[:3]:
            narrative += f"**{s.get('name')}** — Grade {s.get('grade')}/10 with {s.get('live_attendance') or s.get('attendance','?')}% attendance places this subject in the at-risk zone. Immediate remediation is required.\n\n"

    if moves:
        narrative += "**Your 3 Critical Priorities This Week**\n\n"
        for m in moves[:3]:
            narrative += f"{m['priority']}. {m['action']} — expected impact: {m.get('impact','?')} within {m.get('timeline','?')}.\n"

    narrative += f"\n**CGPA Outlook** — Pessimistic: {verdict.get('pessimistic','?')} | Realistic: {verdict.get('realistic','?')} | Optimistic: {verdict.get('optimistic','?')}.\n\n"
    narrative += "Stay consistent with attendance and complete assignments on time — these two factors have the highest statistical correlation with CGPA improvement."
    return narrative


# ── Numeric CGPA predictor (kept for stats) ──────────────────────────────────
def compute_predicted_cgpa(profile: dict, improvement: dict = None) -> dict:
    """
    Scikit-learn linear regression CGPA prediction.
    improvement = { attendance_delta, assignment_delta, study_hours_delta }
    """
    cgpa_history = [
        _to_float(point, 0.0)
        for point in (profile.get("cgpaHistory") or [])
        if point is not None and point != ""
    ]
    subjects = profile.get("subjects") or []
    trend_prediction = _to_float(profile.get("currentCGPA"), 0.0)
    r_sq = 0.5  # default confidence

    if len(cgpa_history) >= 2:
        X = np.array(range(1, len(cgpa_history) + 1)).reshape(-1, 1)
        y = np.array(cgpa_history)
        model = LinearRegression()
        model.fit(X, y)
        trend_prediction = model.predict([[len(cgpa_history) + 1]])[0]
        r_sq = model.score(X, y)

    grades = [_to_float(s.get("grade"), 7.0) for s in subjects]
    attendances = [_to_float(s.get("live_attendance") or s.get("attendance"), 80.0) for s in subjects]

    if grades:
        mean_grade = np.mean(grades)
        std_grade  = np.std(grades)
        mean_att   = np.mean(attendances)
        std_att    = np.std(attendances)

        for s in subjects:
            g = _to_float(s.get("grade"), 7.0)
            a = _to_float(s.get("live_attendance") or s.get("attendance"), 80.0)
            grade_risk = (g < mean_grade - 1.5 * std_grade) or (g < 6.0)
            att_risk   = (a < mean_att - 1.5 * std_att) or (a < 75)
            s["status"] = "risk" if (grade_risk and att_risk) else ("watch" if (grade_risk or att_risk or g < 7.0) else "safe")

            boost = 0.0
            if improvement:
                boost += _to_float(improvement.get("attendance_delta"), 0.0) * 0.05
                boost += _to_float(improvement.get("study_hours_delta"), 0.0) * 0.1
            s["predicted"] = round(min(10.0, g + boost + (0.1 if trend_prediction > mean_grade else -0.1)), 1)

    boost = 0.0
    if improvement:
        boost += _to_float(improvement.get("attendance_delta"), 0.0) * 0.008
        boost += _to_float(improvement.get("assignment_delta"), 0.0) * 0.005
        boost += _to_float(improvement.get("study_hours_delta"), 0.0) * 0.01

    final = round(min(10.0, trend_prediction + boost), 2)
    margin = round(max(0.2, 0.5 - r_sq * 0.3), 1)

    return {
        "cgpa": final,
        "range": [round(max(0, final - margin), 1), round(min(10, final + margin), 1)],
        "confidence": round(r_sq, 2),
    }


def build_prediction_fallback(profile: dict) -> dict:
    """Return a deterministic prediction payload when LLM analysis fails."""
    subjects = profile.get("subjects") or []
    phase1 = _fallback_phase1(profile, subjects)
    return {
        **phase1,
        "analysis_narrative": _fallback_narrative(profile, phase1),
        "providers": {"phase1": "fallback", "phase2": "fallback"},
    }


# ── LangGraph-compatible node ─────────────────────────────────────────────────
async def prediction_node(state: dict) -> dict:
    """
    LangGraph node wrapper for the prediction engine.
    Calls run_bedrock_analysis; falls back to build_prediction_fallback on error.
    Writes prediction_output + model_used into AgentState.
    """
    profile = state.get("student_profile", {})

    try:
        from db import db
        student_id = state.get("student_id")
        learning_dna = None
        if student_id:
            try:
                learning_dna = await db.get_learning_dna(student_id)
            except Exception as dna_err:
                logger.warning(f"Learning DNA load skipped: {dna_err}")

        result = await run_bedrock_analysis(profile, learning_dna)
        provider = (result.get("providers") or {}).get("phase1", "bedrock")
    except Exception as e:
        logger.error(f"prediction_node LLM failed ({e}), using deterministic fallback")
        result = build_prediction_fallback(profile)
        provider = "fallback"

    # Build a concise narrative for the chat response
    narrative = result.get("analysis_narrative") or ""
    verdict = result.get("cgpa_verdict") or {}
    if not narrative and verdict:
        narrative = (
            f"**CGPA Outlook** — Realistic: {verdict.get('realistic', '?')} | "
            f"Optimistic: {verdict.get('optimistic', '?')} | "
            f"Pessimistic: {verdict.get('pessimistic', '?')}\n\n"
            f"{verdict.get('key_factor', '')}"
        )

    return {
        **state,
        "prediction_output": narrative,
        "primary_agent": "prediction",
        "model_used": provider,
        "citations": [
            {"label": f"CGPA: {profile.get('currentCGPA', 'N/A')}", "source": "ERP Academic Record"},
            {"label": f"Trajectory: {result.get('trajectory_signal', 'stable')}", "source": "Prediction Engine"},
        ],
    }

