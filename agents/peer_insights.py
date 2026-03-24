"""
Peer Comparison & Insights — Show how student is doing relative to peers.
Motivates through social comparison while maintaining privacy.
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from db import db

logger = logging.getLogger(__name__)


class PeerInsightsAnalyzer:
    """Analyze student performance vs peer group."""

    def __init__(self, student_id: str):
        self.student_id = student_id
        self.cache = {
            "last_updated": None,
            "percentile": None,
            "peer_metrics": None,
        }

    async def calculate_percentile(
        self,
        metric: str,  # "cgpa", "engagement", "concepts_learned"
        value: float,
        cohort: str = "all",  # "all", "same_year", "same_major"
    ) -> float:
        """
        Calculate student's percentile in peer group.
        Returns 0-100 where 100 is best.
        """
        if not hasattr(db, "get_cohort_stats"):
            return 50.0  # Default to middle if no data

        try:
            stats = await db.get_cohort_stats(metric, cohort)
            if not stats:
                return 50.0

            # Find percentile using distribution
            values = stats.get("values", [])
            if not values:
                return 50.0

            sorted_values = sorted(values)
            position = sum(1 for v in sorted_values if v <= value) / len(sorted_values) * 100
            return round(position, 1)
        except Exception as e:
            logger.warning(f"Percentile calculation failed: {e}")
            return 50.0

    async def get_peer_comparison(self, student_profile: dict) -> dict:
        """
        Get comprehensive peer comparison data.
        What percentile is student at for: CGPA, engagement, learning speed.
        """
        if (
            self.cache.get("last_updated")
            and (datetime.now() - self.cache["last_updated"]).total_seconds() < 3600
        ):
            # Use cached data (1 hour TTL)
            logger.info(f"✅ Using cached peer insights for {self.student_id}")
            return self.cache["peer_metrics"]

        try:
            cgpa = student_profile.get("cgpa", 0.0)
            engagement_score = student_profile.get("engagement_score", 50)
            concepts_learned = student_profile.get("concepts_learned_count", 0)
            study_hours = student_profile.get("weekly_study_hours", 0)
            year = student_profile.get("year", 1)

            # Calculate percentiles
            cgpa_percentile = await self.calculate_percentile(
                "cgpa", cgpa, cohort=f"year_{year}"
            )
            engagement_percentile = await self.calculate_percentile(
                "engagement", engagement_score, cohort="all"
            )
            learning_speed_percentile = await self.calculate_percentile(
                "concepts_per_week",
                concepts_learned / max(student_profile.get("weeks_active", 1), 1),
                cohort=f"year_{year}"
            )
            study_consistency_percentile = await self.calculate_percentile(
                "study_hours", study_hours, cohort="all"
            )

            # Get comparison tags
            tags = self._generate_comparison_tags(
                cgpa_percentile,
                engagement_percentile,
                learning_speed_percentile,
                study_consistency_percentile,
            )

            comparison_data = {
                "timestamp": datetime.now().isoformat(),
                "metrics": {
                    "cgpa": {
                        "value": round(cgpa, 2),
                        "percentile": cgpa_percentile,
                        "status": "Above average" if cgpa_percentile > 60 else "Below average" if cgpa_percentile < 40 else "Average",
                    },
                    "engagement": {
                        "value": round(engagement_score, 1),
                        "percentile": engagement_percentile,
                        "status": "High" if engagement_percentile > 70 else "Low" if engagement_percentile < 30 else "Moderate",
                    },
                    "learning_speed": {
                        "value": round(concepts_learned, 1),
                        "percentile": learning_speed_percentile,
                        "status": "Fast learner" if learning_speed_percentile > 65 else "Steady learner" if learning_speed_percentile > 35 else "Take it slow",
                    },
                    "study_consistency": {
                        "value": round(study_hours, 1),
                        "percentile": study_consistency_percentile,
                        "status": "Very consistent" if study_consistency_percentile > 70 else "Moderate" if study_consistency_percentile > 40 else "Needs improvement",
                    },
                },
                "summary": {
                    "overall_percentile": round(
                        (cgpa_percentile + engagement_percentile + learning_speed_percentile + study_consistency_percentile) / 4,
                        1
                    ),
                    "strengths": tags["strengths"],
                    "areas_for_improvement": tags["improvements"],
                    "peer_comparison_message": tags["message"],
                },
            }

            # Cache result
            self.cache = {
                "last_updated": datetime.now(),
                "percentile": comparison_data["summary"]["overall_percentile"],
                "peer_metrics": comparison_data,
            }

            logger.info(f"✅ Peer comparison calculated: {self.student_id} at {comparison_data['summary']['overall_percentile']}th percentile")
            return comparison_data

        except Exception as e:
            logger.warning(f"Peer comparison failed: {e}")
            return {"error": str(e)}

    def _generate_comparison_tags(
        self,
        cgpa_p: float,
        engagement_p: float,
        learning_p: float,
        consistency_p: float,
    ) -> dict:
        """Generate motivational comparison messages."""
        strengths = []
        improvements = []

        # Strengths
        if cgpa_p > 75:
            strengths.append("🎓 Top-tier CGPA (75th+ percentile)")
        if engagement_p > 80:
            strengths.append("🔥 Highly engaged learner")
        if learning_p > 70:
            strengths.append("⚡ Fast learner")
        if consistency_p > 75:
            strengths.append("📅 Very consistent study habits")

        # Improvements
        if cgpa_p < 30:
            improvements.append("📚 Focus on CGPA improvement")
        if engagement_p < 35:
            improvements.append("💪 Increase engagement frequency")
        if learning_p < 40:
            improvements.append("🎯 Try deeper concept exploration")
        if consistency_p < 30:
            improvements.append("⏰ Build more consistent study routine")

        # Generate message
        if not strengths and not improvements:
            message = f"You're in the {max(cgpa_p, engagement_p, learning_p, consistency_p):.0f}th percentile overall — keep up the steady work!"
        elif cgpa_p > 70 and engagement_p > 70:
            message = "🌟 You're outperforming most peers in academics and engagement! Keep this momentum!"
        elif learning_p > 75:
            message = "⚡ You learn fast! Challenge yourself with harder topics."
        elif consistency_p > 75:
            message = "📅 Your consistency is your superpower. Now focus on depth!"
        else:
            message = "💡 You're on a steady trajectory. Identify one area to focus on this week."

        return {
            "strengths": strengths or ["You're making progress!"],
            "improvements": improvements or ["Everything looks good!"],
            "message": message,
        }


class PeerInsightsSuggestions:
    """Generate personalized suggestions based on peer data."""

    @staticmethod
    async def suggest_next_steps(
        student_profile: dict,
        peer_comparison: dict,
    ) -> List[str]:
        """
        Generate action-oriented suggestions based on peer comparison.
        """
        suggestions = []
        summary = peer_comparison.get("summary", {})

        # CGPA improvement
        cgpa_p = peer_comparison.get("metrics", {}).get("cgpa", {}).get("percentile", 50)
        if cgpa_p < 40:
            suggestions.append(
                "📚 Your CGPA is below average. Try the 'Weak Areas' feature to focus on your poorest subjects."
            )
        elif cgpa_p > 80:
            suggestions.append("🏆 Your CGPA is excellent! Help peers — teach one concept this week.")

        # Engagement
        engagement_p = peer_comparison.get("metrics", {}).get("engagement", {}).get("percentile", 50)
        if engagement_p < 30:
            suggestions.append(
                "💬 Try our commitment contracts — students who set goals improve 40% faster."
            )

        # Learning speed
        learning_p = peer_comparison.get("metrics", {}).get("learning_speed", {}).get("percentile", 50)
        if learning_p > 75:
            suggestions.append("⚡ You're learning fast! Try advanced topics in your weak areas.")
        elif learning_p < 35:
            suggestions.append("🐢 Take more time with fundamentals. Quality > Speed!")

        # Study consistency
        consistency_p = peer_comparison.get("metrics", {}).get("study_consistency", {}).get("percentile", 50)
        if consistency_p < 25:
            suggestions.append(
                "⏰ Build a consistent study routine. 30 min daily beats 3 hours once a week."
            )

        # Fallback
        if not suggestions:
            suggestions = [
                "You're doing well! Focus on one weak area this week.",
                "Have you explored the tutor feature for deep learning?",
            ]

        return suggestions[:3]  # Top 3 suggestions


async def get_response_with_peer_insights(
    response_content: str,
    student_id: str,
    student_profile: dict,
) -> dict:
    """
    Enhance response with peer comparison insights.
    """
    analyzer = PeerInsightsAnalyzer(student_id)
    peer_comparison = await analyzer.get_peer_comparison(student_profile)

    suggestions = await PeerInsightsSuggestions.suggest_next_steps(
        student_profile,
        peer_comparison,
    )

    return {
        "content": response_content,
        "peer_insights": {
            "comparison": peer_comparison.get("summary", {}),
            "suggestions": suggestions,
        },
    }
