"""
Pipeline Tracker - Capture AI thinking process at each stage
Shows students how the AI reasons through problems (like Perplexity)
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PipelineTracker:
    """
    Tracks each stage of the AI reasoning pipeline.
    Shows what the AI is thinking at each step.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset tracker for new request"""
        self.intent = None
        self.agent_selection = None
        self.context = None
        self.agent_outputs = {}
        self.synthesis = None
        self.overall_confidence = 0.0
        self.stages_timing = {}
        self.start_time = datetime.now()

    def track_intent_parsing(
        self,
        user_message: str,
        intent: str,
        confidence: float = 0.0,
        reasoning: Optional[str] = None
    ):
        """Stage 1: Intent Parsing"""
        self.intent = {
            "user_message": user_message,
            "intent": intent,
            "confidence": confidence,
            "reasoning": reasoning,
        }
        logger.info(f"✅ Intent parsed: {intent} ({confidence:.2%})")

    def track_agent_selection(
        self,
        primary_agent: str,
        supporting_agents: List[str] = None,
        reasoning: Optional[str] = None
    ):
        """Stage 2: Agent Selection"""
        self.agent_selection = {
            "primary": primary_agent,
            "supporting": supporting_agents or [],
            "reasoning": reasoning,
        }
        agents_str = primary_agent
        if supporting_agents:
            agents_str += f" + {', '.join(supporting_agents)}"
        logger.info(f"✅ Agents selected: {agents_str}")

    def track_context_loading(
        self,
        profile: Optional[Dict[str, Any]] = None,
        sentiment: Optional[float] = None,
        bloom: Optional[int] = None,
        learning_style: Optional[str] = None,
        peak_hour: Optional[str] = None,
        exam_days: Optional[int] = None,
    ):
        """Stage 3: Context Loading"""
        self.context = {
            "profile": profile,
            "sentiment": sentiment,
            "bloom": bloom,
            "learning_style": learning_style,
            "peak_hour": peak_hour,
            "exam_days": exam_days,
        }
        logger.info(f"✅ Context loaded (CGPA: {profile.get('cgpa', 'N/A')}, Bloom: L{bloom}/6)")

    def track_agent_reasoning(
        self,
        agent_name: str,
        reasoning: Optional[str] = None,
        key_insight: Optional[str] = None,
        score: float = 0.0,
    ):
        """Stage 4: Agent Reasoning"""
        self.agent_outputs[agent_name] = {
            "reasoning": reasoning,
            "key_insight": key_insight,
            "score": score,
        }
        logger.info(f"✅ {agent_name} agent computed (confidence: {score:.2%})")

    def track_synthesis(
        self,
        response_mode: Optional[str] = None,
        tone: Optional[str] = None,
        personalization: List[str] = None,
        ui_widgets: List[str] = None,
    ):
        """Stage 5: Response Synthesis"""
        self.synthesis = {
            "response_mode": response_mode,
            "tone": tone,
            "personalization": personalization or [],
            "ui_widgets": ui_widgets or [],
        }
        logger.info(f"✅ Response synthesized ({response_mode} mode, {len(ui_widgets or [])} widgets)")

    def set_overall_confidence(self, confidence: float):
        """Set overall response confidence"""
        self.overall_confidence = min(1.0, max(0.0, confidence))
        logger.info(f"✅ Overall confidence: {self.overall_confidence:.2%}")

    def get_pipeline_data(self) -> Dict[str, Any]:
        """Return complete pipeline data for frontend"""
        return {
            "intent": self.intent,
            "agent_selection": self.agent_selection,
            "context": self.context,
            "agent_outputs": self.agent_outputs or None,
            "synthesis": self.synthesis,
            "overall_confidence": self.overall_confidence,
        }

    def get_timing(self) -> Dict[str, float]:
        """Get stage timings in milliseconds"""
        elapsed = (datetime.now() - self.start_time).total_seconds() * 1000
        return {
            "total_ms": elapsed,
            "stages": self.stages_timing,
        }


# Global instance
_tracker = PipelineTracker()


def get_tracker() -> PipelineTracker:
    """Get global pipeline tracker instance"""
    return _tracker


def reset_tracker():
    """Reset tracker for new request"""
    _tracker.reset()
