"""
Shared helpers for mentor planning and response personalization.
"""
from __future__ import annotations

import json
from typing import Any


def _coalesce(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _format_topic_list(items: list[Any], limit: int = 3) -> str:
    names: list[str] = []
    for item in items[:limit]:
        if isinstance(item, str):
            label = item.strip()
        elif isinstance(item, dict):
            label = str(
                item.get("topic")
                or item.get("name")
                or item.get("subject_name")
                or item.get("subject_code")
                or ""
            ).strip()
        else:
            label = str(item).strip()
        if label:
            names.append(label)
    return ", ".join(names) if names else "None noted"


def build_student_snapshot(profile: dict | None, learning_dna: dict | None = None) -> str:
    profile = profile or {}
    learning_dna = learning_dna or {}
    subjects = profile.get("subjects") or profile.get("subject_profiles") or []

    semester = _coalesce(profile.get("semester"), profile.get("current_semester"), default="N/A")
    department = _coalesce(profile.get("department"), default="Engineering")
    current_cgpa = _coalesce(
        profile.get("currentCGPA"),
        profile.get("current_cgpa"),
        profile.get("cgpa"),
        default="N/A",
    )
    exam_days = _coalesce(profile.get("examDays"), profile.get("exam_days"), default="N/A")
    attendance = _coalesce(
        profile.get("attendanceOverall"),
        profile.get("attendance_overall"),
        default="N/A",
    )
    streak = _coalesce(profile.get("studyStreak"), profile.get("study_streak"), default=0)

    risk_subjects: list[str] = []
    watch_subjects: list[str] = []
    strong_subjects: list[str] = []

    for subject in subjects[:8]:
        name = str(subject.get("name") or subject.get("subject_name") or subject.get("code") or "Unknown")
        grade = _coalesce(subject.get("grade"), subject.get("current_grade"), default="N/A")
        att = _coalesce(subject.get("live_attendance"), subject.get("attendance"), default="N/A")
        bloom = _coalesce(subject.get("bloomLevel"), subject.get("bloom_level"), default="N/A")
        descriptor = f"{name} (grade {grade}, attendance {att}%, bloom {bloom}/6)"
        status = str(subject.get("status") or "").lower()
        if status == "risk":
            risk_subjects.append(descriptor)
        elif status == "watch":
            watch_subjects.append(descriptor)
        elif status == "safe" and len(strong_subjects) < 3:
            strong_subjects.append(descriptor)

    style = learning_dna.get("preferred_style") or "balanced"
    peak_hour = learning_dna.get("peak_hour")
    weak_topics = _format_topic_list(learning_dna.get("weak_topics") or [])
    strong_topics = _format_topic_list(learning_dna.get("strong_topics") or [])

    lines = [
        f"Department: {department}",
        f"Semester: {semester}",
        f"Current CGPA: {current_cgpa}",
        f"Overall attendance: {attendance}%",
        f"Exam window: {exam_days} days away",
        f"Study streak: {streak} days",
        f"At-risk subjects: {'; '.join(risk_subjects[:3]) if risk_subjects else 'None currently flagged'}",
        f"Watch subjects: {'; '.join(watch_subjects[:3]) if watch_subjects else 'None currently flagged'}",
        f"Strong subjects: {'; '.join(strong_subjects[:3]) if strong_subjects else 'Not enough data'}",
        f"Preferred learning style: {style}",
        f"Peak study hour: {f'{peak_hour}:00' if peak_hour is not None else 'Unknown'}",
        f"Weak topics from learning history: {weak_topics}",
        f"Strong topics from learning history: {strong_topics}",
    ]
    return "\n".join(lines)


def build_history_summary(history: list[dict] | None, max_turns: int = 6) -> str:
    history = history or []
    lines: list[str] = []
    for message in history[-max_turns:]:
        role = str(message.get("role") or "user").strip()
        content = " ".join(str(message.get("content") or "").split())
        if not content:
            continue
        if len(content) > 140:
            content = content[:137] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "No recent mentor-chat context."


def build_mentor_brief(state: dict) -> str:
    plan = state.get("mentor_plan") or {}
    if not plan:
        return ""

    focus_items = plan.get("personalization_focus") or []
    focus_text = ", ".join(str(item) for item in focus_items if str(item).strip()) or "student progress"
    support_agents = plan.get("supporting_agents") or []
    support_text = ", ".join(str(agent) for agent in support_agents if str(agent).strip()) or "none"

    lines = [
        f"Primary mentor action: {plan.get('mentor_action', 'guide')}",
        f"Response mode: {plan.get('response_mode', 'guided')}",
        f"Student readiness: {plan.get('student_readiness', 'steady')}",
        f"Primary agent: {plan.get('primary_agent', state.get('primary_agent', 'academic'))}",
        f"Supporting agents: {support_text}",
        f"Personalization focus: {focus_text}",
        f"Use empathy: {bool(plan.get('should_use_empathy', False))}",
        f"Include checkpoint: {bool(plan.get('should_include_checkpoint', False))}",
        f"Include micro-plan: {bool(plan.get('should_include_plan', False))}",
    ]
    return "\n".join(lines)


def merge_citations(existing: list[dict] | None, new: list[dict] | None, limit: int = 8) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for citation in (existing or []) + (new or []):
        if not isinstance(citation, dict):
            continue
        label = str(citation.get("label") or "").strip()
        source = str(citation.get("source") or "").strip()
        key = (label, source)
        if not label or key in seen:
            continue
        seen.add(key)
        merged.append({"label": label, "source": source})
        if len(merged) >= limit:
            break
    return merged


def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)
