"""
Adaptive Explanation Engine — Phase 6 V8 Behavioral Intelligence
Classifies student emotional/cognitive state from hesitation + checkpoint data,
then produces a teaching directive for TutorGraph.
"""
import logging

logger = logging.getLogger(__name__)

# ── Emotion State Classification ─────────────────────────────────────────────

def classify_emotion_state(
    checkpoint_score: float,       # 0.0 – 1.0
    hesitation_data: dict,          # { hesitation_score, deletion_ratio, pause_count, blank_stare_ms }
) -> str:
    """
    Classify student cognitive/emotional state from behavioral signals.

    States: confused | confident | overconfident | careful | struggling | engaged
    """
    hs         = float(hesitation_data.get("hesitation_score", 50))
    del_ratio  = float(hesitation_data.get("deletion_ratio", 0))
    pause_cnt  = int(hesitation_data.get("pause_count", 0))
    blank_ms   = int(hesitation_data.get("blank_stare_ms", 0))
    correct    = checkpoint_score >= 0.7

    # Confused: high hesitation + wrong answer
    if not correct and hs > 65:
        return "confused"

    # Struggling: high deletion + blank stare + wrong
    if not correct and del_ratio > 0.35 and blank_ms > 6000:
        return "struggling"

    # Overconfident: fast answer (low hesitation) + wrong
    if not correct and hs < 30 and blank_ms < 2000:
        return "overconfident"

    # Careful: slow, high deletion, but correct (thinking deeply)
    if correct and del_ratio > 0.25 and blank_ms > 4000:
        return "careful"

    # Confident: fast + correct + minimal hesitation
    if correct and hs < 35 and pause_cnt <= 1:
        return "confident"

    # Engaged: correct with moderate hesitation (healthy thinking)
    if correct:
        return "engaged"

    return "confused"


# ── Teaching Directive Generator ─────────────────────────────────────────────

DIRECTIVES = {
    "confused": {
        "explanation_mode":  "analogy",
        "language_level":    "simplified",
        "bloom_adjustment":  -1,           # Step back one level
        "scaffold":          True,
        "tutor_hint":        "Student is confused. Switch to analogy or real-world example. Simplify language. Do NOT advance.",
        "xp_hint":           "Try again — you can get this! 💡",
    },
    "struggling": {
        "explanation_mode":  "breakdown",
        "language_level":    "very_simple",
        "bloom_adjustment":  -2,
        "scaffold":          True,
        "tutor_hint":        "Student is struggling. Break into smallest steps. Use a numbered walkthrough. Offer encouragement.",
        "xp_hint":           "Every expert was once a beginner. Let's break this down! 🌱",
    },
    "overconfident": {
        "explanation_mode":  "counterexample",
        "language_level":    "standard",
        "bloom_adjustment":  0,
        "scaffold":          False,
        "tutor_hint":        "Student answered fast but incorrectly — possibly guessing. Challenge with a counterexample or edge case.",
        "xp_hint":           "Interesting try! Let me show you a tricky edge case. 🎯",
    },
    "careful": {
        "explanation_mode":  "validation",
        "language_level":    "standard",
        "bloom_adjustment":  1,
        "scaffold":          False,
        "tutor_hint":        "Student is thinking carefully and got it right. Validate their reasoning. Ready to advance.",
        "xp_hint":           "Excellent deep thinking! +XP for your thoroughness 🏆",
    },
    "confident": {
        "explanation_mode":  "challenge",
        "language_level":    "advanced",
        "bloom_adjustment":  2,
        "scaffold":          False,
        "tutor_hint":        "Student is confident and correct. Advance Bloom level. Reduce scaffolding. Move to next topic quickly.",
        "xp_hint":           "Brilliant! You're on fire! 🔥 +XP",
    },
    "engaged": {
        "explanation_mode":  "standard",
        "language_level":    "standard",
        "bloom_adjustment":  1,
        "scaffold":          False,
        "tutor_hint":        "Student is engaged. Continue at current pace. Advance one Bloom level.",
        "xp_hint":           "Great work! Keep it up! ✨",
    },
}


def get_adaptive_directive(
    emotion_state: str,
    current_bloom: int = 2,
) -> dict:
    """
    Return teaching directive for a given emotion state.
    Clamps bloom_level to [1, 6].
    """
    directive = DIRECTIVES.get(emotion_state, DIRECTIVES["engaged"]).copy()
    new_bloom = max(1, min(6, current_bloom + directive["bloom_adjustment"]))
    directive["new_bloom_level"] = new_bloom
    directive["emotion_state"]   = emotion_state
    return directive


async def log_adaptive_directive(
    pool,
    student_db_id: int,
    session_id: str,
    emotion_state: str,
    directive: dict,
    hesitation_score: int = 0,
    checkpoint_score: float = 0.0,
    bloom_level: int = 2,
) -> None:
    """Persist adaptive directive to DB for audit + future ML use."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO adaptive_directives
                    (student_db_id, session_id, emotion_state, bloom_level,
                     directive, hesitation_score, checkpoint_score)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                student_db_id,
                session_id,
                emotion_state,
                bloom_level,
                directive.get("tutor_hint", ""),
                hesitation_score,
                checkpoint_score,
            )
    except Exception as e:
        logger.warning(f"Adaptive directive log failed: {e}")


# ── V8: Burnout Detection ─────────────────────────────────────────────────────

def detect_burnout(break_log: list, attention_log: list) -> dict:
    """
    Analyze session patterns to detect burnout risk.
    break_log: [{ session_minutes, break_at }]
    attention_log: [{ is_visible, ts }]
    Returns: { burnout_score, risk_level, signals, recommendation, break_suggestion }
    """
    signals = []
    score = 0.0  # 0.0 (none) → 1.0 (critical)

    # Signal 1: Too many long sessions (> 90 min in past 3 days)
    long_sessions = [b for b in break_log if b.get("session_minutes", 0) >= 90]
    if len(long_sessions) >= 3:
        signals.append("3+ sessions over 90 minutes in last week")
        score += 0.3
    elif len(long_sessions) >= 1:
        signals.append("Extended study sessions detected")
        score += 0.15

    # Signal 2: High session frequency (> 8 sessions in past week)
    if len(break_log) >= 8:
        signals.append(f"{len(break_log)} sessions in last 7 days — very high frequency")
        score += 0.2

    # Signal 3: Low attention visibility (>30% of heartbeats hidden)
    total_hb = len(attention_log)
    if total_hb >= 5:
        hidden = sum(1 for h in attention_log if not h.get("is_visible", True))
        hidden_pct = hidden / total_hb
        if hidden_pct > 0.4:
            signals.append(f"Tab hidden {int(hidden_pct * 100)}% of study time — attention drifting")
            score += 0.25
        elif hidden_pct > 0.2:
            signals.append("Frequent tab switching detected")
            score += 0.1

    # Signal 4: No breaks between long sessions
    if len(break_log) > 3:
        total_mins = sum(b.get("session_minutes", 0) for b in break_log[:3])
        if total_mins > 180:
            signals.append("Over 3 hours of study with minimal breaks")
            score += 0.25

    score = min(1.0, score)

    if score >= 0.7:
        risk_level = "high"
        recommendation = "⚠️ You're showing signs of burnout. Take a 30-minute break and get some rest. Sleep consolidates memory — studying while tired is counterproductive."
        break_suggestion = True
    elif score >= 0.4:
        risk_level = "moderate"
        recommendation = "😴 You've been studying a lot. Take a 15-minute break, hydrate, and stretch. Your brain will retain more after a short rest."
        break_suggestion = True
    elif score >= 0.2:
        risk_level = "low"
        recommendation = "👍 Good study rhythm. Keep sessions to 45-50 minutes then take short breaks (Pomodoro technique)."
        break_suggestion = False
    else:
        risk_level = "none"
        recommendation = "🌟 Great balance! You're studying efficiently. Keep it up!"
        break_suggestion = False

    return {
        "burnout_score": round(score, 2),
        "risk_level": risk_level,
        "signals": signals,
        "recommendation": recommendation,
        "break_suggestion": break_suggestion,
        "sessions_analyzed": len(break_log),
    }


# ── V8: Attention Score ───────────────────────────────────────────────────────

def estimate_attention_score(heartbeats: list) -> dict:
    """
    Compute attention quality from visibility heartbeats.
    heartbeats: [{ is_visible: bool }]
    Returns: { score, hidden_pct, total_heartbeats, recommendation }
    """
    total = len(heartbeats)
    if total == 0:
        return {
            "score": 1.0,
            "hidden_pct": 0,
            "total_heartbeats": 0,
            "recommendation": "Start a lesson to track your focus!",
        }

    hidden = sum(1 for h in heartbeats if not h.get("is_visible", True))
    hidden_pct = round(hidden / total, 2)
    score = round(1.0 - hidden_pct, 2)

    if score >= 0.85:
        recommendation = "🎯 Excellent focus! You're fully engaged."
    elif score >= 0.65:
        recommendation = "👀 Good attention, with some distractions. Try to stay on this tab during lessons."
    elif score >= 0.4:
        recommendation = "😕 Your attention is split. Close distracting tabs and focus on the lesson."
    else:
        recommendation = "⚠️ Very low focus detected. Find a quiet space and eliminate distractions."

    return {
        "score": score,
        "hidden_pct": int(hidden_pct * 100),
        "total_heartbeats": total,
        "recommendation": recommendation,
    }


# ── V8: Silence Confusion Detector ───────────────────────────────────────────

def check_silence_confusion(silence_ms: int, topic: str = "", step_num: int = 0) -> dict:
    """
    Detect confusion from prolonged silence during a lesson.
    silence_ms: milliseconds of inactivity
    Returns: { confusion_suspected, severity, suggestion, directive }
    """
    silence_s = silence_ms / 1000

    if silence_s < 45:
        return {
            "confusion_suspected": False,
            "severity": "none",
            "suggestion": "Still within normal response time.",
            "directive": None,
        }
    elif silence_s < 90:
        return {
            "confusion_suspected": True,
            "severity": "mild",
            "suggestion": f"💡 Stuck on Step {step_num}? Try asking a question below or click 'Get Help' for an alternative explanation.",
            "directive": {"explanation_mode": "hint", "bloom_adjustment": 0},
        }
    elif silence_s < 180:
        return {
            "confusion_suspected": True,
            "severity": "moderate",
            "suggestion": f"🤔 You've been quiet for a while on '{topic}'. Would you like a simpler explanation or an analogy?",
            "directive": {"explanation_mode": "analogy", "bloom_adjustment": -1},
        }
    else:
        return {
            "confusion_suspected": True,
            "severity": "high",
            "suggestion": "😵 Looks like this concept might need a break. Rest for 5 minutes, then we'll try a completely different approach.",
            "directive": {"explanation_mode": "breakdown", "bloom_adjustment": -2},
        }

