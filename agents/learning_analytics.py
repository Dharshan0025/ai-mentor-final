"""
Learning outcome tracking per session.
Measures student progress, engagement, and learning effectiveness.
"""
import json
import logging
from datetime import datetime
from typing import Optional, List
from db import db

logger = logging.getLogger(__name__)


class LearningSessionAnalytics:
    """Track learning outcomes per chat session."""

    def __init__(self, session_id: str, student_id: str):
        self.session_id = session_id
        self.student_id = student_id
        self.start_time = datetime.now()
        self.metrics = {
            "session_id": session_id,
            "student_id": student_id,
            "start_time": self.start_time.isoformat(),
            "messages_exchanged": 0,
            "questions_asked": 0,
            "insights_provided": 0,
            "avg_response_quality": 0.0,
            "engagement_score": 0.0,
            "topics_covered": [],
            "concepts_learned": [],
            "misconceptions_corrected": 0,
            "follow_up_questions": 0,
            "student_satisfaction": 0.0,
            "ai_confidence_avg": 0.85,
            "learning_bloom_progression": [],  # Bloom level progression
        }

    async def track_message(
        self,
        message_type: str,  # "user_question" | "mentor_response"
        content: str,
        metadata: Optional[dict] = None
    ):
        """Track a message in the session."""
        if message_type == "user_question":
            self.metrics["questions_asked"] += 1
        elif message_type == "mentor_response":
            self.metrics["insights_provided"] += 1

        self.metrics["messages_exchanged"] += 1

        # Extract topics from content
        if metadata and "topics" in metadata:
            self.metrics["topics_covered"].extend(metadata["topics"])

    async def track_learning_moment(
        self,
        concept: str,
        bloom_level: int,
        confidence: float = 0.85
    ):
        """Track when student learns a new concept."""
        if concept not in self.metrics["concepts_learned"]:
            self.metrics["concepts_learned"].append(concept)
            self.metrics["learning_bloom_progression"].append({
                "concept": concept,
                "bloom_level": bloom_level,
                "timestamp": datetime.now().isoformat(),
                "ai_confidence": confidence,
            })
        logger.info(f"📚 Concept learned: {concept} (Bloom L{bloom_level})")

    async def track_misconception(self):
        """Track when a misconception is corrected."""
        self.metrics["misconceptions_corrected"] += 1
        logger.info(f"✅ Misconception corrected")

    async def track_follow_up_question(self):
        """Track follow-up questions (indicates deeper engagement)."""
        self.metrics["follow_up_questions"] += 1

    async def calculate_engagement_score(self) -> float:
        """
        Calculate engagement score (0-100).
        Based on: message count, follow-ups, topics, depth.
        """
        base_score = min(self.metrics["messages_exchanged"] * 5, 40)  # Up to 40
        follow_up_bonus = min(self.metrics["follow_up_questions"] * 10, 30)  # Up to 30
        breadth_bonus = min(len(set(self.metrics["topics_covered"])) * 5, 20)  # Up to 20
        depth_bonus = min(len(self.metrics["concepts_learned"]) * 5, 10)  # Up to 10

        engagement = base_score + follow_up_bonus + breadth_bonus + depth_bonus
        self.metrics["engagement_score"] = min(engagement, 100)
        return self.metrics["engagement_score"]

    async def calculate_response_quality(
        self,
        pipeline_confidence: float,
        student_feedback: Optional[float] = None
    ) -> float:
        """
        Calculate average response quality (0-100).
        Based on: AI pipeline confidence, student feedback, factual accuracy.
        """
        ai_score = pipeline_confidence * 100  # Use pipeline confidence

        if student_feedback:
            # Student can rate 1-5, convert to 0-100
            quality = (ai_score * 0.7) + (student_feedback * 20 * 0.3)
        else:
            quality = ai_score

        self.metrics["avg_response_quality"] = min(quality, 100)
        self.metrics["ai_confidence_avg"] = pipeline_confidence
        return self.metrics["avg_response_quality"]

    async def finalize_session(self) -> dict:
        """Finalize session and calculate learning outcomes."""
        end_time = datetime.now()
        duration_minutes = (end_time - self.start_time).total_seconds() / 60

        # Calculate engagement
        await self.calculate_engagement_score()

        # Build final metrics
        self.metrics.update({
            "end_time": end_time.isoformat(),
            "duration_minutes": round(duration_minutes, 2),
            "topics_unique": len(set(self.metrics["topics_covered"])),
            "concepts_learned_count": len(self.metrics["concepts_learned"]),
            "avg_bloom_level": (
                sum(p["bloom_level"] for p in self.metrics["learning_bloom_progression"]) /
                len(self.metrics["learning_bloom_progression"])
                if self.metrics["learning_bloom_progression"]
                else 2
            ),
        })

        # Save to database if connected
        if hasattr(db, "save_learning_session"):
            try:
                await db.save_learning_session(self.metrics)
                logger.info(f"✅ Learning session saved: {self.session_id}")
            except Exception as e:
                logger.warning(f"Learning session save failed: {e}")

        return self.metrics

    def get_summary(self) -> dict:
        """Get human-readable summary of learning session."""
        return {
            "duration": f"{self.metrics['duration_minutes']} min",
            "engagement": f"{self.metrics['engagement_score']:.0f}/100",
            "quality": f"{self.metrics['avg_response_quality']:.0f}/100",
            "concepts_learned": self.metrics["concepts_learned"],
            "topics_covered": list(set(self.metrics["topics_covered"])),
            "follow_ups": self.metrics["follow_up_questions"],
            "misconceptions_fixed": self.metrics["misconceptions_corrected"],
            "avg_bloom_level": self.metrics.get("avg_bloom_level", 2),
        }


# Global session tracking
_active_sessions: dict[str, LearningSessionAnalytics] = {}


def get_session_analytics(session_id: str, student_id: str = "") -> LearningSessionAnalytics:
    """Get or create session analytics tracker."""
    if session_id not in _active_sessions:
        _active_sessions[session_id] = LearningSessionAnalytics(session_id, student_id)
    return _active_sessions[session_id]


def cleanup_old_sessions():
    """Cleanup old sessions (>2 hours old)."""
    import time
    from datetime import timedelta

    current_time = datetime.now()
    to_remove = []

    for session_id, analytics in _active_sessions.items():
        if (current_time - analytics.start_time) > timedelta(hours=2):
            to_remove.append(session_id)

    for session_id in to_remove:
        del _active_sessions[session_id]

    if to_remove:
        logger.info(f"🧹 Cleaned up {len(to_remove)} old learning sessions")


async def get_student_learning_metrics(student_id: str) -> dict:
    """
    Get aggregated learning metrics for a student.
    Includes: total concepts learned, avg engagement, improvement trajectory.
    """
    if not hasattr(db, "get_student_learning_sessions"):
        return {}

    try:
        sessions = await db.get_student_learning_sessions(student_id, limit=10)
        if not sessions:
            return {"message": "No learning data yet"}

        total_sessions = len(sessions)
        total_concepts = sum(s.get("concepts_learned_count", 0) for s in sessions)
        avg_engagement = sum(s.get("engagement_score", 0) for s in sessions) / max(total_sessions, 1)
        avg_quality = sum(s.get("avg_response_quality", 0) for s in sessions) / max(total_sessions, 1)

        # Trend analysis
        recent_3 = sessions[:3]
        older_sessions = sessions[3:]
        recent_avg = sum(s.get("engagement_score", 0) for s in recent_3) / max(len(recent_3), 1)
        older_avg = sum(s.get("engagement_score", 0) for s in older_sessions) / max(len(older_sessions), 1)
        improvement_trend = "📈 Improving" if recent_avg > older_avg else "📉 Declining" if recent_avg < older_avg else "➡️ Stable"

        return {
            "total_sessions": total_sessions,
            "total_concepts_learned": total_concepts,
            "avg_engagement_score": round(avg_engagement, 1),
            "avg_response_quality": round(avg_quality, 1),
            "improvement_trend": improvement_trend,
            "recent_topics": list(set(sum((s.get("topics_covered", []) for s in recent_3), []))),
        }
    except Exception as e:
        logger.warning(f"Student learning metrics failed: {e}")
        return {}
