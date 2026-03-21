"""
AI-Mentor — Emotional Intelligence Agent
Handles: stress detection, motivation, burnout signals,
         empathetic support, mental health nudges
LLM: NVIDIA NIM (llama-3.3-70b-instruct) with Groq fallback
"""
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings
import logging

logger = logging.getLogger(__name__)


def _get_llm(temperature: float = 0.5, max_tokens: int = 400):
    """Return NVIDIA NIM LLM first, fall back to Groq."""
    if settings.nvidia_api_key:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                api_key=settings.nvidia_api_key,
                base_url=settings.nvidia_base_url,
                model=settings.nvidia_model,
                temperature=temperature,
                max_tokens=max_tokens,
            ), "nvidia"
        except Exception as e:
            logger.warning(f"NVIDIA NIM init failed ({e}), using Groq")
    from langchain_groq import ChatGroq
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=temperature,
        max_tokens=max_tokens,
    ), "groq"



EMOTIONAL_SYSTEM = """You are the Emotional Intelligence Agent for an AI academic mentor.

Your role:
- Detect stress, burnout, anxiety, and academic pressure in the student's message
- Validate the student's feelings before giving advice
- Offer practical, evidence-based coping strategies
- Know when to recommend professional counseling (if crisis signals)
- Keep the student motivated without being toxic-positive

Tone principles:
- Warm, non-judgmental, peer-like (not authoritative)
- Say "I understand how that feels" before advice
- Never minimize: "Don't worry" is BANNED — validate first
- Offer ONE specific action, not a list of 10 things to change
- End with an encouragement connected to their academic context

Student academic context:
{student_context}

Crisis signals that require professional referral:
- Mentions of self-harm, hopelessness, giving up entirely
- If detected → "I'm worried about you. Please talk to your campus counselor today."

Rules:
- Maximum 250 words
- If the message is purely academic (not emotional), return an empty string
- Always begin with emotional validation before any advice"""


# ── Keyword Signal Tables ─────────────────────────────────────────────────────
# Positive signals → push score toward +1.0
_POSITIVE_SIGNALS = {
    "happy": 0.7, "excited": 0.8, "great": 0.6, "awesome": 0.7,
    "love": 0.6, "confident": 0.75, "motivated": 0.8, "proud": 0.7,
    "understood": 0.5, "clear": 0.4, "good": 0.4, "thanks": 0.5,
    "thank you": 0.5, "excellent": 0.7, "perfect": 0.7, "achieved": 0.75,
    "passed": 0.8, "cleared": 0.7, "easy": 0.4, "fun": 0.6,
    "better": 0.5, "improved": 0.6, "progress": 0.6, "got it": 0.5,
}

# Negative signals → push score toward -1.0
_NEGATIVE_SIGNALS = {
    "stress": -0.6, "stressed": -0.65, "anxious": -0.7, "anxiety": -0.7,
    "worried": -0.55, "scared": -0.65, "depressed": -0.85, "depression": -0.85,
    "overwhelmed": -0.75, "can't": -0.4, "cannot": -0.4, "tired": -0.5,
    "exhausted": -0.7, "burnout": -0.8, "fail": -0.6, "failed": -0.65,
    "give up": -0.85, "hate": -0.65, "frustrated": -0.65, "fear": -0.6,
    "nervous": -0.55, "hopeless": -0.9, "alone": -0.6, "help me": -0.5,
    "too much": -0.55, "confused": -0.45, "lost": -0.5, "difficult": -0.35,
    "hard": -0.3, "struggle": -0.6, "stuck": -0.5, "terrible": -0.7,
    "horrible": -0.75, "bad": -0.5, "sad": -0.65, "cry": -0.7,
    "crying": -0.7, "not good": -0.55, "won't pass": -0.7,
}

# Intensity amplifiers
_AMPLIFIERS = {"very": 1.3, "extremely": 1.5, "really": 1.2, "so": 1.15, "too": 1.2}


def extract_sentiment_score(message: str) -> float:
    """
    Compute a sentiment score in [-1.0, +1.0] from student message text.
    Uses weighted keyword matching with amplifier detection.
    Neutral messages return 0.0.
    """
    words = message.lower().split()
    total_score = 0.0
    count = 0
    amplifier = 1.0

    for i, word in enumerate(words):
        # Check for amplifier on the previous word
        if word in _AMPLIFIERS:
            amplifier = _AMPLIFIERS[word]
            continue

        # Check single word signals (positive then negative)
        score = None
        if word in _POSITIVE_SIGNALS:
            score = _POSITIVE_SIGNALS[word]
        elif word in _NEGATIVE_SIGNALS:
            score = _NEGATIVE_SIGNALS[word]

        # Check two-word phrases
        if i < len(words) - 1:
            phrase = f"{word} {words[i + 1]}"
            if phrase in _POSITIVE_SIGNALS:
                score = _POSITIVE_SIGNALS[phrase]
            elif phrase in _NEGATIVE_SIGNALS:
                score = _NEGATIVE_SIGNALS[phrase]

        if score is not None:
            total_score += score * amplifier
            count += 1
            amplifier = 1.0  # reset after use

    if count == 0:
        return 0.0  # neutral — no signal detected

    # Average and clamp to [-1, 1]
    avg = total_score / count
    return round(max(-1.0, min(1.0, avg)), 3)


def emotional_node(state: dict) -> dict:
    """Emotional intelligence agent — empathy, mental wellness, plus sentiment scoring."""
    message = state["message"]

    # Always compute sentiment score — persisted regardless of agent activation
    sentiment_score = extract_sentiment_score(message)

    # Quick check: is this actually an emotional message?
    emotional_keywords = [
        "stress", "anxious", "anxiety", "worried", "scared", "depressed",
        "overwhelmed", "can't", "cannot", "tired", "exhausted", "burnout",
        "fail", "give up", "hate", "frustrated", "fear", "nervous",
        "hopeless", "pressure", "alone", "help me", "too much"
    ]
    message_lower = message.lower()
    has_emotional_content = any(kw in message_lower for kw in emotional_keywords)

    if not has_emotional_content:
        # Still expose sentiment_score for write-back — just no LLM response
        return {**state, "emotional_output": None, "sentiment_score": sentiment_score}

    llm, provider = _get_llm()

    profile = state.get("student_profile", {})
    context = _format_emotional_context(profile)

    system_prompt = EMOTIONAL_SYSTEM.format(student_context=context)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=message),
    ]

    result = llm.invoke(messages)

    return {
        **state,
        "emotional_output": result.content,
        "sentiment_score": sentiment_score,
        "model_used": provider,
    }


def _format_emotional_context(profile: dict) -> str:
    """Minimal context for emotional empathy — no grade pressure."""
    if not profile:
        return "Student is in their final year of engineering."

    risk_count = len([s for s in profile.get("subjects", []) if s.get("status") == "risk"])
    return f"""
Department: {profile.get('department', 'Engineering')}
Current semester: {profile.get('semester', '?')} of 8
Subjects needing attention: {risk_count}
Exam in: {profile.get('examDays', '?')} days
Study streak: {profile.get('studyStreak', 0)} days
"""


