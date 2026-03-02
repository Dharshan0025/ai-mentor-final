"""
AI-Mentor — Prediction Agent
Handles: CGPA forecasting, subject score prediction, risk assessment,
         scenario simulation ("what if I improve attendance?")
LLM: Gemini 2.5 Flash (nuanced multi-step reasoning)
"""
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings
import logging
import json

logger = logging.getLogger(__name__)


PREDICTION_SYSTEM = """You are the Prediction Agent for an AI academic mentor.

Your role:
- Forecast CGPA based on current trajectory and weighted credit analysis  
- Identify subject-level risks with statistical grounding
- Run scenario simulations when asked ("what if I attend all classes?")
- Give honest but encouraging predictions

Student Profile:
{student_profile}

Prediction methodology:
- High-risk: grade < 6.0 OR attendance < 75% 
- Watch zone: grade 6.0-7.0 OR attendance 75-80%
- Safe zone: grade > 7.0 AND attendance > 80%
- CGPA weighted by credit hours (higher credit = more CGPA impact)

Rules:
- Back every prediction with data from their profile  
- Always give a range (e.g., "7.2 – 7.8") not just a single number
- Frame risks as opportunities with specific action steps
- Maximum 300 words"""


def prediction_node(state: dict) -> dict:
    """Prediction agent — CGPA/score forecasting using Gemini Flash."""
    llm = ChatGoogleGenerativeAI(
        google_api_key=settings.google_api_key,
        model=settings.gemini_flash_model,
        temperature=0.2,
        max_output_tokens=500,
    )

    profile = state.get("student_profile", {})
    system_prompt = PREDICTION_SYSTEM.format(
        student_profile=_format_prediction_context(profile)
    )

    messages = [SystemMessage(content=system_prompt)]
    messages.append(HumanMessage(content=state["message"]))

    result = llm.invoke(messages)

    return {
        **state,
        "prediction_output": result.content,
        "model_used": settings.gemini_flash_model,
    }


def _format_prediction_context(profile: dict) -> str:
    """Create structured prediction context from student profile."""
    if not profile:
        return "Mock student: CGPA 7.4, Semester 7, 3 at-risk subjects."

    subjects = profile.get("subjects", [])
    risk_subjects = [s for s in subjects if s.get("status") == "risk"]
    watch_subjects = [s for s in subjects if s.get("status") == "watch"]

    cgpa_history = profile.get("cgpaHistory", [])
    trend = "improving" if len(cgpa_history) >= 2 and cgpa_history[-1] > cgpa_history[-2] else "declining" if len(cgpa_history) >= 2 and cgpa_history[-1] < cgpa_history[-2] else "stable"

    return f"""
CGPA: {profile.get('currentCGPA')} (Trend: {trend})
CGPA History: {cgpa_history}
Predicted: {profile.get('predictedCGPA')} (Range: {profile.get('predictedCGPARange', [])})
Semester: {profile.get('semester')}
Exam in: {profile.get('examDays')} days

At-Risk Subjects ({len(risk_subjects)}): {[s.get('name') + ' (Grade: ' + str(s.get('grade')) + ', Att: ' + str(s.get('attendance')) + '%)' for s in risk_subjects]}
Watch Subjects ({len(watch_subjects)}): {[s.get('name') for s in watch_subjects]}

Credit-weighted subjects: {[s.get('name') + '(' + str(s.get('creditWeight', 3)) + ' credits)' for s in subjects]}
"""


import numpy as np
from sklearn.linear_model import LinearRegression

def compute_predicted_cgpa(profile: dict, improvement: dict = None) -> dict:
    """
    Scikit-learn based CGPA prediction using Time-Series Linear Regression on historical data.
    improvement = { "attendance_delta": 10, "assignment_delta": 5, "study_hours_delta": 1 }
    """
    cgpa_history = profile.get("cgpaHistory", [])
    subjects = profile.get("subjects", [])

    # Default trend prediction to current CGPA so it's always defined,
    # even when there are not enough historical points for regression.
    trend_prediction = profile.get("currentCGPA", 0.0)

    if not cgpa_history or len(cgpa_history) < 2:
        # Fallback to simple average if not enough history
        base_predicted = trend_prediction
    else:
        # 1. Linear Regression on historical CGPA trend
        X = np.array(range(1, len(cgpa_history) + 1)).reshape(-1, 1)  # Semesters 1, 2, 3...
        y = np.array(cgpa_history)

        model = LinearRegression()
        model.fit(X, y)

        # Predict next semester
        next_sem_x = np.array([[len(cgpa_history) + 1]])
        trend_prediction = model.predict(next_sem_x)[0]

        # Calculate R-squared for confidence margin
        r_sq = model.score(X, y)
        base_predicted = trend_prediction

    # 2. Subject-Level Anomaly Detection (Standard Deviation)
    grades = [s.get("grade", 7.0) for s in subjects]
    attendances = [s.get("attendance", 80) for s in subjects]
    
    if grades:
        mean_grade = np.mean(grades)
        std_grade = np.std(grades)
        mean_att = np.mean(attendances)
        std_att = np.std(attendances)
        
        for s in subjects:
            g = s.get("grade", 7.0)
            a = s.get("attendance", 80)
            
            # Risk: Grade is > 1.5 standard deviations below their own mean, or absolute < 6.0
            # Risk: Attendance > 1.5 SD below mean or absolute < 75%
            grade_risk = (g < mean_grade - 1.5 * std_grade) or (g < 6.0)
            att_risk = (a < mean_att - 1.5 * std_att) or (a < 75)
            
            if grade_risk and att_risk:
                s["status"] = "risk"
            elif grade_risk or att_risk or (g < 7.0):
                s["status"] = "watch"
            else:
                s["status"] = "safe"
                
            # Individual subject predicted score
            subject_boost = 0.0
            if improvement:
                subject_boost += improvement.get("attendance_delta", 0) * 0.05
                subject_boost += improvement.get("study_hours_delta", 0) * 0.1
            
            s["predicted"] = round(min(10.0, g + subject_boost + (0.1 if trend_prediction > mean_grade else -0.1)), 1)

    # 3. Apply global improvement boosts if provided
    boost = 0.0
    if improvement:
        boost += improvement.get("attendance_delta", 0) * 0.008
        boost += improvement.get("assignment_delta", 0) * 0.005
        boost += improvement.get("study_hours_delta", 0) * 0.01

    final_predicted = round(min(10.0, base_predicted + boost), 2)
    # Range is tighter if R^2 is high (consistent student), wider if erratic
    margin = round(0.5 - (r_sq * 0.3 if 'r_sq' in locals() else 0.2), 1)
    
    return {
        "cgpa": final_predicted,
        "range": [round(max(0, final_predicted - margin), 1), round(min(10, final_predicted + margin), 1)]
    }
