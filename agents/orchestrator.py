"""
AI-Mentor — LangGraph Orchestrator
Multi-agent state machine that routes student queries
to the best specialist agent(s) and merges the response.

Flow:
  classify_intent
       ↓
  [academic | prediction | emotional | learning | schedule | career | rag]
       ↓
  merge_response
       ↓
  final output (SSE stream)
"""
from __future__ import annotations
from typing import TypedDict, Annotated, Optional
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import operator
import json
import logging

from config import settings
from schemas import AgentId, Language, ChatMessage

logger = logging.getLogger(__name__)


# ── Agent State ─────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    message: str
    session_id: str
    student_id: str
    lang: str
    history: list[dict]

    # Student context (loaded from DB or mock)
    student_profile: dict

    # Routing
    intent: str                # Which agent(s) should handle this
    agents_to_invoke: list[str]

    # Outputs from each agent
    academic_output:    Optional[str]
    prediction_output:  Optional[str]
    emotional_output:   Optional[str]
    learning_output:    Optional[str]
    schedule_output:    Optional[str]
    career_output:      Optional[str]
    rag_context:        Optional[str]

    # Sentiment (computed by emotional_node on every message)
    sentiment_score:    float

    # Final merged response
    final_response:     str
    primary_agent:      str
    citations:          list[dict]
    tokens_used:        int
    model_used:         str


# ── Intent Classification ───────────────────────────────────────────────────

INTENT_PROMPT = """You are an intent classifier for an academic AI mentor.
Given a student's message, return ONLY a JSON object with:
- "intent": one of [academic, prediction, emotional, learning, schedule, career, general]
- "agents": array of agents to invoke (pick 1-2 most relevant)
- "reasoning": brief explanation (1 sentence)

Agents available:
- academic: subject questions, grades, ERP data lookup, exam tips
- prediction: CGPA forecast, score predictions, risk assessment, scenarios
- emotional: stress, anxiety, motivation, mental wellness
- learning: explanations, quizzes, study material, Bloom's taxonomy
- schedule: study plan, timetable, time management
- career: internships, placements, career guidance (only for career queries)
- general: greetings, simple factual questions

Student message: {message}

Respond ONLY with valid JSON, no markdown."""


def classify_intent_node(state: AgentState) -> AgentState:
    """Route query to appropriate specialist agents."""
    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0,
        max_tokens=200,
    )

    prompt = INTENT_PROMPT.format(message=state["message"])
    result = llm.invoke([HumanMessage(content=prompt)])

    try:
        parsed = json.loads(result.content.strip())
        intent = parsed.get("intent", "general")
        agents = parsed.get("agents", ["academic"])
    except json.JSONDecodeError:
        logger.warning("Intent classification failed to parse JSON, defaulting to academic")
        intent = "general"
        agents = ["academic"]

    return {
        **state,
        "intent": intent,
        "agents_to_invoke": agents,
    }


# ── Routing Logic ────────────────────────────────────────────────────────────

def route_to_agents(state: AgentState) -> str:
    """Conditional edge — decides which agent node runs next."""
    agents = state.get("agents_to_invoke", ["academic"])

    # Priority routing — run the most important agent first
    priority_order = ["academic", "prediction", "emotional", "learning", "schedule", "career"]
    for agent in priority_order:
        if agent in agents:
            return agent

    return "academic"


# ── Merge Node ─────────────────────────────────────────────────────────────

MERGE_PROMPT = """You are a senior AI academic advisor synthesizing a response for a student.

Student question: {message}
Language: {lang}

Agent outputs:
{agent_outputs}

Merge these into ONE cohesive, helpful response. Requirements:
- Use markdown formatting (bold key terms, bullet points for lists)
- Be empathetic and encouraging, not clinical
- If multiple agents contributed, blend seamlessly — no "According to Agent X..."
- Maximum 400 words
- If Tamil (ta), respond in Tamil; otherwise English
- Add a brief follow-up offer at the end"""

def merge_response_node(state: AgentState) -> AgentState:
    """Combine outputs from all invoked agents into a final response."""
    from langchain_groq import ChatGroq

    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.4,
        max_tokens=600,
    )

    # Collect all non-null agent outputs
    outputs_map = {
        "academic":   state.get("academic_output"),
        "prediction": state.get("prediction_output"),
        "emotional":  state.get("emotional_output"),
        "learning":   state.get("learning_output"),
        "schedule":   state.get("schedule_output"),
        "career":     state.get("career_output"),
    }
    filled = {k: v for k, v in outputs_map.items() if v}

    if not filled:
        return {**state, "final_response": "I'm here to help! Could you tell me more about what you need assistance with?", "primary_agent": "academic", "citations": [], "tokens_used": 0, "model_used": settings.groq_model}

    agent_outputs_str = "\n\n".join(
        f"[{agent.upper()} AGENT]:\n{output}" for agent, output in filled.items()
    )

    # If only one agent ran, skip merging (saves tokens)
    if len(filled) == 1:
        primary = list(filled.keys())[0]
        return {
            **state,
            "final_response": list(filled.values())[0],
            "primary_agent": primary,
            "citations": state.get("citations", []),
            "tokens_used": state.get("tokens_used", 0),
            "model_used": settings.groq_model,
        }

    prompt = MERGE_PROMPT.format(
        message=state["message"],
        lang=state.get("lang", "en"),
        agent_outputs=agent_outputs_str,
    )
    result = llm.invoke([HumanMessage(content=prompt)])

    return {
        **state,
        "final_response":  result.content,
        "primary_agent":   list(filled.keys())[0],
        "citations":       state.get("citations", []),
        "tokens_used":     state.get("tokens_used", 0),
        "model_used":      settings.groq_model,
    }


# ── Graph Construction ───────────────────────────────────────────────────────

def build_orchestrator_graph():
    """
    Build and compile the LangGraph multi-agent orchestration graph.
    
    Graph structure:
      START → classify_intent → [agent routes] → merge_response → END
    """
    from agents.academic    import academic_node
    from agents.prediction  import prediction_node
    from agents.emotional   import emotional_node
    from agents.learning    import learning_node
    from agents.schedule    import schedule_node
    from agents.career      import career_node

    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("classify_intent",   classify_intent_node)
    graph.add_node("merge_response",    merge_response_node)
    graph.add_node("academic",          academic_node)
    graph.add_node("prediction",        prediction_node)
    graph.add_node("emotional",         emotional_node)
    graph.add_node("learning",          learning_node)
    graph.add_node("schedule",          schedule_node)
    graph.add_node("career",            career_node)

    # Entry
    graph.set_entry_point("classify_intent")

    # Intent → agent routing (conditional edge)
    graph.add_conditional_edges(
        "classify_intent",
        route_to_agents,
        {
            "academic":   "academic",
            "prediction": "prediction",
            "emotional":  "emotional",
            "learning":   "learning",
            "schedule":   "schedule",
            "career":     "career",
            "general":    "academic",
        }
    )

    # All agents → merge
    for agent in ["academic", "prediction", "emotional", "learning", "schedule", "career"]:
        graph.add_edge(agent, "merge_response")

    graph.add_edge("merge_response", END)

    return graph.compile()


# Singleton compiled graph
_graph = None

def get_orchestrator():
    global _graph
    if _graph is None:
        _graph = build_orchestrator_graph()
    return _graph
