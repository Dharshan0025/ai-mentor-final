"""
AI-Mentor orchestrator.

The live chat path uses a mentor-planning step first, then executes one or
more specialist agents, and finally synthesizes everything into one mentor
response.
"""
from __future__ import annotations

import inspect
import json
import logging
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph

from config import settings
from mentor_strategy import (
    build_history_summary,
    build_student_snapshot,
    merge_citations,
    pretty_json,
)

logger = logging.getLogger(__name__)

AVAILABLE_AGENTS = ("academic", "prediction", "emotional", "learning", "schedule", "career")
AVAILABLE_AGENT_SET = set(AVAILABLE_AGENTS)
DEFAULT_GREETING = "I'm here with you. Tell me what you're trying to handle right now, and I'll help you move it forward."


class AgentState(TypedDict):
    message: str
    session_id: str
    student_id: str
    lang: str
    history: list[dict]
    student_profile: dict
    learning_dna: dict
    student_snapshot: str
    intent: str
    agents_to_invoke: list[str]
    mentor_plan: dict
    academic_output: Optional[str]
    prediction_output: Optional[str]
    emotional_output: Optional[str]
    learning_output: Optional[str]
    schedule_output: Optional[str]
    career_output: Optional[str]
    rag_context: Optional[str]
    sentiment_score: float
    final_response: str
    ui_card: Optional[dict]          # NEW: generative UI widget for the chat
    suggested_actions: list[dict]    # NEW: CTA chips below the response
    xp_awarded: int                  # NEW: XP points earned this turn (0 if none)
    primary_agent: str
    citations: list[dict]
    tokens_used: int
    model_used: str
    models_used: list[str]


MENTOR_PLANNER_PROMPT = """You are the mentor planner for an adaptive AI mentor.

Your job is to decide the best mentoring move for THIS student, not just classify the message.

Return ONLY a valid JSON object with this schema:
{{
  "intent": "academic|prediction|emotional|learning|schedule|career|general",
  "primary_agent": "academic|prediction|emotional|learning|schedule|career",
  "supporting_agents": ["academic|prediction|emotional|learning|schedule|career"],
  "mentor_action": "answer|diagnose|teach|coach|plan|motivate|forecast|roadmap|redirect",
  "response_mode": "direct|guided|diagnostic|recovery|strategic|concise",
  "student_readiness": "fragile|foundational|steady|advanced",
  "should_use_empathy": true,
  "should_include_checkpoint": false,
  "should_include_plan": false,
  "personalization_focus": ["short phrase", "short phrase"],
  "reasoning": "one short sentence"
}}

Planner rules:
- Choose exactly 1 primary agent and up to 2 supporting agents.
- Think student-state first, message second.
- Use learning or academic for concept help and doubts.
- Add schedule when the student needs time management, sequencing, or a study plan.
- Add prediction only for forecast, risk, grade-outlook, or what-if questions.
- Add emotional when stress, overwhelm, pressure, or confidence issues are present.
- Use career only for jobs, internships, skills, resume, roadmap, or placement strategy.
- If the student seems weak, confused, or at risk, prefer guided or diagnostic modes over dense direct answers.
- If the message is simple social small talk, keep it concise and still choose the best primary mentor agent.

Student snapshot:
{student_snapshot}

Recent chat context:
{history_summary}

Latest student message:
{message}
"""


MENTOR_SYNTHESIS_PROMPT = """You are the final response composer for a world-class AI mentor.

You are not a generic chatbot. You must sound like one coherent mentor who:
- understands this student's capacity and pressure
- gives the most useful next move
- teaches or coaches at the right depth
- never mentions agents, routing, or internal system details

Student snapshot:
{student_snapshot}

Mentor plan:
{mentor_plan}

Latest student message:
{message}

Language:
{lang}

Specialist outputs:
{agent_outputs}

Write one cohesive response that follows these rules:
- Answer the student's real need first.
- Adapt to the student's readiness level from the mentor plan.
- If empathy is needed, validate briefly and then guide.
- If a micro-plan is needed, include a short 2-3 step plan.
- If a checkpoint is needed, end with exactly one short check question or action prompt.
- Use clear `##` section headings when the answer has multiple parts.
- When presenting comparisons, metrics, subject lists, timelines, or priority breakdowns, prefer a markdown table with short cell text.
- Use concise markdown with short paragraphs and flat bullets only when helpful.
- Avoid cliches, generic motivation, and long lectures.
- Maximum 450 words.
- If lang is ta, respond in Tamil. Otherwise respond in English.

After the prose response, output a JSON block delimited EXACTLY like this:
```ui_metadata
{{"ui_card": null_or_object, "suggested_actions": [{{"label": "...", "prompt": "...", "icon": "..."}}]}}
```
Rules for ui_card:
- If the response contains a study schedule → {{"type": "schedule_card", "data": {{"days": [...]}}}}
- If the response contains a grade/CGPA forecast → {{"type": "prediction_card", "data": {{"current": X, "predicted": Y}}}}
- If the response proposes a quiz/checkpoint question → {{"type": "quiz_widget", "data": {{"question": "...", "subject": "..."}}}}
- If the response lists subject risk status → {{"type": "subject_status", "data": {{"subjects": [...]}}}}
- If the response explains a complex diagrammable concept (architecture, process, life-cycle) → {{"type": "concept_board", "data": {{"keyword": "topic_name", "code": "valid_mermaid_diagram_code"}}}}
- Otherwise → null
Rules for suggested_actions: provide 2-3 short next-step prompts the student can tap to continue.
Icon options: 📅 📊 🧠 📝 💼 ❤️ 🧪 🎯
"""


def _extract_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(text[start : end + 1])


def _fallback_plan(state: AgentState) -> dict:
    message = (state.get("message") or "").lower()
    profile = state.get("student_profile") or {}
    subjects = profile.get("subjects") or []
    risk_count = len([s for s in subjects if str(s.get("status") or "").lower() == "risk"])

    primary_agent = "academic"
    intent = "academic"
    mentor_action = "coach"
    response_mode = "guided"

    if any(word in message for word in ["internship", "placement", "career", "job", "resume"]):
        primary_agent = "career"
        intent = "career"
        mentor_action = "roadmap"
        response_mode = "strategic"
    elif any(word in message for word in ["schedule", "timetable", "plan", "routine", "time table", "study plan"]):
        primary_agent = "schedule"
        intent = "schedule"
        mentor_action = "plan"
        response_mode = "strategic"
    elif any(word in message for word in ["predict", "cgpa", "gpa", "score", "will i pass", "what if"]):
        primary_agent = "prediction"
        intent = "prediction"
        mentor_action = "forecast"
        response_mode = "strategic"
    elif any(word in message for word in ["stress", "anxious", "overwhelmed", "burnout", "frustrated", "scared", "tired"]):
        primary_agent = "emotional"
        intent = "emotional"
        mentor_action = "motivate"
        response_mode = "recovery"
    elif any(word in message for word in ["explain", "teach", "how", "why", "what is", "doubt", "understand"]):
        primary_agent = "learning"
        intent = "learning"
        mentor_action = "teach"
        response_mode = "guided"

    supporting_agents: list[str] = []
    if primary_agent in {"academic", "learning"}:
        supporting_agents.append("academic" if primary_agent == "learning" else "learning")
    if primary_agent in {"prediction", "career"}:
        supporting_agents.append("schedule")

    should_use_empathy = primary_agent == "emotional" or any(
        word in message for word in ["can't", "cannot", "stuck", "confused", "stress", "overwhelmed", "fail"]
    )
    if should_use_empathy and primary_agent != "emotional":
        supporting_agents.insert(0, "emotional")

    should_include_checkpoint = primary_agent in {"academic", "learning"} and any(
        word in message for word in ["explain", "teach", "understand", "how", "why", "doubt"]
    )
    should_include_plan = primary_agent in {"schedule", "prediction", "career"} or any(
        phrase in message for phrase in ["what should i do", "next step", "how do i improve", "plan for"]
    )

    if risk_count >= 2 and should_use_empathy:
        student_readiness = "fragile"
    elif risk_count >= 1 or primary_agent in {"academic", "learning"}:
        student_readiness = "foundational"
    else:
        student_readiness = "steady"

    return {
        "intent": intent,
        "primary_agent": primary_agent,
        "supporting_agents": supporting_agents[:2],
        "mentor_action": mentor_action,
        "response_mode": response_mode,
        "student_readiness": student_readiness,
        "should_use_empathy": should_use_empathy,
        "should_include_checkpoint": should_include_checkpoint,
        "should_include_plan": should_include_plan,
        "personalization_focus": [
            "risk subjects" if risk_count else "current goals",
            "learning style",
            "exam proximity",
        ],
        "reasoning": "Fallback heuristic selected the mentor path from message signals and student risk.",
    }


def _normalize_plan(plan: dict, state: AgentState) -> dict:
    fallback = _fallback_plan(state)
    primary_agent = str(plan.get("primary_agent") or fallback["primary_agent"]).strip().lower()
    if primary_agent not in AVAILABLE_AGENT_SET:
        primary_agent = fallback["primary_agent"]

    intent = str(plan.get("intent") or primary_agent or fallback["intent"]).strip().lower()
    if intent not in {"academic", "prediction", "emotional", "learning", "schedule", "career", "general"}:
        intent = fallback["intent"]

    raw_support = plan.get("supporting_agents") or []
    if not isinstance(raw_support, list):
        raw_support = []
    supporting_agents: list[str] = []
    for agent in raw_support:
        agent_name = str(agent).strip().lower()
        if agent_name in AVAILABLE_AGENT_SET and agent_name != primary_agent and agent_name not in supporting_agents:
            supporting_agents.append(agent_name)

    message = (state.get("message") or "").lower()
    if primary_agent in {"academic", "learning"} and any(
        phrase in message for phrase in ["study plan", "schedule", "time table", "routine"]
    ):
        supporting_agents.append("schedule")
    if primary_agent != "emotional" and any(
        phrase in message for phrase in ["stress", "stressed", "overwhelmed", "anxious", "frustrated", "confused"]
    ):
        supporting_agents.insert(0, "emotional")

    deduped_support: list[str] = []
    for agent in supporting_agents:
        if agent != primary_agent and agent not in deduped_support:
            deduped_support.append(agent)

    return {
        "intent": intent,
        "primary_agent": primary_agent,
        "supporting_agents": deduped_support[:2],
        "mentor_action": str(plan.get("mentor_action") or fallback["mentor_action"]).strip().lower(),
        "response_mode": str(plan.get("response_mode") or fallback["response_mode"]).strip().lower(),
        "student_readiness": str(plan.get("student_readiness") or fallback["student_readiness"]).strip().lower(),
        "should_use_empathy": bool(plan.get("should_use_empathy", fallback["should_use_empathy"])),
        "should_include_checkpoint": bool(plan.get("should_include_checkpoint", fallback["should_include_checkpoint"])),
        "should_include_plan": bool(plan.get("should_include_plan", fallback["should_include_plan"])),
        "personalization_focus": plan.get("personalization_focus") or fallback["personalization_focus"],
        "reasoning": str(plan.get("reasoning") or fallback["reasoning"]).strip(),
    }


def plan_mentor_response_node(state: AgentState) -> AgentState:
    snapshot = state.get("student_snapshot") or build_student_snapshot(
        state.get("student_profile"), state.get("learning_dna")
    )
    history_summary = build_history_summary(state.get("history"))

    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.1,
        max_tokens=350,
    )

    prompt = MENTOR_PLANNER_PROMPT.format(
        student_snapshot=snapshot,
        history_summary=history_summary,
        message=state["message"],
    )

    try:
        result = llm.invoke([HumanMessage(content=prompt)])
        parsed = _extract_json_object(result.content)
    except Exception as exc:
        logger.warning("Mentor planner failed, using fallback plan: %s", exc)
        parsed = _fallback_plan(state)

    mentor_plan = _normalize_plan(parsed, state)
    agents = [mentor_plan["primary_agent"], *mentor_plan.get("supporting_agents", [])]
    ordered_agents: list[str] = []
    for agent in agents:
        if agent in AVAILABLE_AGENT_SET and agent not in ordered_agents:
            ordered_agents.append(agent)

    return {
        **state,
        "student_snapshot": snapshot,
        "intent": mentor_plan["intent"],
        "mentor_plan": mentor_plan,
        "agents_to_invoke": ordered_agents,
    }


def _merge_agent_state(current_state: AgentState, update: dict) -> AgentState:
    merged: AgentState = {**current_state, **update}
    merged["citations"] = merge_citations(current_state.get("citations"), update.get("citations"))

    models_used = list(current_state.get("models_used") or [])
    candidate_model = str(update.get("model_used") or "").strip()
    if candidate_model:
        for part in [item.strip() for item in candidate_model.split(",") if item.strip()]:
            if part not in models_used:
                models_used.append(part)
    merged["models_used"] = models_used
    if models_used:
        merged["model_used"] = ", ".join(models_used)
    return merged


async def _call_agent(node, state: AgentState) -> dict:
    result = node(state)
    if inspect.isawaitable(result):
        return await result
    return result


async def run_selected_agents_node(state: AgentState) -> AgentState:
    from agents.academic import academic_node
    from agents.career import career_node
    from agents.emotional import emotional_node
    from agents.learning import learning_node
    from agents.prediction import prediction_node
    from agents.schedule import schedule_node

    agent_map = {
        "academic": academic_node,
        "prediction": prediction_node,
        "emotional": emotional_node,
        "learning": learning_node,
        "schedule": schedule_node,
        "career": career_node,
    }

    working_state = dict(state)
    try:
        emotional_update = emotional_node(working_state)
        working_state = _merge_agent_state(working_state, emotional_update)
    except Exception as exc:
        logger.warning("Emotional agent pre-pass failed: %s", exc)

    selected_agents = list(state.get("agents_to_invoke") or [])
    mentor_plan = state.get("mentor_plan") or {}
    primary_agent = mentor_plan.get("primary_agent", "academic")

    if (
        mentor_plan.get("should_use_empathy")
        or working_state.get("sentiment_score", 0.0) <= -0.45
    ) and "emotional" not in selected_agents:
        selected_agents.insert(1 if primary_agent != "emotional" else 0, "emotional")

    ordered_agents: list[str] = []
    for agent in [primary_agent, *selected_agents]:
        if agent in AVAILABLE_AGENT_SET and agent not in ordered_agents:
            ordered_agents.append(agent)

    if not ordered_agents:
        ordered_agents = ["academic"]

    for agent in ordered_agents:
        if agent == "emotional":
            continue
        try:
            update = await _call_agent(agent_map[agent], working_state)
            working_state = _merge_agent_state(working_state, update)
        except Exception as exc:
            logger.warning("%s agent failed during mentor workflow: %s", agent, exc)

    primary_output_key = f"{primary_agent}_output"
    if not working_state.get(primary_output_key):
        for fallback_agent in ("academic", "learning", "prediction", "schedule", "career", "emotional"):
            if working_state.get(f"{fallback_agent}_output"):
                primary_agent = fallback_agent
                break

    return {
        **working_state,
        "agents_to_invoke": ordered_agents,
        "primary_agent": primary_agent,
        "model_used": ", ".join(working_state.get("models_used") or []) or settings.groq_model,
    }


def _parse_ui_metadata(raw: str) -> tuple[str, dict | None, list]:
    """Strip ```ui_metadata block from LLM response, parse it, return (prose, ui_card, suggested_actions)."""
    ui_card = None
    suggested_actions = []
    prose = raw

    marker_start = "```ui_metadata"
    marker_end = "```"
    if marker_start in raw:
        parts = raw.split(marker_start, 1)
        prose = parts[0].strip()
        rest = parts[1]
        json_block = rest.split(marker_end, 1)[0].strip()
        try:
            meta = json.loads(json_block)
            ui_card = meta.get("ui_card")
            suggested_actions = meta.get("suggested_actions") or []
        except json.JSONDecodeError:
            pass  # ui_metadata is optional — never break the response

    return prose, ui_card, suggested_actions


def merge_response_node(state: AgentState) -> AgentState:
    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.3,
        max_tokens=900,  # increased to accommodate ui_metadata block
    )

    outputs_map = {
        "academic": state.get("academic_output"),
        "prediction": state.get("prediction_output"),
        "emotional": state.get("emotional_output"),
        "learning": state.get("learning_output"),
        "schedule": state.get("schedule_output"),
        "career": state.get("career_output"),
    }
    filled = {name: output for name, output in outputs_map.items() if output}

    if not filled:
        return {
            **state,
            "final_response": DEFAULT_GREETING,
            "ui_card": None,
            "suggested_actions": [],
            "xp_awarded": 0,
            "primary_agent": "academic",
            "citations": state.get("citations", []),
            "tokens_used": state.get("tokens_used", 0),
            "model_used": ", ".join(state.get("models_used") or []) or settings.groq_model,
        }

    agent_outputs_str = "\n\n".join(
        f"[{agent.upper()}]\n{output}" for agent, output in filled.items()
    )

    primary_agent = state.get("mentor_plan", {}).get("primary_agent") or state.get("primary_agent") or "academic"
    if primary_agent not in filled:
        primary_agent = next(iter(filled.keys()))

    models_used = list(state.get("models_used") or [])
    if settings.groq_model not in models_used:
        models_used.append(settings.groq_model)

    prompt = MENTOR_SYNTHESIS_PROMPT.format(
        student_snapshot=state.get("student_snapshot") or build_student_snapshot(
            state.get("student_profile"), state.get("learning_dna")
        ),
        mentor_plan=pretty_json(state.get("mentor_plan") or {}),
        message=state["message"],
        lang=state.get("lang", "en"),
        agent_outputs=agent_outputs_str,
    )

    try:
        result = llm.invoke([HumanMessage(content=prompt)])
        raw_response = result.content.strip() or DEFAULT_GREETING
    except Exception as exc:
        logger.warning("Mentor synthesis failed, using fallback response: %s", exc)
        ordered_outputs = []
        for agent in [primary_agent, *filled.keys()]:
            if agent in filled and filled[agent] not in ordered_outputs:
                ordered_outputs.append(filled[agent])
        raw_response = "\n\n".join(ordered_outputs[:2]) if ordered_outputs else DEFAULT_GREETING

    prose, ui_card, suggested_actions = _parse_ui_metadata(raw_response)

    # XP heuristic: award 10 XP for analytical/evaluative questions (Bloom L4+)
    message_lower = (state.get("message") or "").lower()
    xp_awarded = 10 if any(kw in message_lower for kw in [
        "why", "compare", "evaluate", "analyze", "design", "create", "tradeoff", "difference between"
    ]) else 0

    return {
        **state,
        "final_response": prose,
        "ui_card": ui_card,
        "suggested_actions": suggested_actions,
        "xp_awarded": xp_awarded,
        "primary_agent": primary_agent,
        "citations": state.get("citations", []),
        "tokens_used": state.get("tokens_used", 0),
        "model_used": ", ".join(models_used),
        "models_used": models_used,
    }



def build_orchestrator_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan_mentor_response", plan_mentor_response_node)
    graph.add_node("run_selected_agents", run_selected_agents_node)
    graph.add_node("merge_response", merge_response_node)

    graph.set_entry_point("plan_mentor_response")
    graph.add_edge("plan_mentor_response", "run_selected_agents")
    graph.add_edge("run_selected_agents", "merge_response")
    graph.add_edge("merge_response", END)
    return graph.compile()


_graph = None


def get_orchestrator():
    global _graph
    if _graph is None:
        _graph = build_orchestrator_graph()
    return _graph
